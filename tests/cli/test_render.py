import asyncio
import io
from dataclasses import dataclass
from datetime import UTC, datetime

from rich.console import Console

from oppie.ask.engine import AskResult
from oppie.cli.render import (
    EventRenderer,
    RenderMode,
    _SpinnerController,
    _summarize_tool_input,
)
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
from tests.cli.conftest import install_fake_status


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
    assert 'turns' not in out
    assert 'ask ' in out
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

    assert not renderer.is_spinner_active


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

    assert not renderer.is_spinner_active


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


# --- _summarize_tool_input -------------------------------------------------


def test_summarize_tool_input_empty_dict():
    assert _summarize_tool_input({}) == ''


def test_summarize_tool_input_single_string():
    assert _summarize_tool_input({'q': 'foo'}) == 'q="foo"'


def test_summarize_tool_input_non_string_value():
    result = _summarize_tool_input({'n': 42})

    assert result == 'n=42'


def test_summarize_tool_input_multiple_keys():
    result = _summarize_tool_input({'a': '1', 'b': '2'})

    assert result == 'a="1", b="2"'


def test_summarize_tool_input_truncates_over_40_chars():
    result = _summarize_tool_input({'key': 'x' * 100})

    assert len(result) <= 40
    assert result.endswith('…')


def test_summarize_tool_input_strips_newlines():
    result = _summarize_tool_input({'q': 'line1\nline2\rline3'})

    assert '\n' not in result
    assert '\r' not in result
    assert 'line1 line2 line3' in result


# --- _SpinnerController._label --------------------------------------------


def test_label_thinking_without_step(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 0.0)
    controller._phase_start = 0.0

    assert controller._label() == 'Thinking... (0s)'


def test_label_thinking_with_step(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    controller.set_step('research')
    controller._phase_start = 0.0
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 3.7)

    assert controller._label() == 'Thinking... (step: research, 3s)'


def test_label_idle_warning_at_30s(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    controller.set_step('research')
    controller._phase_start = 0.0
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 31.0)

    label = controller._label()

    assert 'no response — check LLM backend?' in label
    assert '31s' in label


def test_label_idle_warning_only_when_thinking(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    controller._tool_name = 'search_tickets'
    controller._tool_input_summary = ''
    controller._phase_start = 0.0
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 31.0)

    label = controller._label()

    assert 'no response' not in label


def test_label_tool_without_input(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    controller._tool_name = 'search_tickets'
    controller._tool_input_summary = ''
    controller._phase_start = 0.0
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 2.0)

    assert controller._label() == 'Calling tool: search_tickets ... 2s'


def test_label_tool_with_input(monkeypatch):
    controller = _SpinnerController(console=Console(file=io.StringIO()))
    controller._tool_name = 'search_tickets'
    controller._tool_input_summary = 'q="foo"'
    controller._phase_start = 0.0
    monkeypatch.setattr('oppie.cli.render.time.monotonic', lambda: 0.0)

    assert controller._label() == 'Calling tool: search_tickets (q="foo") ... 0s'


# --- _SpinnerController state transitions ----------------------------------


def test_state_transitions_reset_phase_and_toggle_tool_name(monkeypatch):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    created = install_fake_status(monkeypatch, console)

    counter = {'n': 0.0}

    def fake_monotonic():
        counter['n'] += 10.0
        return counter['n']

    monkeypatch.setattr('oppie.cli.render.time.monotonic', fake_monotonic)

    async def run():
        controller = _SpinnerController(console)
        controller.set_step('research')

        controller.show_thinking()
        phase1 = controller._phase_start
        assert controller._tool_name is None

        controller.show_tool_call('search_tickets', {'q': 'foo'})
        phase2 = controller._phase_start
        assert controller._tool_name == 'search_tickets'
        assert controller._tool_input_summary == 'q="foo"'
        assert phase2 != phase1

        controller.show_thinking()
        phase3 = controller._phase_start
        assert controller._tool_name is None
        assert phase3 != phase2

        await controller.aclose()

    asyncio.run(run())

    assert len(created) == 1
    all_labels = [created[0].label, *created[0].updates]
    assert any('Thinking' in label for label in all_labels)
    assert any('Calling tool: search_tickets' in label for label in all_labels)


