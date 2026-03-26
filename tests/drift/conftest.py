from oppie.models.plan import Plan, PlanStatus


def make_plan(operations, ticket_snapshots=None):
    return Plan(
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
        ticket_snapshots=ticket_snapshots,
    )
