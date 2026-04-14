from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from oppie.events import (
    EngineEvent,
    PlanOperationEvent,
    StatsEvent,
    StepStartEvent,
    TextDeltaEvent,
    ThinkingEvent,
    ToolCallEvent,
    _StepDoneEvent,
)
from oppie.llm.base import LLMProvider, TokenUsage, ToolCallResult
from oppie.models.operation import Operation
from oppie.tools.base import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class EngineMode(Enum):
    ASK = 'ask'
    PLAN = 'plan'


@dataclass(slots=True)
class EngineResult:
    """Result of an engine run."""

    text: str
    operations: list[Operation]
    usage: TokenUsage
    turns: int


@dataclass(slots=True)
class EngineStep:
    """One phase of an engine run."""

    name: str
    tools: list[Tool]
    tool_choice: str | dict | None  # None=auto, 'any', {'name': '...'}
    max_turns: int
    inject_prompt: str | None = None


def _plan_steps(all_tools: list[Tool]) -> list[EngineStep]:
    """Define the step sequence for plan mode."""
    research_tools = [
        t for t in all_tools if t.name in ('search_tickets', 'get_ticket')
    ]
    propose_tools = [
        t for t in all_tools if t.name in ('propose_operation', 'get_ticket')
    ]

    return [
        EngineStep(
            name='research',
            tools=research_tools,
            tool_choice='any',
            max_turns=5,
        ),
        EngineStep(
            name='propose',
            tools=propose_tools,
            tool_choice={'name': 'propose_operation'},
            max_turns=5,
            inject_prompt=(
                'Based on the ticket data you gathered, propose operations '
                'using the propose_operation tool. Call it once per change.'
            ),
        ),
        EngineStep(
            name='summary',
            tools=[],
            tool_choice=None,
            max_turns=1,
            inject_prompt=(
                'Summarize the proposed operations and list any risks or concerns.'
            ),
        ),
    ]


def _ask_steps(all_tools: list[Tool]) -> list[EngineStep]:
    """Define the step sequence for ask mode."""
    research_tools = [
        t for t in all_tools if t.name in ('search_tickets', 'get_ticket')
    ]

    return [
        EngineStep(
            name='research',
            tools=research_tools,
            tool_choice='any',
            max_turns=5,
        ),
        EngineStep(
            name='answer',
            tools=[],
            tool_choice=None,
            max_turns=1,
            inject_prompt='Now answer the question based on the ticket data you gathered.',
        ),
    ]


