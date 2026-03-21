from datetime import UTC, datetime
from pathlib import Path

from oppie.config import OppieConfig
from oppie.llm import LLMNotConfiguredError, create_llm_provider
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus, compute_plan_id
from oppie.plan.fallback import generate_plan_fallback
from oppie.plan.persistence import load_plan, save_plan
from oppie.plan.preflight import run_preflight
from oppie.plan.schema import PLAN_RESPONSE_SCHEMA, find_similar_plans, load_context
from oppie.prompts.plan import build_plan_prompt
from oppie.providers.local import LocalProvider


async def generate_plan(
    instruction: str,
    home: Path,
    config: OppieConfig | None = None,
) -> Plan:
    """Generate a plan from a user instruction.

    Pipeline:
    1. Load tickets from the local provider.
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
    provider = LocalProvider(home)
    try:
        tickets = provider.list_tickets()
        context = load_context(home)
        past_plans = find_similar_plans(home, instruction)

        # Try LLM path
        try:
            llm_config = config.llm if config else None
            llm = create_llm_provider(llm_config)
        except LLMNotConfiguredError:
            plan = generate_plan_fallback(instruction, provider)
            preflight_errors = run_preflight(plan.operations, provider)
            if preflight_errors:
                plan.status = PlanStatus.INVALID
                plan.risks.extend(preflight_errors)
            plan.plan_id = compute_plan_id(plan.operations)
            save_plan(plan, home)
            return plan

        messages = build_plan_prompt(instruction, context, tickets, past_plans)

        async with llm:
            response = await llm.generate(
                messages=messages,
                response_schema=PLAN_RESPONSE_SCHEMA,
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
        preflight_errors = run_preflight(operations, provider)
        status = PlanStatus.INVALID if preflight_errors else PlanStatus.SAVED
        if preflight_errors:
            risks.extend(preflight_errors)

        plan_id = compute_plan_id(operations)
        plan = Plan(
            plan_id=plan_id,
            instruction=instruction,
            operations=operations,
            risks=risks,
            created_at=datetime.now(UTC).isoformat(),
            status=status,
        )

        save_plan(plan, home)
        return plan
    finally:
        provider.close()


async def amend_plan(
    plan_id: str,
    home: Path,
    config: OppieConfig | None = None,
) -> Plan:
    """Load an existing plan and re-generate with current state.

    Set parent_plan_id to the original plan's ID.
    The new plan gets its own ID (content hash of new operations).
    """
    original = load_plan(plan_id, home)
    new_plan = await generate_plan(original.instruction, home, config)
    new_plan.parent_plan_id = plan_id
    # Re-save with parent_plan_id set
    save_plan(new_plan, home)
    return new_plan
