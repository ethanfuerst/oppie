from oppie.models.plan import Plan, PlanStatus


def make_and_save_plan(
    engine, operations, status=PlanStatus.SAVED, ticket_snapshots=None
):
    """Create a plan with correct plan_id and save it."""
    plan_id = Plan.compute_id(operations)
    plan = Plan(
        plan_id=plan_id,
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=status,
        ticket_snapshots=ticket_snapshots,
    )
    engine.save_plan(plan)
    return plan