def test_step_name_flows_into_thinking_label(monkeypatch):
    renderer, _ = _make_renderer(RenderMode.PLAN)
    created = install_fake_status(monkeypatch, renderer.console)
    events = [
        StepStartEvent(step_name='research'),
        ThinkingEvent(),
    ]

    asyncio.run(renderer.consume(_gen(events)))

    assert len(created) == 1
    fake = created[0]
    all_labels = [fake.label, *fake.updates]
    assert any('step: research' in label for label in all_labels)


def test_tool_call_swaps_spinner_label(monkeypatch):
    renderer, buf = _make_renderer(RenderMode.PLAN)
    created = install_fake_status(monkeypatch, renderer.console)
    events = [
        StepStartEvent(step_name='research'),
        ThinkingEvent(),
        ToolCallEvent(tool_name='search_tickets', input={'q': 'foo'}),
    ]

    asyncio.run(renderer.consume(_gen(events)))

    # Two FakeStatus instances: first for Thinking, second after stop() for the tool.
    assert len(created) == 2
    tool_status = created[1]
    labels = [tool_status.label, *tool_status.updates]
    assert any(
        label.startswith('Calling tool: search_tickets (q="foo")') for label in labels
    )
    assert '[search_tickets]' in buf.getvalue()


def test_aclose_cancels_tick_task(monkeypatch):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    install_fake_status(monkeypatch, console)

    async def run():
        controller = _SpinnerController(console)
        controller.show_thinking()
        task = controller._tick_task
        assert task is not None
        # Yield so the tick task gets to schedule itself.
        await asyncio.sleep(0)
        await controller.aclose()

        return task

    task = asyncio.run(run())

    assert task.done()


def test_ensure_status_handles_missing_event_loop():
    """Calling the controller outside an event loop must not crash."""
    console = Console(file=io.StringIO(), force_terminal=False, width=120)
    controller = _SpinnerController(console)
    controller.show_thinking()

    assert controller._tick_task is None
    controller.stop()


def test_stats_includes_sync_duration():
    renderer, buf = _make_renderer(RenderMode.ASK)
    renderer.sync_duration = 0.2
    events = [
        StatsEvent(
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
            turns=1,
            duration=1.5,
        ),
    ]
    asyncio.run(renderer.consume(_gen(events)))

    out = buf.getvalue()

    assert 'sync 0.2s' in out


def test_render_sync_emits_sync_done_when_synced(tmp_path, monkeypatch):
    """When auto_sync returns synced=True, render_sync emits SyncDoneEvent."""
    from contextlib import contextmanager

    from oppie.cli import render as render_module
    from oppie.cli.render import render_sync
    from oppie.config import load_oppie_config
    from oppie.sync import AutoSyncResult
    from tests.cli.conftest import setup_cli_instance

    home = setup_cli_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    renderer, _ = _make_renderer(RenderMode.ASK)

    fake_result = AutoSyncResult(synced=True, ticket_count=5, duration=0.4, error=None)

    @contextmanager
    def fake_setup_provider(home, config, *, no_sync, print_sync_success):
        yield (object(), fake_result)

    monkeypatch.setattr(render_module, 'setup_provider', fake_setup_provider)

    with render_sync(renderer, home, config, no_sync=False) as (provider, result):
        assert result.synced is True

    assert renderer.sync_duration == 0.4


def test_tick_updates_status_label(monkeypatch):
    """`_tick` pushes `_label()` updates onto the live status."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    created = install_fake_status(monkeypatch, console)

    async def run():
        # Stub asyncio.sleep so _tick cycles instantly.
        real_sleep = asyncio.sleep

        async def fast_sleep(_delay):
            await real_sleep(0)

        monkeypatch.setattr('oppie.cli.render.asyncio.sleep', fast_sleep)

        times = iter([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
        monkeypatch.setattr(
            'oppie.cli.render.time.monotonic',
            lambda: next(times, 5.0),
        )

        controller = _SpinnerController(console)
        controller.show_thinking()
        # Let the tick task run a few iterations.
        await real_sleep(0)
        await real_sleep(0)
        await real_sleep(0)
        await controller.aclose()

    asyncio.run(run())

    assert len(created) == 1
    # The initial status was created via console.status(...) with a label,
    # and _tick then called .update(...) at least once.
    assert len(created[0].updates) >= 1
