from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from enum import Enum

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
) -> tuple[str, list[Operation], TokenUsage, int]:
    """Run one engine step. Return (text, operations, usage, turns_used)."""
    tool_schemas = [t.to_llm_schema() for t in step.tools] or None
    tool_map = {t.name: t for t in step.tools}

    if step.inject_prompt:
        messages.append({'role': 'user', 'content': step.inject_prompt})

    total_usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    collected_operations: list[Operation] = []
    final_text = ''

    for turn in range(step.max_turns):
        logger.debug('Step %s turn %d/%d', step.name, turn + 1, step.max_turns)

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
            final_text = response.text

        if not response.tool_calls:
            break

        # Execute tool calls
        tool_results: list[ToolCallResult] = []
        for tc in response.tool_calls:
            tool = tool_map.get(tc.name)
            if tool is None:
                result = ToolResult(content=f'Unknown tool: {tc.name}', is_error=True)
            else:
                result = await tool.execute(tc.input, tool_context)

            if tc.name == 'propose_operation' and not result.is_error:
                op_data = json.loads(result.content)
                if op_data.get('accepted'):
                    collected_operations.append(
                        Operation(
                            ticket_id=op_data['ticket_id'],
                            field=op_data['field'],
                            before_value=op_data['before_value'],
                            after_value=op_data['after_value'],
                            rationale=op_data['rationale'],
                        )
                    )

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

    return final_text, collected_operations, total_usage, turn + 1


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
) -> EngineResult:
    """Run a mode-specific step sequence.

    Plan mode: research -> propose -> summary.
    Ask mode: research -> answer.
    Each step has explicit tools, tool_choice, and turn budget.
    """
    logger.info('Engine run: mode=%s', mode.value)

    steps = _plan_steps(tools) if mode == EngineMode.PLAN else _ask_steps(tools)

    messages: list[dict] = [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': prompt},
    ]

    total_usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
    all_operations: list[Operation] = []
    final_text = ''
    total_turns = 0

    for step in steps:
        logger.info('Engine step: %s', step.name)
        text, operations, usage, turns = await _run_step(
            step=step,
            messages=messages,
            llm=llm,
            tool_context=tool_context,
            max_tokens=max_tokens,
            temperature=temperature,
            system_parts=system_parts,
        )
        if text:
            final_text = text
        all_operations.extend(operations)
        total_usage = total_usage + usage
        total_turns += turns

    return EngineResult(
        text=final_text,
        operations=all_operations,
        usage=total_usage,
        turns=total_turns,
    )
