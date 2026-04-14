import click
from rich.table import Table

from oppie.cli.console import console, info
from oppie.run_log import RunLog


@click.command()
@click.option('--limit', '-n', default=6, help='Number of entries to show.')
@click.pass_context
def history(ctx: click.Context, limit: int) -> None:
    """Show recent run history."""
    home = ctx.obj['resolved_home']
    run_log = RunLog(home)

    all_entries = run_log.query()
    total = len(all_entries)
    entries = all_entries[-limit:] if limit < total else all_entries

    if not entries:
        info('No run history yet.')
        return

    console.print('[bold]Run history[/bold]')
    console.print()

    table = Table(show_header=True, header_style='bold', box=None, pad_edge=False)
    table.add_column('Run')
    table.add_column('Command')
    table.add_column('Date')
    table.add_column('Duration')
    table.add_column('Ref')

    for entry in entries:
        date = entry.timestamp[:10] if len(entry.timestamp) >= 10 else entry.timestamp
        ref_id = entry.plan_id or entry.apply_id or '-'
        table.add_row(
            entry.run_id[:8],
            entry.command,
            date,
            f'{entry.duration:.1f}s',
            ref_id,
        )

    console.print(table)

    console.print()
    if total > limit:
        console.print(
            f'[dim]Showing {len(entries)} of {total} entries. '
            f'Use --limit to see more.[/dim]'
        )
