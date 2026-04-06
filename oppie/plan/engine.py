import json
import logging
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.config import OppieConfig
from oppie.engine import EngineMode, run_engine
from oppie.llm import create_llm_provider
from oppie.models.apply import ApplyResult, OperationResult, OperationStatus
from oppie.models.drift import DriftResolution, DriftResult, FieldDrift
from oppie.models.operation import Operation
from oppie.models.plan import PLAN_INDEX_FILENAME, Plan, PlanStatus
from oppie.prompts.builder import PromptMode, build_system_prompt, flatten_system_prompt
from oppie.prompts.formatting import (
    format_past_plans,
    format_tickets_for_llm,
)
from oppie.providers.base import TicketProvider
from oppie.run_log import RunLog, RunLogEntry, generate_run_id
from oppie.tools.base import ToolContext
from oppie.tools.operations import PROPOSE_OPERATION_TOOL
from oppie.tools.tickets import GET_TICKET_TOOL, SEARCH_TICKETS_TOOL

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PreApplyCheck:
    """Result of pre-apply validation (integrity, drift, capabilities)."""

    plan: Plan
    integrity_ok: bool
    already_applied: bool
    drift: DriftResult
    capability_errors: list[str] = field(default_factory=list)

    @property
    def can_apply(self) -> bool:
        """Return True if apply can proceed without resolution or force."""
        return (
            self.integrity_ok
            and not self.already_applied
            and not self.drift.has_critical
            and not self.capability_errors
        )


async def generate_plan(
    provider: TicketProvider,
    config: OppieConfig,
    instruction: str,
    *,
    save: bool = True,
) -> Plan:
    """Generate a plan from a user instruction using the agent loop."""
    logger.info('Generating plan for instruction: %r', instruction)
    home = provider.home

    # 1. Load tickets
    tickets = provider.list_tickets()
    ticket_snapshots = {t.id: t for t in tickets}
    logger.debug('Loaded %d tickets', len(tickets))

    # 2. Create LLM provider
    llm = create_llm_provider(config.llm)

    # 3. Build layered system prompt
    past_plans = _find_similar_plans(home, instruction)
    past_plans_text = format_past_plans(past_plans)
    system_parts = build_system_prompt(
        mode=PromptMode.PLAN,
        home=home,
        capabilities=provider.capabilities,
        past_plans_text=past_plans_text,
    )
    system_prompt = flatten_system_prompt(system_parts)
    system_parts_dicts = [
        {
            'content': p.content,
            **({'cache_control': p.cache_control} if p.cache_control else {}),
        }
        for p in system_parts
    ]

    # Build user prompt with ticket summary
    ticket_summary = format_tickets_for_llm(tickets)
    user_prompt = (
        f'# Current tickets\n{ticket_summary}\n\n# User instruction\n{instruction}'
    )

    # Set up tools and context
    all_tools = [SEARCH_TICKETS_TOOL, GET_TICKET_TOOL, PROPOSE_OPERATION_TOOL]
    tool_context = ToolContext(
        provider=provider,
        home=home,
        capabilities=provider.capabilities,
    )

    max_tokens = config.llm.max_tokens
    temperature = config.llm.temperature

    # 4. Run agent loop (research -> propose -> summary)
    async with llm:
        result = await run_engine(
            prompt=user_prompt,
            tools=all_tools,
            llm=llm,
            tool_context=tool_context,
            mode=EngineMode.PLAN,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            system_parts=system_parts_dicts,
        )

    operations = result.operations

    # 5. Preflight validation
    preflight_errors = _run_preflight(provider, operations)
    status = PlanStatus.INVALID if preflight_errors else PlanStatus.SAVED
    risks: list[str] = []
    if preflight_errors:
        risks.extend(preflight_errors)

    # Extract risks from the final text (LLM summary)
    if result.text:
        risks.append(result.text)

    plan = Plan(
        instruction=instruction,
        operations=operations,
        risks=risks,
        created_at=datetime.now(UTC).isoformat(),
        status=status,
        ticket_snapshots=ticket_snapshots,
    )

    # 6. Optionally save plan
    if save:
        plan.save(home)
        logger.info(
            'Plan %s saved with %d operations', plan.plan_id, len(plan.operations)
        )
    return plan


