import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.config import OppieConfig
from oppie.engine import EngineMode, run_engine
from oppie.events import AskResultEvent, EngineEvent, StatsEvent, TextDeltaEvent
from oppie.llm import create_llm_provider
from oppie.llm.base import TokenUsage
from oppie.prompts.builder import PromptMode, build_system_prompt, flatten_system_prompt
from oppie.prompts.formatting import format_tickets_for_llm
from oppie.providers.base import TicketProvider
from oppie.run_log import RunLog, RunLogEntry, generate_run_id
from oppie.tools.base import ToolContext
from oppie.tools.tickets import GET_TICKET_TOOL, SEARCH_TICKETS_TOOL

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AskResult:
    """Result of an ask operation."""

    answer: str
    artifact_path: Path | None
    run_id: str
    duration: float
    usage: TokenUsage | None


async def generate_ask(
    provider: TicketProvider,
    config: OppieConfig,
    question: str,
) -> AsyncGenerator[EngineEvent, None]:
    """Answer a question about tickets, yielding events."""
    logger.info('Generating ask for question: %r', question)
    home = provider.home
    start = time.monotonic()

    tickets = provider.list_tickets()

    # Create LLM provider
    llm = create_llm_provider(config.llm)

    # Build layered system prompt
    system_parts = build_system_prompt(mode=PromptMode.ASK, home=home)
    system_prompt = flatten_system_prompt(system_parts)
    system_parts_dicts = [
        {
            'content': p.content,
            **({'cache_control': p.cache_control} if p.cache_control else {}),
        }
        for p in system_parts
    ]

    # Build user prompt with ticket summary
    ticket_summary = format_tickets_for_llm(tickets)
    user_prompt = f'# Current tickets\n{ticket_summary}\n\n# Question\n{question}'

    # Set up tools and context
    all_tools = [SEARCH_TICKETS_TOOL, GET_TICKET_TOOL]
    tool_context = ToolContext(
        provider=provider,
        home=home,
        capabilities=provider.capabilities,
    )

    max_tokens = config.llm.max_tokens
    temperature = config.llm.temperature

    text_parts: list[str] = []
    result_usage: TokenUsage | None = None

    async with llm:
        async for event in run_engine(
            prompt=user_prompt,
            tools=all_tools,
            llm=llm,
            tool_context=tool_context,
            mode=EngineMode.ASK,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            system_parts=system_parts_dicts,
        ):
            if isinstance(event, TextDeltaEvent):
                text_parts.append(event.text)
            elif isinstance(event, StatsEvent):
                result_usage = event.usage
            yield event

    duration = time.monotonic() - start
    answer = ''.join(text_parts)
    run_id = generate_run_id()
    artifact_path = _save_ask_artifact(home, question, answer, run_id)
    _append_run_log(home, run_id, duration, artifact_path, result_usage)

    ask_result = AskResult(
        answer=answer,
        artifact_path=artifact_path,
        run_id=run_id,
        duration=duration,
        usage=result_usage,
    )

    yield AskResultEvent(result=ask_result)


def _save_ask_artifact(
    home: Path,
    question: str,
    answer: str,
    run_id: str,
) -> Path:
    """Save ask artifact as JSON."""
    store = ArtifactStore(home)
    content = json.dumps(
        {'question': question, 'answer': answer, 'run_id': run_id},
        indent=2,
    )
    return store.save_artifact(ArtifactType.ASK, content, run_id)


def _append_run_log(
    home: Path,
    run_id: str,
    duration: float,
    artifact_path: Path,
    usage: TokenUsage | None,
) -> None:
    """Append ask entry to run log."""
    run_log = RunLog(home)
    run_log.append(
        RunLogEntry(
            run_id=run_id,
            command='ask',
            timestamp=datetime.now(UTC).isoformat(),
            duration=duration,
            artifact_paths=[str(artifact_path)],
            token_usage=usage.to_dict() if usage else None,
        )
    )
