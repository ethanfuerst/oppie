import json
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.config import OppieConfig
from oppie.llm import LLMNotConfiguredError, create_llm_provider
from oppie.models.apply import ApplyResult, OperationResult, OperationStatus
from oppie.models.drift import DriftResolution, DriftResult, FieldDrift
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.models.ticket import Ticket
from oppie.providers.base import TicketProvider
from oppie.run_log import RunLog, RunLogEntry, generate_run_id


@dataclass
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


_STATUS_KEYWORDS: dict[str, str] = {
    'close': 'done',
    'finish': 'done',
    'complete': 'done',
    'done': 'done',
    'reopen': 'open',
    'open': 'open',
    'start': 'in_progress',
    'begin': 'in_progress',
    'block': 'blocked',
}

_PRIORITY_KEYWORDS: dict[str, str] = {
    'prioritize': 'high',
    'urgent': 'high',
    'critical': 'high',
    'deprioritize': 'low',
}


class PlanEngine:
    """Orchestrates the plan lifecycle: generate, amend, check, and apply."""

    PLAN_INDEX_FILENAME = '.plan-index.jsonl'

    PLAN_RESPONSE_SCHEMA: dict = {
        'type': 'object',
        'properties': {
            'operations': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'ticket_id': {'type': 'string'},
                        'field': {'type': 'string'},
                        'before_value': {},
                        'after_value': {},
                        'rationale': {'type': 'string'},
                    },
                    'required': [
                        'ticket_id',
                        'field',
                        'before_value',
                        'after_value',
                        'rationale',
                    ],
                },
            },
            'risks': {
                'type': 'array',
                'items': {'type': 'string'},
            },
        },
        'required': ['operations', 'risks'],
    }

    def __init__(
        self,
        home: Path,
        provider: TicketProvider,
        config: OppieConfig | None = None,
    ) -> None:
        self._home = home
        self._provider = provider
        self._config = config

    # --- Public methods ---

    async def generate(self, instruction: str) -> Plan:
        """Generate a plan from a user instruction.

        Pipeline:
        1. Load tickets from the provider.
        2. Load context docs (vision, roadmap, etc.) if present.
        3. Find similar past plans (up to 3) for few-shot context.
        4. Build LLM prompt and call LLM with structured output.
           - If no LLM configured, fall back to keyword matching.
        5. Parse LLM response into Operation objects.
        6. Run preflight validation (capabilities + ticket existence).
        7. Compute plan_id from content hash.
        8. Save plan as JSON artifact.
        9. Return the Plan.
        """
        tickets = self._provider.list_tickets()
        ticket_snapshots = {t.id: t for t in tickets}
        context = self._load_context()
        past_plans = self._find_similar_plans(instruction)

        # Try LLM path
        try:
            llm_config = self._config.llm if self._config else None
            llm = create_llm_provider(llm_config)
        except LLMNotConfiguredError:
            plan = self._generate_fallback(instruction)
            preflight_errors = self._run_preflight(plan.operations)
            if preflight_errors:
                plan.status = PlanStatus.INVALID
                plan.risks.extend(preflight_errors)
            plan.plan_id = Plan.compute_id(plan.operations)
            plan.ticket_snapshots = ticket_snapshots
            self.save_plan(plan)
            return plan

        messages = self._build_prompt(instruction, context, tickets, past_plans)

        async with llm:
            response = await llm.generate(
                messages=messages,
                response_schema=self.PLAN_RESPONSE_SCHEMA,
                max_tokens=llm_config.max_tokens if llm_config else 2000,
                temperature=llm_config.temperature if llm_config else 0.7,
            )

        if response.json is None:
            raise ValueError('LLM returned no structured output')

        # Parse operations
        raw_ops = response.json.get('operations', [])
        operations = [
            Operation(
                ticket_id=op['ticket_id'],
                field=op['field'],
                before_value=op.get('before_value'),
                after_value=op.get('after_value'),
                rationale=op.get('rationale', ''),
            )
            for op in raw_ops
        ]
        risks = response.json.get('risks', [])

        # Preflight validation
        preflight_errors = self._run_preflight(operations)
        status = PlanStatus.INVALID if preflight_errors else PlanStatus.SAVED
        if preflight_errors:
            risks.extend(preflight_errors)

        plan_id = Plan.compute_id(operations)
        plan = Plan(
            plan_id=plan_id,
            instruction=instruction,
            operations=operations,
            risks=risks,
            created_at=datetime.now(UTC).isoformat(),
            status=status,
            ticket_snapshots=ticket_snapshots,
        )

        self.save_plan(plan)
        return plan

    async def amend(self, plan_id: str) -> Plan:
        """Load an existing plan and re-generate with current state.

        Set parent_plan_id to the original plan's ID.
        The new plan gets its own ID (content hash of new operations).
        """
        original = self.load_plan(plan_id)
        new_plan = await self.generate(original.instruction)
        new_plan.parent_plan_id = plan_id
        # Re-save with parent_plan_id set
        self.save_plan(new_plan)
        return new_plan

    def check_apply(self, plan_id: str) -> PreApplyCheck:
        """Run all pre-apply validations: integrity, already-applied, drift, capabilities.

        Return a PreApplyCheck with results for the UI layer to inspect.
        """
        plan = self.load_plan(plan_id)

        # Integrity check
        recomputed = Plan.compute_id(plan.operations)
        integrity_ok = recomputed == plan.plan_id

        # Already applied check
        already_applied = plan.status == PlanStatus.APPLIED

        # Drift check
        drift = self._check_drift(plan)

        # Capability re-check
        capability_errors = self._provider.validate_operations(plan.operations)

        return PreApplyCheck(
            plan=plan,
            integrity_ok=integrity_ok,
            already_applied=already_applied,
            drift=drift,
            capability_errors=capability_errors,
        )

    def execute_apply(
        self,
        plan_id: str,
        force: bool = False,
        resolutions: dict[tuple[str, str], DriftResolution] | None = None,
    ) -> ApplyResult:
        """Execute a plan's operations against the provider.

        Assumes check_apply() was called first. Re-validates integrity and drift
        as a safety net. Executes operations sequentially, stops on first failure.
        """
        plan = self.load_plan(plan_id)

        # Safety checks (re-validate even though check_apply should have been called)
        recomputed = Plan.compute_id(plan.operations)
        if recomputed != plan.plan_id:
            raise ValueError(
                f'Plan integrity check failed: expected {plan.plan_id}, '
                f'got {recomputed}'
            )

        if plan.status == PlanStatus.APPLIED:
            raise ValueError(f'Plan {plan_id} has already been applied')

        # Drift check
        drift = self._check_drift(plan)

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
            effective_ops = self._resolve_operations(plan.operations, resolutions)

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
                self._provider.update_ticket(op.ticket_id, {op.field: op.after_value})
                results.append(OperationResult(operation=op, status=OperationStatus.OK))
            except Exception as e:
                results.append(
                    OperationResult(
                        operation=op,
                        status=OperationStatus.FAILED,
                        error=str(e),
                    )
                )
                failed = True

        duration = time.monotonic() - start_time
        created_at = datetime.now(UTC).isoformat()

        apply_result = ApplyResult(
            apply_id=apply_id,
            plan=plan,
            results=results,
            duration=duration,
            created_at=created_at,
        )

        # Mark plan as applied
        plan.status = PlanStatus.APPLIED
        self.save_plan(plan)

        # Write apply artifact
        artifact_store = ArtifactStore(self._home)
        run_id = generate_run_id()
        artifact_content = apply_result.build_artifact()
        artifact_path = artifact_store.save_artifact(
            ArtifactType.APPLY, artifact_content, run_id
        )

        # Append run log
        run_log = RunLog(self._home)
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

    def save_plan(self, plan: Plan) -> Path:
        """Save plan as JSON to artifacts/plans/plan-{plan_id}.json.

        Use atomic write (temp file + rename).
        Return the path to the saved JSON file.
        """
        plans_dir = self._home / 'artifacts' / 'plans'
        plans_dir.mkdir(parents=True, exist_ok=True)
        target = plans_dir / f'plan-{plan.plan_id}.json'

        fd, tmp_path = tempfile.mkstemp(dir=plans_dir, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                json.dump(plan.to_dict(), f, indent=2)
                f.write('\n')
            Path(tmp_path).replace(target)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        self._append_plan_index(plans_dir, plan)
        return target

    def load_plan(self, plan_id: str) -> Plan:
        """Load a plan by ID from artifacts/plans/plan-{plan_id}.json.

        Raise FileNotFoundError if not found.
        """
        path = self._home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
        if not path.exists():
            raise FileNotFoundError(f'Plan not found: {plan_id}')
        data = json.loads(path.read_text())
        return Plan.from_dict(data)

    @staticmethod
    def _normalize_value(value: object) -> object:
        """Normalize a value for drift comparison.

        Sort lists to avoid false positives from ordering differences.
        """
        if isinstance(value, list):
            return sorted(value)
        return value

    def _check_drift(self, plan: Plan) -> DriftResult:
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
        changing_fields: dict[str, set[str]] = {}
        for op in plan.operations:
            changing_fields.setdefault(op.ticket_id, set()).add(op.field)

        # Collect unique ticket IDs (preserve operation order for deterministic output)
        seen_tickets: set[str] = set()
        ticket_ids: list[str] = []
        for op in plan.operations:
            if op.ticket_id not in seen_tickets:
                seen_tickets.add(op.ticket_id)
                ticket_ids.append(op.ticket_id)

        for ticket_id in ticket_ids:
            ticket = self._provider.read_ticket(ticket_id)
            if ticket is None:
                result.deleted_tickets.append(ticket_id)
                continue

            # Critical drift: check fields the plan is changing
            for op in plan.operations:
                if op.ticket_id != ticket_id:
                    continue
                if not hasattr(ticket, op.field):
                    continue
                current = self._normalize_value(getattr(ticket, op.field))
                expected = self._normalize_value(op.before_value)
                if current != expected:
                    result.critical_drifts.append(
                        FieldDrift(
                            ticket_id=ticket_id,
                            field=op.field,
                            expected_value=op.before_value,
                            current_value=getattr(ticket, op.field),
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
                    if field_name == 'schema_version':
                        continue
                    if field_name in changed_fields:
                        continue
                    current = self._normalize_value(ticket_dict.get(field_name))
                    expected = self._normalize_value(snapshot_dict.get(field_name))
                    if current != expected:
                        result.informational_drifts.append(
                            FieldDrift(
                                ticket_id=ticket_id,
                                field=field_name,
                                expected_value=snapshot_dict.get(field_name),
                                current_value=ticket_dict.get(field_name),
                            )
                        )

        return result

    def _run_preflight(self, operations: list[Operation]) -> list[str]:
        """Validate operations against provider capabilities and ticket state.

        For each operation:
        1. Check provider capabilities support the field update.
        2. Verify the ticket exists.
        3. Overwrite before_value with the actual ticket value (LLM may hallucinate).

        Return a list of error strings. Empty list means all valid.
        """
        errors = self._provider.validate_operations(operations)
        if errors:
            return errors

        # Overwrite before_value with actual values (only if all validations passed)
        for op in operations:
            ticket = self._provider.read_ticket(op.ticket_id)
            # Safe: validate_operations already confirmed ticket exists and field is valid
            op.before_value = getattr(ticket, op.field)

        return errors

    def _load_context(self) -> dict[str, str]:
        """Read optional context docs from {home}/context/.

        Return a dict of filename stem -> content for each .md file that exists.
        Known files: vision.md, roadmap.md, metrics.md, prioritization.md.
        """
        context_dir = self._home / 'context'
        if not context_dir.is_dir():
            return {}
        context = {}
        for name in ('vision', 'roadmap', 'metrics', 'prioritization'):
            path = context_dir / f'{name}.md'
            if path.exists():
                content = path.read_text().strip()
                if content:
                    context[name] = content
        return context

    def _find_similar_plans(
        self,
        instruction: str,
        limit: int = 3,
    ) -> list[Plan]:
        """Find past plans with instruction keyword overlap.

        Read from the JSONL index for scoring, then load full Plan JSON
        only for the top matches.
        """
        plans_dir = self._home / 'artifacts' / 'plans'
        entries = self._load_plan_index(plans_dir)

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
                plan = self.load_plan(entry['plan_id'])
                plans.append(plan)
            except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
                continue
        return plans

    def _generate_fallback(self, instruction: str) -> Plan:
        """Generate a plan without LLM using keyword matching.

        Parse instruction for status/priority keywords, filter tickets,
        and generate simple field-change operations.
        """
        words = set(re.findall(r'\w+', instruction.lower()))
        operations: list[Operation] = []
        tickets = self._provider.list_tickets()

        # Determine target status change
        target_status: str | None = None
        for keyword, status in _STATUS_KEYWORDS.items():
            if keyword in words:
                target_status = status
                break

        # Determine target priority change
        target_priority: str | None = None
        for keyword, priority in _PRIORITY_KEYWORDS.items():
            if keyword in words:
                target_priority = priority
                break

        # Filter tickets by label keywords (any label word appearing in instruction)
        matching_tickets = tickets
        label_words = words - set(_STATUS_KEYWORDS) - set(_PRIORITY_KEYWORDS)
        if label_words:
            matching_tickets = [
                t
                for t in tickets
                if any(lw in label.lower() for lw in label_words for label in t.labels)
                or any(lw in t.title.lower() for lw in label_words)
            ]
            # Fall back to all tickets if no label match
            if not matching_tickets:
                matching_tickets = tickets

        for ticket in matching_tickets:
            if target_status and ticket.status != target_status:
                operations.append(
                    Operation(
                        ticket_id=ticket.id,
                        field='status',
                        before_value=ticket.status,
                        after_value=target_status,
                        rationale=f'Keyword match: set status to {target_status}',
                    )
                )
            if target_priority and ticket.priority != target_priority:
                operations.append(
                    Operation(
                        ticket_id=ticket.id,
                        field='priority',
                        before_value=ticket.priority,
                        after_value=target_priority,
                        rationale=f'Keyword match: set priority to {target_priority}',
                    )
                )

        plan_id = Plan.compute_id(operations)
        return Plan(
            plan_id=plan_id,
            instruction=instruction,
            operations=operations,
            risks=['Generated without LLM — operations based on keyword matching only'],
            created_at=datetime.now(UTC).isoformat(),
            status=PlanStatus.SAVED,
        )

    @staticmethod
    def _append_plan_index(plans_dir: Path, plan: Plan) -> None:
        """Append a plan entry to the JSONL index."""
        entry = {
            'plan_id': plan.plan_id,
            'instruction': plan.instruction,
            'created_at': plan.created_at,
        }
        index_path = plans_dir / PlanEngine.PLAN_INDEX_FILENAME
        with open(index_path, 'a') as f:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')

    @staticmethod
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

        index_path = plans_dir / PlanEngine.PLAN_INDEX_FILENAME
        with open(index_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry, separators=(',', ':')) + '\n')
        return entries

    @staticmethod
    def _load_plan_index(plans_dir: Path) -> list[dict]:
        """Load the plan index from JSONL. Rebuild if missing."""
        index_path = plans_dir / PlanEngine.PLAN_INDEX_FILENAME
        if not index_path.exists():
            if not plans_dir.exists():
                return []
            return PlanEngine._rebuild_plan_index(plans_dir)

        entries: list[dict] = []
        for line in index_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return entries

    @staticmethod
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

    _SYSTEM_PROMPT = """\
You are oppie, a ticket operations bot that uses a plan/apply workflow.
You receive a set of tickets and a user instruction, then generate a plan \
consisting of explicit field-level operations on those tickets.

Rules:
- Each operation targets exactly one ticket and one field.
- Include before_value (current) and after_value (proposed) for every operation.
- Include a short rationale for each operation.
- Identify risks or concerns with the proposed changes.
- Only propose operations that are actionable — do not suggest vague changes.
- If the instruction is ambiguous, propose the most conservative interpretation.\
"""

    @staticmethod
    def _format_tickets(tickets: list[Ticket]) -> str:
        """Format tickets as a compact text block for the LLM prompt."""
        if not tickets:
            return '(no tickets)'
        lines = []
        for t in tickets:
            labels = ', '.join(t.labels) if t.labels else 'none'
            lines.append(
                f'- [{t.id}] {t.title} | status={t.status} priority={t.priority} '
                f'owner={t.owner or "unassigned"} labels={labels}'
            )
        return '\n'.join(lines)

    @staticmethod
    def _format_past_plans(plans: list[Plan]) -> str:
        """Format past similar plans as context for the LLM."""
        if not plans:
            return '(no similar past plans)'
        parts = []
        for p in plans:
            ops_summary = '; '.join(
                f'{op.ticket_id}.{op.field}: {op.before_value!r} -> {op.after_value!r}'
                for op in p.operations
            )
            parts.append(f'- Plan {p.plan_id}: "{p.instruction}" -> [{ops_summary}]')
        return '\n'.join(parts)

    @staticmethod
    def _format_context(context: dict[str, str]) -> str:
        """Format context docs (vision, roadmap, etc.) for the prompt."""
        if not context:
            return ''
        parts = []
        for name, content in context.items():
            parts.append(f'## {name.replace("_", " ").title()}\n{content}')
        return '\n\n'.join(parts)

    def _build_prompt(
        self,
        instruction: str,
        context: dict[str, str],
        tickets: list[Ticket],
        past_plans: list[Plan],
    ) -> list[dict]:
        """Build OpenAI-format messages for plan generation."""
        context_section = self._format_context(context)
        context_block = f'\n# Context\n{context_section}\n' if context_section else ''

        user_content = f"""\
{context_block}
# Current tickets
{self._format_tickets(tickets)}

# Past similar plans
{self._format_past_plans(past_plans)}

# User instruction
{instruction}

Generate a plan with explicit operations (ticket_id, field, before_value, \
after_value, rationale) and a list of risks.\
"""

        return [
            {'role': 'system', 'content': self._SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ]