async def amend_plan(
    provider: TicketProvider,
    config: OppieConfig,
    plan_id: str,
) -> Plan:
    """Load an existing plan and re-generate with current state.

    Set parent_plan_id to the original plan's ID.
    The new plan gets its own ID (content hash of new operations).
    """
    logger.info('Amending plan %s', plan_id)
    home = provider.home
    original = load_plan(home, plan_id)
    new_plan = await generate_plan(provider, config, original.instruction)
    new_plan.parent_plan_id = plan_id
    logger.debug('New plan %s (parent=%s)', new_plan.plan_id, plan_id)
    # Re-save with parent_plan_id set
    new_plan.save(home)
    return new_plan


def check_apply(
    provider: TicketProvider,
    plan_id: str,
) -> PreApplyCheck:
    """Run all pre-apply validations: integrity, already-applied, drift, capabilities.

    Return a PreApplyCheck with results for the UI layer to inspect.
    """
    logger.info('Checking plan %s for apply', plan_id)
    plan = load_plan(provider.home, plan_id)

    # Integrity check
    recomputed = Plan.compute_id(plan.operations)
    integrity_ok = recomputed == plan.plan_id

    # Already applied check
    already_applied = plan.status == PlanStatus.APPLIED

    # Drift check
    drift = _check_drift(provider, plan)

    # Capability re-check
    capability_errors = provider.validate_operations(plan.operations)

    logger.debug(
        'Integrity=%s, already_applied=%s, drift_critical=%d, drift_info=%d, cap_errors=%d',
        integrity_ok,
        already_applied,
        len(drift.critical_drifts),
        len(drift.informational_drifts),
        len(capability_errors),
    )
    plan.checked = True
    plan.save(provider.home)

    return PreApplyCheck(
        plan=plan,
        integrity_ok=integrity_ok,
        already_applied=already_applied,
        drift=drift,
        capability_errors=capability_errors,
    )


def execute_apply(
    provider: TicketProvider,
    plan_id: str,
    force: bool = False,
    resolutions: dict[tuple[str, str], DriftResolution] | None = None,
) -> ApplyResult:
    """Execute a plan's operations against the provider.

    Requires check_apply() to have been called first (sets plan.checked).
    Re-validates integrity and drift as a safety net.
    Executes operations sequentially, stops on first failure.
    """
    logger.info('Executing apply for plan %s', plan_id)
    home = provider.home
    plan = load_plan(home, plan_id)

    if not plan.checked:
        raise ValueError(
            f'Plan {plan_id} has not been checked. Call check_apply() first.'
        )

    # Safety re-checks (defense in depth — state may have changed since check)
    recomputed = Plan.compute_id(plan.operations)
    if recomputed != plan.plan_id:
        raise ValueError(
            f'Plan integrity check failed: expected {plan.plan_id}, got {recomputed}'
        )

    if plan.status == PlanStatus.APPLIED:
        raise ValueError(f'Plan {plan_id} has already been applied')

    drift = _check_drift(provider, plan)

    if drift.deleted_tickets:
        raise ValueError(
            f'Cannot apply: tickets deleted since plan creation: '
            f'{", ".join(drift.deleted_tickets)}'
        )

    if drift.has_critical and not force and not resolutions:
        raise ValueError(
            f'Critical drift detected on {len(drift.critical_drifts)} '
            f'field(s). Provide resolutions or use force=True.'
        )

    # Build effective operations list based on resolutions
    effective_ops = list(plan.operations)
    if drift.has_critical and resolutions and not force:
        effective_ops = _resolve_operations(plan.operations, resolutions)

    # Execute operations
    apply_id = str(uuid.uuid4())
    start_time = time.monotonic()
    results: list[OperationResult] = []
    failed = False

    for i, op in enumerate(effective_ops):
        if op is None:
            # Operation was resolved as SKIP_OPERATION or KEEP_CURRENT_VALUE
            results.append(
                OperationResult(
                    operation=plan.operations[i],
                    status=OperationStatus.SKIPPED,
                    error='Skipped via drift resolution',
                )
            )
            continue

        if failed:
            results.append(
                OperationResult(
                    operation=op,
                    status=OperationStatus.SKIPPED,
                )
            )
            continue

        try:
            provider.update_ticket(op.ticket_id, {op.field: op.after_value})
            result = OperationResult(operation=op, status=OperationStatus.OK)
            results.append(result)
            logger.debug(
                'Operation %d/%d: %s.%s -> %s',
                i + 1,
                len(effective_ops),
                op.ticket_id,
                op.field,
                result.status.value,
            )
        except Exception as e:
            result = OperationResult(
                operation=op,
                status=OperationStatus.FAILED,
                error=str(e),
            )
            results.append(result)
            logger.debug(
                'Operation %d/%d: %s.%s -> %s',
                i + 1,
                len(effective_ops),
                op.ticket_id,
                op.field,
                result.status.value,
            )
            failed = True

    duration = time.monotonic() - start_time
    ok_count = sum(1 for r in results if r.status == OperationStatus.OK)
    fail_count = sum(1 for r in results if r.status == OperationStatus.FAILED)
    skip_count = sum(1 for r in results if r.status == OperationStatus.SKIPPED)
    logger.info(
        'Apply %s complete: %.2fs, %d ok, %d failed, %d skipped',
        apply_id,
        duration,
        ok_count,
        fail_count,
        skip_count,
    )
    created_at = datetime.now(UTC).isoformat()

    apply_result = ApplyResult(
        apply_id=apply_id,
        plan=plan,
        results=results,
        duration=duration,
        created_at=created_at,
    )

    # Mark plan as applied and save
    plan.status = PlanStatus.APPLIED
    plan.save(home)

    # Write apply artifact
    artifact_store = ArtifactStore(home)
    run_id = generate_run_id()
    artifact_content = apply_result.build_artifact()
    artifact_path = artifact_store.save_artifact(
        ArtifactType.APPLY, artifact_content, run_id
    )

    # Append run log
    run_log = RunLog(home)
    run_log.append(
        RunLogEntry(
            run_id=run_id,
            command='apply',
            timestamp=created_at,
            duration=duration,
            artifact_paths=[str(artifact_path)],
            plan_id=plan_id,
            apply_id=apply_id,
        )
    )

    return apply_result


