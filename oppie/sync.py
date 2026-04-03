import logging
import time
from dataclasses import dataclass

from oppie.providers.base import ExternalProvider, TicketProvider

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AutoSyncResult:
    """Result of auto_sync attempt."""

    synced: bool
    ticket_count: int
    duration: float
    error: str | None = None


def auto_sync(provider: TicketProvider, *, no_sync: bool = False) -> AutoSyncResult:
    """Run auto-sync if provider supports it.

    - If no_sync=True, skip sync entirely.
    - If provider is not an ExternalProvider, skip (local-only mode).
    - On sync failure, warn and continue with cached data.
    """
    if no_sync:
        ticket_count = len(provider.list_tickets())
        logger.debug('Sync skipped (--no-sync), %d cached tickets', ticket_count)
        return AutoSyncResult(synced=False, ticket_count=ticket_count, duration=0.0)

    if not isinstance(provider, ExternalProvider):
        ticket_count = len(provider.list_tickets())
        return AutoSyncResult(synced=False, ticket_count=ticket_count, duration=0.0)

    start = time.monotonic()
    try:
        provider.sync()
        duration = time.monotonic() - start
        ticket_count = len(provider.list_tickets())
        logger.info('Sync complete: %d tickets in %.1fs', ticket_count, duration)
        return AutoSyncResult(synced=True, ticket_count=ticket_count, duration=duration)
    except Exception as exc:
        duration = time.monotonic() - start
        ticket_count = len(provider.list_tickets())
        logger.warning(
            'Sync failed: %s (continuing with %d cached tickets)', exc, ticket_count
        )
        return AutoSyncResult(
            synced=False,
            ticket_count=ticket_count,
            duration=duration,
            error=str(exc),
        )
