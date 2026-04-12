import logging
import time

import click

from oppie.cli.console import console, error, info, success, warn
from oppie.cli.extras import extras_available
from oppie.config import ProviderType
from oppie.models.apply import OperationStatus

logger = logging.getLogger(__name__)


@click.command('sync')
@click.option(
    '--full',
    is_flag=True,
    default=False,
    help='Full resync, ignore saved checkpoint.',
)
@click.option(
    '--no-flush',
    is_flag=True,
    default=False,
    help='Skip outbox flush before pulling.',
)
@click.pass_context
def sync(ctx: click.Context, full: bool, no_flush: bool) -> None:
    """Sync tickets with the configured external provider.

    On first run (no saved checkpoint) incremental sync behaves like a full
    sync; --full is a no-op in that case. If Linear rate-limits mid-pagination,
    some tickets may have been upserted but the checkpoint is not advanced —
    rerun to resume.
    """
    home = ctx.obj['resolved_home']
    config = ctx.obj['config']

    if config.provider.provider_type != ProviderType.LINEAR:
        info('Nothing to sync — this is a local instance.')
        return

    if not extras_available().get('linear'):
        error('Linear extra is not installed.')
        console.print(r"Install with: [bold]pip install 'oppie\[linear]'[/bold]")
        raise SystemExit(1)

    # Deferred imports: only after extras check so missing httpx doesn't crash.
    import httpx

    from oppie.providers.factory import create_external_provider
    from oppie.providers.linear.provider import (
        LinearAPIError,
        LinearAuthError,
        LinearRateLimitError,
    )
    from oppie.providers.local import LocalProvider

    cache = LocalProvider(home)
    provider = create_external_provider(config, home=home, cache=cache)

    try:
        if not no_flush:
            _flush(provider)

        _pull(provider, full=full)
    except LinearAuthError as exc:
        error(f'Authentication failed: {exc}')
        console.print('Run [bold]oppie config[/bold] to update your Linear API key.')
        raise SystemExit(2) from None
    except LinearRateLimitError as exc:
        retry = f' Retry after {exc.retry_after:.0f}s.' if exc.retry_after else ''
        error(f'Rate limited by Linear.{retry}')
        raise SystemExit(3) from None
    except httpx.HTTPError as exc:
        error(f'Network error: {exc}')
        raise SystemExit(4) from None
    except LinearAPIError as exc:
        error(f'Linear error: {exc}')
        raise SystemExit(5) from None
    finally:
        provider.close()


def _flush(provider) -> None:
    results = provider.flush_outbox()
    if not results:
        return
    failed = sum(1 for r in results if r.status != OperationStatus.OK)
    ok = len(results) - failed
    if failed:
        warn(f'Flushed outbox: {ok} ok, {failed} failed (kept in outbox).')
    else:
        success(f'Flushed outbox: {ok} operations.')


def _pull(provider, *, full: bool) -> None:
    checkpoint = '' if full else None
    start = time.monotonic()
    result = provider.sync(checkpoint=checkpoint)
    duration = time.monotonic() - start
    label = 'Full sync' if full else 'Sync'
    success(f'{label} complete: {result.tickets_upserted} tickets in {duration:.1f}s.')
    if result.errors:
        for err in result.errors:
            warn(err)