def load_plan(home: Path, plan_id: str) -> Plan:
    """Load a plan by ID from artifacts/plans/plan-{plan_id}.json.

    Raise FileNotFoundError if not found.
    """
    path = home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
    if not path.exists():
        raise FileNotFoundError(f'Plan not found: {plan_id}')
    data = json.loads(path.read_text())
    return Plan.from_dict(data)


def _normalize_value(value: object) -> object:
    """Normalize a value for drift comparison.

    Sort lists to avoid false positives from ordering differences.
    """
    if isinstance(value, list):
        return sorted(value)
    return value


def _check_drift(provider: TicketProvider, plan: Plan) -> DriftResult:
    """Compare plan's recorded state against current ticket state.

    Critical drift: a field the plan is changing has a different current value
    than the plan's recorded before_value.

    Informational drift: a field the plan is NOT changing has changed since
    plan creation (requires ticket_snapshots on the plan).

    Deleted tickets are tracked separately and always block apply.
    """
    skip_fields = frozenset({'id', 'metadata', 'created_at'})
    result = DriftResult()

    # Collect which fields each ticket is changing
    changing_fields: defaultdict[str, set[str]] = defaultdict(set)
    for op in plan.operations:
        changing_fields[op.ticket_id].add(op.field)

    # Collect unique ticket IDs (preserve operation order for deterministic output)
    ticket_ids = list(dict.fromkeys(op.ticket_id for op in plan.operations))

    for ticket_id in ticket_ids:
        ticket = provider.read_ticket(ticket_id)
        if ticket is None:
            result.deleted_tickets.append(ticket_id)
            continue

        # Critical drift: check fields the plan is changing
        for op in plan.operations:
            if op.ticket_id != ticket_id:
                continue
            if not hasattr(ticket, op.field):
                continue
            current = _normalize_value(getattr(ticket, op.field))
            expected = _normalize_value(op.before_value)
            if current != expected:
                result.critical_drifts.append(
                    FieldDrift(
                        ticket_id=ticket_id,
                        field=op.field,
                        expected_value=op.before_value,
                        current_value=getattr(ticket, op.field),
                        updated_at=ticket.updated_at,
                    )
                )

        # Informational drift: check fields the plan is NOT changing
        if plan.ticket_snapshots and ticket_id in plan.ticket_snapshots:
            snapshot = plan.ticket_snapshots[ticket_id]
            snapshot_dict = snapshot.to_dict()
            ticket_dict = ticket.to_dict()
            changed_fields = changing_fields.get(ticket_id, set())
            for field_name in ticket_dict:
                if field_name in skip_fields:
                    continue
                # schema_version is a model version marker, not user data
                if field_name == 'schema_version':
                    continue
                if field_name in changed_fields:
                    continue
                current = _normalize_value(ticket_dict.get(field_name))
                expected = _normalize_value(snapshot_dict.get(field_name))
                if current != expected:
                    result.informational_drifts.append(
                        FieldDrift(
                            ticket_id=ticket_id,
                            field=field_name,
                            expected_value=snapshot_dict.get(field_name),
                            current_value=ticket_dict.get(field_name),
                            updated_at=ticket.updated_at,
                        )
                    )

    logger.debug(
        'Drift check: %d deleted, %d critical, %d informational',
        len(result.deleted_tickets),
        len(result.critical_drifts),
        len(result.informational_drifts),
    )
    return result


