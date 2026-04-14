import asyncio
import io
from dataclasses import dataclass
from datetime import UTC, datetime

from rich.console import Console

from oppie.ask.engine import AskResult
from oppie.cli.render import EventRenderer, RenderMode
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
from oppie.llm.base import TokenUsage
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus


async def _gen(events):
    for e in events:
        yield e


def _make_renderer(mode):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    return EventRenderer(mode, console=console), buf


def _make_ask_result():
    return AskResult(
        answer='Hello, world.',
        artifact_path=None,
        run_id='run-1',
        duration=1.5,
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )


def _make_plan(operations):
    return Plan(
        instruction='do the thing',
        operations=operations,
        risks=[],
        created_at=datetime.now(UTC).isoformat(),
        status=PlanStatus.SAVED,
    )


def test_ask_flow_streams_text_and_captures_result():
    renderer, buf = _make_renderer(RenderMode.ASK)
    events = [
        SyncStartEvent(provider='local'),
        SyncDoneEvent(ticket_count=3, duration=0.2),
        StepStartEvent(step_name='answer'),
        ThinkingEvent(),
        TextDeltaEvent(text='Hello, '),
        TextDeltaEvent(text='world.'),
        StatsEvent(
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            turns=1,
            duration=1.5,
        ),
        AskResultEvent(result=_make_ask_result()),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    out = buf.getvalue()

    assert 'Synced (3 tickets' in out
    assert 'Hello, world.' in out
    assert '0.1k tokens' in out
    assert '1 turns' in out
    assert renderer.ask_result is not None
    assert renderer.ask_result.answer == 'Hello, world.'


def test_plan_flow_streams_operations_and_captures_plan():
    renderer, buf = _make_renderer(RenderMode.PLAN)
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='open',
        after_value='done',
        rationale='closing it',
    )
    events = [
        StepStartEvent(step_name='research'),
        ThinkingEvent(),
        ToolCallEvent(tool_name='search_tickets', input={'q': 'foo'}),
        ThinkingEvent(),
        PlanOperationEvent(operation=op),
        StatsEvent(
            usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
            turns=2,
            duration=2.0,
        ),
        PlanResultEvent(plan=_make_plan([op])),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    out = buf.getvalue()

    assert '[search_tickets]' in out
    assert 'Operations:' in out
    assert 'T-1' in out
    assert 'open -> done' in out
    assert 'closing it' in out
    assert renderer.plan is not None
    assert len(renderer.plan.operations) == 1


def test_thinking_clears_on_first_text_delta():
    renderer, _ = _make_renderer(RenderMode.ASK)
    events = [
        ThinkingEvent(),
        TextDeltaEvent(text='hi'),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    assert renderer._thinking is None


def test_multiple_thinking_events_handled():
    renderer, _ = _make_renderer(RenderMode.PLAN)
    events = [
        ThinkingEvent(),
        ToolCallEvent(tool_name='search_tickets', input={}),
        ThinkingEvent(),
        ToolCallEvent(tool_name='get_ticket', input={}),
        ThinkingEvent(),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    assert renderer._thinking is None


def test_unknown_event_ignored():
    @dataclass
    class WeirdEvent:
        x: int = 1

    renderer, buf = _make_renderer(RenderMode.ASK)
    asyncio.run(renderer.consume(_gen([WeirdEvent()])))

    assert buf.getvalue() == ''


def test_sync_start_without_sync_done_still_completes():
    renderer, _ = _make_renderer(RenderMode.ASK)
    events = [SyncStartEvent(provider='local')]
    asyncio.run(renderer.consume(_gen(events)))

    assert renderer._sync_status is not None  # never explicitly stopped


def test_text_block_terminates_on_step_start():
    renderer, buf = _make_renderer(RenderMode.ASK)
    events = [
        TextDeltaEvent(text='partial'),
        StepStartEvent(step_name='next'),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    assert renderer._in_text is False
    assert 'partial' in buf.getvalue()


def test_render_sync_local_no_sync_event(tmp_path, monkeypatch):
    """For local provider, auto_sync returns synced=False — no SyncDone."""
    from oppie.cli.render import render_sync
    from oppie.config import load_oppie_config
    from tests.cli.conftest import setup_cli_instance

    home = setup_cli_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    renderer, _ = _make_renderer(RenderMode.ASK)

    with render_sync(renderer, home, config, no_sync=False) as (provider, result):
        assert provider is not None
        assert result.synced is False

    # No SyncDoneEvent fired (local doesn't sync), but spinner stopped
    assert renderer._sync_status is None
