from __future__ import annotations

import logging
from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING

from oppie.cli.console import console as default_console
from oppie.cli.provider_setup import setup_provider
from oppie.events import (
    AskResultEvent,
    PlanOperationEvent,
    PlanResultEvent,
    StatsEvent,
    StepStartEvent,
    SyncDoneEvent,
    SyncStartEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator
    from pathlib import Path

    from rich.console import Console
    from rich.status import Status

    from oppie.ask.engine import AskResult
    from oppie.config import OppieConfig
    from oppie.events import EngineEvent
    from oppie.models.plan import Plan
    from oppie.providers.base import TicketProvider
    from oppie.sync import AutoSyncResult

logger = logging.getLogger(__name__)


class RenderMode(Enum):
    ASK = 'ask'
    PLAN = 'plan'


class EventRenderer:
    """Consume an EngineEvent stream and render it to a Rich console.

    Holds final domain results on `ask_result` / `plan` for callers to read
    after `consume()` completes.
    """

    def __init__(self, mode: RenderMode, console: Console | None = None) -> None:
        self.mode = mode
        self.console = console or default_console
        self.ask_result: AskResult | None = None
        self.plan: Plan | None = None
        self._thinking: Status | None = None
        self._sync_status: Status | None = None
        self._in_text = False
        self._operations_started = False

    async def consume(self, events: AsyncIterator[EngineEvent]) -> None:
        async for event in events:
            self._dispatch(event)
        self._stop_thinking()
        self._end_text_block()

    def _dispatch(self, event: EngineEvent) -> None:
        if isinstance(event, SyncStartEvent):
            self.on_sync_start(event)
        elif isinstance(event, SyncDoneEvent):
            self.on_sync_done(event)
        elif isinstance(event, StepStartEvent):
            self.on_step_start(event)
        elif isinstance(event, ThinkingEvent):
            self.on_thinking(event)
        elif isinstance(event, TextDeltaEvent):
            self.on_text_delta(event)
        elif isinstance(event, ToolCallEvent):
            self.on_tool_call(event)
        elif isinstance(event, PlanOperationEvent):
            self.on_plan_operation(event)
        elif isinstance(event, StatsEvent):
            self.on_stats(event)
        elif isinstance(event, AskResultEvent):
            self.on_ask_result(event)
        elif isinstance(event, PlanResultEvent):
            self.on_plan_result(event)

    def on_sync_start(self, event: SyncStartEvent) -> None:
        self._sync_status = self.console.status(
            f'Syncing from {event.provider}...', spinner='dots'
        )
        self._sync_status.start()

    def on_sync_done(self, event: SyncDoneEvent) -> None:
        if self._sync_status is not None:
            self._sync_status.stop()
            self._sync_status = None
        self.console.print(
            f'[green]\u2713[/green] Synced ({event.ticket_count} tickets, '
            f'{event.duration:.1f}s)'
        )

    def on_step_start(self, event: StepStartEvent) -> None:
        self._end_text_block()
        logger.debug('Render: step %s', event.step_name)

    def on_thinking(self, event: ThinkingEvent) -> None:
        if self._thinking is None:
            self._thinking = self.console.status('Thinking...', spinner='dots')
            self._thinking.start()

    def on_text_delta(self, event: TextDeltaEvent) -> None:
        self._stop_thinking()
        if not self._in_text:
            self.console.print()
            self._in_text = True
        self.console.print(event.text, end='', soft_wrap=True, highlight=False)

    def on_tool_call(self, event: ToolCallEvent) -> None:
        self._stop_thinking()
        self._end_text_block()
        self.console.print(f'[dim]\\[{event.tool_name}][/dim]')

    def on_plan_operation(self, event: PlanOperationEvent) -> None:
        self._stop_thinking()
        self._end_text_block()
        if not self._operations_started:
            self.console.print()
            self.console.print('[bold]Operations:[/bold]')
            self._operations_started = True
        op = event.operation
        self.console.print(
            f'  - {op.ticket_id}  {op.field}: {op.before_value} -> {op.after_value}'
        )
        self.console.print(f'    [dim]{op.rationale}[/dim]')

    def on_stats(self, event: StatsEvent) -> None:
        self._stop_thinking()
        self._end_text_block()
        total = event.usage.prompt_tokens + event.usage.completion_tokens
        self.console.print(
            f'[dim]* {total / 1000:.1f}k tokens \u00b7 '
            f'{event.turns} turns \u00b7 {event.duration:.1f}s[/dim]'
        )

    def on_ask_result(self, event: AskResultEvent) -> None:
        self.ask_result = event.result

    def on_plan_result(self, event: PlanResultEvent) -> None:
        self.plan = event.plan

    def _stop_thinking(self) -> None:
        if self._thinking is not None:
            self._thinking.stop()
            self._thinking = None

    def _end_text_block(self) -> None:
        if self._in_text:
            self.console.print()
            self._in_text = False


@contextmanager
def render_sync(
    renderer: EventRenderer,
    home: Path,
    config: OppieConfig,
    *,
    no_sync: bool,
) -> Iterator[tuple[TicketProvider, AutoSyncResult]]:
    """Wrap setup_provider, feeding sync events to the renderer.

    Suppresses setup_provider's success print line — the renderer narrates
    sync via on_sync_start / on_sync_done. Cached/error paths are still
    printed by setup_provider since they don't fit the SyncStart/Done model.
    """
    provider_name = config.provider.provider_type.value
    if not no_sync:
        renderer._dispatch(SyncStartEvent(provider=provider_name))
    with setup_provider(home, config, no_sync=no_sync, print_sync_success=False) as (
        provider,
        result,
    ):
        if result.synced:
            renderer._dispatch(
                SyncDoneEvent(
                    ticket_count=result.ticket_count, duration=result.duration
                )
            )
        elif renderer._sync_status is not None:
            renderer._sync_status.stop()
            renderer._sync_status = None
        yield provider, result