def _run_preflight(provider: TicketProvider, operations: list[Operation]) -> list[str]:
    """Validate operations against provider capabilities and ticket state.

    For each operation:
    1. Check provider capabilities support the field update.
    2. Verify the ticket exists.
    3. Overwrite before_value with the actual ticket value (LLM may hallucinate).

    Return a list of error strings. Empty list means all valid.
    """
    errors = provider.validate_operations(operations)
    if errors:
        return errors

    # Overwrite before_value with actual values (only if all validations passed)
    for op in operations:
        ticket = provider.read_ticket(op.ticket_id)
        # Safe: validate_operations already confirmed ticket exists and field is valid
        op.before_value = getattr(ticket, op.field)

    return errors


def _find_similar_plans(
    home: Path,
    instruction: str,
    limit: int = 3,
) -> list[Plan]:
    """Find past plans with instruction keyword overlap.

    Read from the JSONL index for scoring, then load full Plan JSON
    only for the top matches.
    """
    plans_dir = home / 'artifacts' / 'plans'
    entries = _load_plan_index(plans_dir)

    instruction_words = set(re.findall(r'\w+', instruction.lower()))
    if not instruction_words:
        return []

    scored: list[tuple[float, dict]] = []
    for entry in entries:
        plan_words = set(re.findall(r'\w+', entry['instruction'].lower()))
        overlap = len(instruction_words & plan_words)
        if overlap > 0:
            score = overlap / max(len(instruction_words), len(plan_words))
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_entries = scored[:limit]

    plans: list[Plan] = []
    for _, entry in top_entries:
        try:
            plan = load_plan(home, entry['plan_id'])
            plans.append(plan)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            continue
    return plans


def _rebuild_plan_index(plans_dir: Path) -> list[dict]:
    """Rebuild the JSONL index by scanning all plan JSON files.

    Write the rebuilt index and return the entries.
    """
    entries: list[dict] = []
    for path in sorted(plans_dir.glob('plan-*.json')):
        try:
            data = json.loads(path.read_text())
            entries.append(
                {
                    'plan_id': data['plan_id'],
                    'instruction': data['instruction'],
                    'created_at': data.get('created_at', ''),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    index_path = plans_dir / PLAN_INDEX_FILENAME
    with open(index_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')
    return entries


def _load_plan_index(plans_dir: Path) -> list[dict]:
    """Load the plan index from JSONL. Rebuild if missing."""
    index_path = plans_dir / PLAN_INDEX_FILENAME
    if not index_path.exists():
        if not plans_dir.exists():
            return []
        return _rebuild_plan_index(plans_dir)

    entries: list[dict] = []
    for line in index_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _resolve_operations(
    operations: list,
    resolutions: dict[tuple[str, str], DriftResolution],
) -> list:
    """Apply drift resolutions to operations.

    Return a list parallel to operations where:
    - KEEP_PLAN_VALUE: operation unchanged (use plan's after_value)
    - KEEP_CURRENT_VALUE: replaced with None (skip the change)
    - SKIP_OPERATION: replaced with None (caller marks as SKIPPED)
    """
    resolved = []
    for op in operations:
        key = (op.ticket_id, op.field)
        resolution = resolutions.get(key)
        if resolution is None:
            # No drift on this field, keep as-is
            resolved.append(op)
        elif resolution == DriftResolution.KEEP_PLAN_VALUE:
            resolved.append(op)
        elif resolution in (
            DriftResolution.KEEP_CURRENT_VALUE,
            DriftResolution.SKIP_OPERATION,
        ):
            resolved.append(None)
    return resolved
