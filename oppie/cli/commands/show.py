import json

import click

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.cli.console import console, error
from oppie.models.apply import ApplyResult, OperationStatus
from oppie.plan import load_plan


@click.command()
@click.argument('id')
@click.pass_context
def show(ctx: click.Context, id: str) -> None:
    """Show details of a plan or apply by ID."""
    home = ctx.obj['resolved_home']

    # Strip plan- prefix if present
    plan_id = id.removeprefix('plan-')

    # Try plan first
    try:
        plan = load_plan(home, plan_id)
        _display_plan(plan, home)
        return
    except FileNotFoundError:
        pass

    # Try apply artifacts
    apply_result = _find_apply(home, id)
    if apply_result:
        _display_apply(apply_result)
        return

    error(f'No plan or apply found for ID: {id}')
    console.print("Use 'oppie history' to see recent activity.")
    raise SystemExit(1)


def _find_apply(home, apply_id: str) -> ApplyResult | None:
    """Scan apply artifacts to find one matching apply_id."""
    store = ArtifactStore(home)
    for path in store.list_artifacts(ArtifactType.APPLY):
        content = store.read_artifact(path)
        data = json.loads(content)
        # Skip drift report artifacts
        if data.get('type') == 'drift_report':
            continue
        if data.get('apply_id') == apply_id:
            return ApplyResult.from_dict(data)
    return None


def _display_plan(plan, home) -> None:
    """Render plan details to console."""
    console.print(f'[bold]Plan {plan.plan_id}[/bold]')
    console.print()
    console.print(f'  Status:      {plan.status.value}')
    console.print(f'  Created:     {plan.created_at}')
    console.print(f'  Instruction: {plan.instruction}')
    console.print()

    if plan.risks:
        console.print('[bold]Risks[/bold]')
        for risk in plan.risks:
            console.print(f'  - {risk}')
        console.print()

    console.print(f'[bold]Operations ({len(plan.operations)})[/bold]')
    console.print()
    for i, op in enumerate(plan.operations, 1):
        console.print(
            f'  {i}. {op.ticket_id}  {op.field}: {op.before_value} -> {op.after_value}'
        )
        if op.rationale:
            console.print(f'     {op.rationale}')
    console.print()

    artifact_path = home / 'artifacts' / 'plans' / f'plan-{plan.plan_id}.json'
    console.print(f'[dim]Artifact: {artifact_path}[/dim]')


def _display_apply(result: ApplyResult) -> None:
    """Render apply result details to console."""
    total = len(result.results)
    ok_count = sum(1 for r in result.results if r.status == OperationStatus.OK)
    fail_count = sum(1 for r in result.results if r.status == OperationStatus.FAILED)

    if fail_count > 0:
        status = 'partial'
    elif ok_count == total:
        status = 'success'
    else:
        status = 'skipped'

    console.print(f'[bold]Apply {result.apply_id}[/bold]')
    console.print()
    console.print(f'  Plan:     {result.plan_id}')
    console.print(f'  Status:   {status}')
    console.print(f'  Applied:  {result.created_at}')
    console.print(f'  Duration: {result.duration:.1f}s')
    console.print()

    console.print(f'[bold]Results ({total})[/bold]')
    console.print()
    for i, r in enumerate(result.results, 1):
        op = r.operation
        if r.status == OperationStatus.OK:
            console.print(f'  {i}. {op.ticket_id}  {op.field}  [green]ok[/green]')
        elif r.status == OperationStatus.FAILED:
            console.print(f'  {i}. {op.ticket_id}  {op.field}  [red]FAILED[/red]')
            if r.error:
                console.print(f'     Error: {r.error}')
        elif r.status == OperationStatus.SKIPPED:
            console.print(f'  {i}. {op.ticket_id}  {op.field}  [dim]skipped[/dim]')
    console.print()
