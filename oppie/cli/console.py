from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

    from oppie.providers.base import TicketProvider
    from oppie.sync import AutoSyncResult

console = Console()


def success(msg: str) -> None:
    """Print a success message with green checkmark."""
    console.print(f'[green]\u2713[/green] {msg}')


def warn(msg: str) -> None:
    """Print a warning message with yellow marker."""
    console.print(f'[yellow]\u26a0[/yellow] {msg}')


def error(msg: str) -> None:
    """Print an error message with red marker."""
    console.print(f'[red]\u2717[/red] {msg}')


def info(msg: str) -> None:
    """Print an info message with blue marker."""
    console.print(f'[blue]\u25cf[/blue] {msg}')


def setup_provider(
    home: Path, *, no_sync: bool = False
) -> tuple[TicketProvider, AutoSyncResult]:
    """Create a provider and run auto-sync, displaying results.

    Returns the provider and sync result for use by the calling command.
    """
    from oppie.providers.local import LocalProvider
    from oppie.sync import auto_sync

    provider = LocalProvider.setup(home)
    sync_result = auto_sync(provider, no_sync=no_sync)
    if sync_result.synced:
        success(
            f'Synced ({sync_result.ticket_count} tickets, {sync_result.duration:.1f}s)'
        )
    elif sync_result.error:
        warn(
            f'Sync failed: {sync_result.error} '
            f'(using {sync_result.ticket_count} cached tickets)'
        )
    elif no_sync:
        info(f'Using cached data ({sync_result.ticket_count} tickets)')
    return provider, sync_result
