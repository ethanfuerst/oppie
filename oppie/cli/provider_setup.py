from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from typing import TYPE_CHECKING

from oppie.cli.console import console, error, info, success, warn
from oppie.cli.extras import extras_available
from oppie.config import ProviderType
from oppie.providers.local import LocalProvider
from oppie.sync import AutoSyncResult, auto_sync

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from oppie.config import OppieConfig
    from oppie.providers.base import TicketProvider

logger = logging.getLogger(__name__)


@contextmanager
def setup_provider(
    home: Path,
    config: OppieConfig,
    *,
    no_sync: bool = False,
    print_sync_success: bool = True,
) -> Iterator[tuple[TicketProvider, AutoSyncResult]]:
    """Construct the configured provider, run auto-sync, yield (provider, result).

    Closes the provider (and its cache, for Linear) on exit. Set
    `print_sync_success=False` when the caller (e.g. the event renderer)
    will narrate sync success itself.
    """
    with ExitStack() as stack:
        provider = _build_provider(config, home, stack)
        sync_result = auto_sync(provider, no_sync=no_sync)
        _print_sync_status(
            sync_result, no_sync=no_sync, print_success=print_sync_success
        )
        yield provider, sync_result


def _build_provider(
    config: OppieConfig, home: Path, stack: ExitStack
) -> TicketProvider:
    ptype = config.provider.provider_type
    if ptype == ProviderType.LOCAL:
        provider = LocalProvider.setup(home)
        stack.callback(provider.close)
        return provider
    if ptype == ProviderType.LINEAR:
        return _build_linear_provider(config, home, stack)
    raise ValueError(f'Unsupported provider type: {ptype}')


def _build_linear_provider(
    config: OppieConfig, home: Path, stack: ExitStack
) -> TicketProvider:
    if not extras_available().get('linear'):
        error("Linear provider requires the 'linear' extra.")
        console.print(r"Install with: [bold]pip install 'oppie\[linear]'[/bold]")
        raise SystemExit(1)

    cache = LocalProvider(home)
    stack.callback(cache.close)

    from oppie.providers.factory import create_external_provider

    try:
        provider = create_external_provider(config, home, cache=cache)
    except ValueError as exc:
        warn(f'Linear provider unavailable ({exc}); using cached tickets.')
        logger.warning('Linear construction failed: %s', exc)
        return cache

    stack.callback(provider.close)
    return provider


def _print_sync_status(
    result: AutoSyncResult, *, no_sync: bool, print_success: bool = True
) -> None:
    if result.synced:
        if print_success:
            success(f'Synced ({result.ticket_count} tickets, {result.duration:.1f}s)')
    elif result.error:
        warn(
            f'Sync failed: {result.error} (using {result.ticket_count} cached tickets)'
        )
    elif no_sync:
        info(f'Using cached data ({result.ticket_count} tickets)')