async def _run_step(
    step: EngineStep,
    messages: list[dict],
    llm: LLMProvider,
    tool_context: ToolContext,
    max_tokens: int,
    temperature: float,
    system_parts: list[dict] | None = None,
) -> AsyncGenerator[EngineEvent | _StepDoneEvent, None]:
    """Run one engine step, yielding events as they occur."""
    tool_schemas = [t.to_llm_schema() for t in step.tools] or None
    tool_map = {t.name: t for t in step.tools}
    is_text_only = not step.tools

    if step.inject_prompt:
        messages.append({'role': 'user', 'content': step.inject_prompt})

    total_usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    turns_used = 0

    for turn in range(step.max_turns):
        logger.debug('Step %s turn %d/%d', step.name, turn + 1, step.max_turns)
        turns_used = turn + 1

        if is_text_only:
            # Text-only step: use stream() for incremental output
            yield ThinkingEvent()
            stream_result = await llm.stream(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            collected_text = ''
            async for chunk in stream_result:
                collected_text += chunk
                yield TextDeltaEvent(text=chunk)
            usage = stream_result.usage or TokenUsage(
                prompt_tokens=0, completion_tokens=0
            )
            total_usage = total_usage + usage
            messages.append({'role': 'assistant', 'content': collected_text})
            break
        else:
            # Tool step: use generate() for full response
            yield ThinkingEvent()
            response = await llm.generate(
                messages=messages,
                tools=tool_schemas,
                tool_choice=step.tool_choice if tool_schemas else None,
                max_tokens=max_tokens,
                temperature=temperature,
                system_parts=system_parts,
            )
            total_usage = total_usage + response.usage

            if response.text:
                yield TextDeltaEvent(text=response.text)

            if not response.tool_calls:
                break

            # Execute tool calls and yield events
            tool_results: list[ToolCallResult] = []
            for tc in response.tool_calls:
                yield ToolCallEvent(tool_name=tc.name, input=tc.input)

                tool = tool_map.get(tc.name)
                if tool is None:
                    result = ToolResult(
                        content=f'Unknown tool: {tc.name}', is_error=True
                    )
                else:
                    result = await tool.execute(tc.input, tool_context)

                if tc.name == 'propose_operation' and not result.is_error:
                    op_data = json.loads(result.content)
                    if op_data.get('accepted'):
                        op = Operation(
                            ticket_id=op_data['ticket_id'],
                            field=op_data['field'],
                            before_value=op_data['before_value'],
                            after_value=op_data['after_value'],
                            rationale=op_data['rationale'],
                        )
                        yield PlanOperationEvent(operation=op)

                tool_results.append(
                    ToolCallResult(
                        request=tc,
                        content=result.content,
                        is_error=result.is_error,
                    )
                )

            # Append to message history
            assistant_msg: dict = {'role': 'assistant', 'content': response.text}
            if response.tool_calls:
                assistant_msg['tool_calls'] = [
                    {'id': tc.id, 'name': tc.name, 'input': tc.input}
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)
            messages.append(
                {
                    'role': 'tool_results',
                    'results': [
                        {
                            'tool_call_id': r.request.id,
                            'content': r.content,
                            'is_error': r.is_error,
                        }
                        for r in tool_results
                    ],
                }
            )

    yield _StepDoneEvent(usage=total_usage, turns=turns_used)


async def run_engine(
    prompt: str,
    tools: list[Tool],
    llm: LLMProvider,
    tool_context: ToolContext,
    mode: EngineMode,
    system_prompt: str,
    max_tokens: int = 2000,
    temperature: float = 0.7,
    system_parts: list[dict] | None = None,
) -> AsyncGenerator[EngineEvent, None]:
    """Run a mode-specific step sequence, yielding events.

    Plan mode: research -> propose -> summary.
    Ask mode: research -> answer.
    Each step has explicit tools, tool_choice, and turn budget.
    """
    logger.info('Engine run: mode=%s', mode.value)
    start = time.monotonic()

    steps = _plan_steps(tools) if mode == EngineMode.PLAN else _ask_steps(tools)

    messages: list[dict] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': prompt},
    ]

    total_usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    total_turns = 0
    step_durations: dict[str, float] = {}

    for step in steps:
        logger.info('Engine step: %s', step.name)
        yield StepStartEvent(step_name=step.name)
        step_start = time.monotonic()
        async for event in _run_step(
            step=step,
            messages=messages,
            llm=llm,
            tool_context=tool_context,
            max_tokens=max_tokens,
            temperature=temperature,
            system_parts=system_parts,
        ):
            if isinstance(event, _StepDoneEvent):
                total_usage = total_usage + event.usage
                total_turns += event.turns
            else:
                yield event
        step_durations[step.name] = time.monotonic() - step_start

    duration = time.monotonic() - start
    yield StatsEvent(
        usage=total_usage,
        turns=total_turns,
        duration=duration,
        step_durations=step_durations,
    )


async def collect_engine_result(
    events: AsyncGenerator[EngineEvent, None],
) -> tuple[EngineResult, list[EngineEvent]]:
    """Consume all events from run_engine() and return an EngineResult.

    Also returns the full event list for callers that need both.
    """
    all_events: list[EngineEvent] = []
    text_parts: list[str] = []
    operations: list[Operation] = []
    usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    turns = 0

    async for event in events:
        all_events.append(event)
        if isinstance(event, TextDeltaEvent):
            text_parts.append(event.text)
        elif isinstance(event, PlanOperationEvent):
            operations.append(event.operation)
        elif isinstance(event, StatsEvent):
            usage = event.usage
            turns = event.turns

    result = EngineResult(
        text=''.join(text_parts),
        operations=operations,
        usage=usage,
        turns=turns,
    )
    return result, all_events
