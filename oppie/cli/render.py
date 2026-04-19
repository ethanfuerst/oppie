from __future__ import annotations

import asyncio
import logging
import time
from contextlib import contextmanager, suppress
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

_IDLE_WARNING_SECONDS = 30
_TOOL_INPUT_SUMMARY_MAX = 40


class RenderMode(Enum):
    ASK = 'ask'
    PLAN = 'plan'


def _summarize_tool_input(tool_input: dict) -> str:
    """Render a dict as 'k1="v1", k2=...' capped at 40 chars, no newlines."""
    if not tool_input:
        return ''
    parts: list[str] = []
    for key, value in tool_input.items():
        rendered = f'{key}="{value}"' if isinstance(value, str) else f'{key}={value!r}'
        parts.append(rendered.replace('\n', ' ').replace('\r', ' '))
    joined = ', '.join(parts)
    if len(joined) > _TOOL_INPUT_SUMMARY_MAX:
        joined = joined[: _TOOL_INPUT_SUMMARY_MAX - 1] + '…'
    return joined


class _SpinnerController:
    """Owns the live Thinking/Calling-tool spinner and elapsed-time task.

    State transitions:
      set_step(name)        — remember step name; does not touch Status.
      show_thinking()       — reset phase timer, enter Thinking mode,
                              start Status + tick task if needed.
      show_tool_call(n, i)  — reset phase timer, enter tool mode,
                              start Status + tick task if needed.
      stop()                — cancel tick task, stop Status. Synchronous.
      aclose()              — awaits the cancelled tick task. Call from
                              consume()'s finally block.
    """

    def __init__(self, console: Console) -> None:
        self._console = console
        self._status: Status | None = None
        self._tick_task: asyncio.Task | None = None
        self._phase_start: float = 0.0
        self._step_name: str | None = None
        self._tool_name: str | None = None
        self._tool_input_summary: str = ''

    @property
    def is_active(self) -> bool:
        return self._status is not None

    def set_step(self, step_name: str) -> None:
        self._step_name = step_name

    def show_thinking(self) -> None:
        self._tool_name = None
        self._tool_input_summary = ''
        self._phase_start = time.monotonic()
        self._ensure_status_and_task()

    def show_tool_call(self, tool_name: str, tool_input: dict) -> None:
        self._tool_name = tool_name
        self._tool_input_summary = _summarize_tool_input(tool_input)
        self._phase_start = time.monotonic()
        self._ensure_status_and_task()

    def stop(self) -> None:
        if self._tick_task is not None:
            self._tick_task.cancel()
            self._tick_task = None
        if self._status is not None:
            self._status.stop()
            self._status = None
        self._tool_name = None
        self._tool_input_summary = ''

    async def aclose(self) -> None:
        task = self._tick_task
        self.stop()
        if task is not None:
            with suppress(asyncio.CancelledError):
                await task

    def _label(self) -> str:
        elapsed = int(time.monotonic() - self._phase_start)
        if self._tool_name is not None:
            base = f'Calling tool: {self._tool_name}'
            if self._tool_input_summary:
                base += f' ({self._tool_input_summary})'
            return f'{base} ... {elapsed}s'
        if self._step_name is not None:
            label = f'Thinking... (step: {self._step_name}, {elapsed}s)'
        else:
            label = f'Thinking... ({elapsed}s)'
        if elapsed >= _IDLE_WARNING_SECONDS:
            label += ' (no response — check LLM backend?)'
        return label

    def _ensure_status_and_task(self) -> None:
        label = self._label()
        if self._status is None:
            self._status = self._console.status(label, spinner='dots')
            self._status.start()
        else:
            self._status.update(label)
        if self._tick_task is None or self._tick_task.done():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                self._tick_task = None
            else:
                self._tick_task = loop.create_task(self._tick())

    async def _tick(self) -> None:
        while True:
            await asyncio.sleep(1)
            if self._status is not None:
                self._status.update(self._label())


class EventRenderer:
    """Consume an EngineEvent stream and render it to a Rich console.

    Holds final domain results on `ask_result` / `plan` for callers to read
    after `consume()` completes. Spinner state (Thinking vs. Calling tool,
    step name, elapsed timer, idle warning) is delegated to a private
    `_SpinnerController` that owns the live Rich `Status` and the asyncio
    tick task that refreshes the label once per second.
    """

    def __init__(
        self,
        mode: RenderMode,
        console: Console | None = None,
        *,
        sync_duration: float | None = None,
    ) -> None:
        self.mode = mode
        self.console = console or default_console
        self.sync_duration = sync_duration
        self.ask_result: AskResult | None = None
        self.plan: Plan | None = None
        self._spinner = _SpinnerController(self.console)
        self._sync_status: Status | None = None
        self._in_text = False
        self._operations_started = False

    @property
    def is_spinner_active(self) -> bool:
        return self._spinner.is_active

    async def consume(self, events: AsyncIterator[EngineEvent]) -> None:
        try:
            async for event in events:
                self._dispatch(event)
        finally:
            await self._spinner.aclose()
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
        self._spinner.set_step(event.step_name)
        logger.debug('Render: step %s', event.step_name)

    def on_thinking(self, event: ThinkingEvent) -> None:
        self._spinner.show_thinking()

    def on_text_delta(self, event: TextDeltaEvent) -> None:
        self._spinner.stop()
        if not self._in_text:
            self.console.print()
            self._in_text = True
        self.console.print(event.text, end='', soft_wrap=True, highlight=False)

    def on_tool_call(self, event: ToolCallEvent) -> None:
        self._spinner.stop()
        self._end_text_block()
        self.console.print(f'[dim]\\[{event.tool_name}][/dim]')
        self._spinner.show_tool_call(event.tool_name, event.input)

    def on_plan_operation(self, event: PlanOperationEvent) -> None:
        self._spinner.stop()
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
        self._spinner.stop()
        self._end_text_block()
        total = event.usage.prompt_tokens + event.usage.completion_tokens
        parts = [f'{total / 1000:.1f}k tokens']
        if self.sync_duration is not None:
            parts.append(f'sync {self.sync_duration:.1f}s')
        label = 'plan' if self.mode is RenderMode.PLAN else 'ask'
        step_total = sum(event.step_durations.values()) or event.duration
        parts.append(f'{label} {step_total:.1f}s')
        self.console.print(f'[dim]* {" \u00b7 ".join(parts)}[/dim]')

    def on_ask_result(self, event: AskResultEvent) -> None:
        self.ask_result = event.result

    def on_plan_result(self, event: PlanResultEvent) -> None:
        self.plan = event.plan

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
            renderer.sync_duration = result.duration
            renderer._dispatch(
                SyncDoneEvent(
                    ticket_count=result.ticket_count, duration=result.duration
                )
            )
        elif renderer._sync_status is not None:
            renderer._sync_status.stop()
            renderer._sync_status = None
        yield provider, result
