from oppie.models.plan import Plan, PlanStatus


def make_and_save_plan(
    home,
    operations,
    status=PlanStatus.SAVED,
    ticket_snapshots=None,
    checked=False,
):
    """Create a plan with auto-computed plan_id and save it."""
    plan = Plan(
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=status,
        ticket_snapshots=ticket_snapshots,
        checked=checked,
    )
    plan.save(home)
    return plan
