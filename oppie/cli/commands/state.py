from pathlib import Path

import click

from oppie.cli.console import console
from oppie.models.plan import PLAN_INDEX_FILENAME
from oppie.run_log import RunLog


@click.group()
def state() -> None:
    """Inspect instance state."""


@state.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Show instance state summary."""
    home = ctx.obj['resolved_home']
    instance = ctx.obj['instance']
    config = ctx.obj.get('config')

    console.print('[bold]Instance[/bold]')
    console.print()
    console.print(f'  Path:     {home}')
    console.print(f'  Type:     {instance.marker.instance_type.value}')
    if config:
        console.print(f'  Provider: {config.provider.provider_type.value}')
    console.print()

    # Ticket count
    tickets_dir = home / 'tickets'
    ticket_count = _count_files(tickets_dir, suffix='.json')
    console.print(f'  Tickets:  {ticket_count}')

    # Plan count (exclude .plan-index.jsonl)
    plans_dir = home / 'artifacts' / 'plans'
    plan_count = _count_files(plans_dir, suffix='.json', exclude={PLAN_INDEX_FILENAME})
    console.print(f'  Plans:    {plan_count}')

    # Apply count
    applies_dir = home / 'artifacts' / 'applies'
    apply_count = _count_files(applies_dir, suffix='.json')
    console.print(f'  Applies:  {apply_count}')

    # Ask count
    ask_dir = home / 'artifacts' / 'ask'
    ask_count = _count_files(ask_dir, suffix='.json')
    console.print(f'  Asks:     {ask_count}')

    # Run log entries
    run_log = RunLog(home)
    entries = run_log.query()
    console.print(f'  Runs:     {len(entries)}')

    # Log size
    logs_dir = home / 'logs'
    log_size = _dir_size(logs_dir)
    console.print(f'  Log size: {_format_size(log_size)}')
    console.print()


def _count_files(
    directory: Path,
    *,
    suffix: str = '',
    exclude: set[str] | None = None,
) -> int:
    """Count files in directory, optionally filtering by suffix and excluding names."""
    if not directory.exists():
        return 0
    exclude = exclude or set()
    return sum(
        1
        for p in directory.iterdir()
        if p.is_file() and p.name not in exclude and (not suffix or p.suffix == suffix)
    )


def _dir_size(directory: Path) -> int:
    """Sum file sizes in a directory (non-recursive)."""
    if not directory.exists():
        return 0
    return sum(p.stat().st_size for p in directory.iterdir() if p.is_file())


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if size_bytes < 1024:
        return f'{size_bytes} B'
    elif size_bytes < 1024 * 1024:
        return f'{size_bytes / 1024:.1f} KB'
    else:
        return f'{size_bytes / (1024 * 1024):.1f} MB'
