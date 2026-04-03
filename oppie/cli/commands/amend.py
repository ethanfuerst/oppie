import asyncio
import logging

import click

from oppie.cli.console import console, error, info, setup_provider, warn
from oppie.models.plan import PlanStatus
from oppie.plan import amend_plan, load_plan
from oppie.session import Session

logger = logging.getLogger(__name__)


@click.command()
@click.argument('plan_id')
@click.pass_context
def amend(ctx: click.Context, plan_id: str) -> None:
    """Re-generate an existing plan with current ticket state."""
    home = ctx.obj['resolved_home']
    config = ctx.obj['config']
    no_sync = ctx.obj.get('no_sync', False)

    # Load original plan
    info(f'Loading plan {plan_id}...')
    try:
        original = load_plan(home, plan_id)
    except FileNotFoundError:
        error(f'Plan not found: {plan_id}')
        raise SystemExit(1) from None

    if original.status == PlanStatus.APPLIED:
        warn(f'{plan_id} was already applied.')
        console.print('Amending will generate a new plan based on current state.')
        if not click.confirm('Continue?', default=False):
            raise SystemExit(0)

    provider, _ = setup_provider(home, no_sync=no_sync)

    # Amend
    info('Re-generating plan with current ticket state...')
    new_plan = asyncio.run(amend_plan(provider, config, plan_id))

    console.print()
    console.print(f'Amended plan (based on {plan_id}):')
    console.print()

    # Show operations summary
    for i, op in enumerate(new_plan.operations, 1):
        console.print(
            f'  {i}. {op.ticket_id}  {op.field}: {op.before_value} -> {op.after_value}'
        )
        console.print(f'     Rationale: {op.rationale}')
    console.print()

    # Interactive save
    save = click.confirm('Save this plan?', default=False)
    if not save:
        console.print('Plan discarded.')
        return

    console.print(f'Plan saved: [bold]{new_plan.plan_id}[/bold] (amends {plan_id})')
    console.print(f'Next: [bold]apply {new_plan.plan_id}[/bold]')

    # Update session
    session = Session.load_latest(home) or Session.create(home)
    session.set_active_plan(new_plan.plan_id)
