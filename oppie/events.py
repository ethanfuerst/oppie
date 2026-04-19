from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oppie.ask.engine import AskResult
    from oppie.llm.base import TokenUsage
    from oppie.models.operation import Operation
    from oppie.models.plan import Plan


@dataclass(slots=True)
class SyncStartEvent:
    """Provider sync has started. Emitted by CLI/TUI, not the engine."""

    provider: str


@dataclass(slots=True)
class SyncDoneEvent:
    """Provider sync completed. Emitted by CLI/TUI, not the engine."""

    ticket_count: int
    duration: float


@dataclass(slots=True)
class StepStartEvent:
    """An engine step is starting."""

    step_name: str
    is_final: bool = False


@dataclass(slots=True)
class ThinkingEvent:
    """LLM call is in progress."""


@dataclass(slots=True)
class TextDeltaEvent:
    """Incremental text output from the LLM.

    ``step_name`` identifies the engine step that produced the chunk.
    ``is_final`` is True only for the final step of the mode (ask: answer;
    plan: summary). Consumers must gate user-facing rendering and persisted
    artifacts on ``is_final=True``; non-final text is intermediate research
    chatter and is only surfaced when the renderer is in debug mode.
    """

    text: str
    step_name: str = ''
    is_final: bool = False


@dataclass(slots=True)
class ToolCallEvent:
    """A tool call was dispatched."""

    tool_name: str
    input: dict


@dataclass(slots=True)
class PlanOperationEvent:
    """A plan operation was accepted."""

    operation: Operation


@dataclass(slots=True)
class StatsEvent:
    """Final statistics for the engine run."""

    usage: TokenUsage
    turns: int
    duration: float
    step_durations: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class PlanResultEvent:
    """Final plan result. Emitted by generate_plan(). Carries full Plan object."""

    plan: Plan


@dataclass(slots=True)
class AskResultEvent:
    """Final ask result. Emitted by generate_ask(). Carries full AskResult object."""

    result: AskResult


@dataclass(slots=True)
class _StepDoneEvent:
    """Internal event for step completion stats. Not yielded to callers."""

    usage: TokenUsage
    turns: int


EngineEvent = (
    SyncStartEvent
    | SyncDoneEvent
    | StepStartEvent
    | ThinkingEvent
    | TextDeltaEvent
    | ToolCallEvent
    | PlanOperationEvent
    | StatsEvent
    | PlanResultEvent
    | AskResultEvent
)
