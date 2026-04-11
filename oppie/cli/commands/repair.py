import click

from oppie.cli.console import console, error, success, warn
from oppie.health import apply_repairs, scan_all


@click.command()
@click.option(
    '--dry-run',
    is_flag=True,
    default=False,
    help='Show what would be fixed without applying.',
)
@click.pass_context
def repair(ctx: click.Context, dry_run: bool) -> None:
    """Scan and repair instance data issues."""
    home = ctx.obj['resolved_home']

    issues, repair_ctx = scan_all(home)

    if not issues:
        console.print('[green]No issues found.[/green]')
        return

    fixable = [i for i in issues if i.fixable]
    unfixable = [i for i in issues if not i.fixable]

    console.print('[bold]Detected issues[/bold]')
    console.print()
    for issue in issues:
        marker = '[green]fixable[/green]' if issue.fixable else '[red]unfixable[/red]'
        console.print(f'  {issue.name}: {issue.description} ({marker})')
        if issue.detail:
            console.print(f'    [dim]{issue.detail}[/dim]')

    console.print()

    if unfixable:
        console.print('[bold]Unfixable issues require manual action:[/bold]')
        for issue in unfixable:
            warn(f'{issue.name}: {issue.detail or issue.description}')
        console.print()

    if not fixable:
        return

    if dry_run:
        console.print(f'[dim]Dry run: {len(fixable)} issue(s) would be repaired.[/dim]')
        return

    if not click.confirm(f'Repair {len(fixable)} issue(s)?', default=False):
        return

    results = apply_repairs(home, issues, repair_ctx)
    console.print()
    for result in results:
        if result.success:
            success(f'{result.name}: {result.message}')
        else:
            error(f'{result.name}: {result.message}')
