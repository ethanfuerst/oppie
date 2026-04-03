from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING

from oppie.prompts.formatting import (
    format_context_for_llm,
    load_context,
)
from oppie.prompts.text.ask import ASK_BASE_PROMPT
from oppie.prompts.text.plan import PLAN_BASE_PROMPT

if TYPE_CHECKING:
    from pathlib import Path

    from oppie.models.capabilities import ProviderCapabilities

logger = logging.getLogger(__name__)


class PromptMode(Enum):
    ASK = 'ask'
    PLAN = 'plan'


@dataclass(slots=True)
class SystemPromptPart:
    """One layer of the system prompt."""

    content: str
    cache_control: dict | None = None


def build_system_prompt(
    mode: PromptMode,
    home: Path,
    capabilities: ProviderCapabilities | None = None,
    past_plans_text: str = '',
) -> list[SystemPromptPart]:
    """Assemble system prompt as ordered layers.

    Layer 1: Base prompt (role, rules) — stable, cacheable.
    Layer 2: Instance context (vision/roadmap) — stable per session.
    Layer 3: Dynamic context (date, constraints, past plans).
    """
    layers: list[SystemPromptPart] = []

    # Layer 1: base prompt
    base = PLAN_BASE_PROMPT if mode == PromptMode.PLAN else ASK_BASE_PROMPT
    layers.append(SystemPromptPart(content=base, cache_control={'type': 'ephemeral'}))

    # Layer 2: instance context
    context = load_context(home)
    if context:
        context_text = format_context_for_llm(context)
        layers.append(
            SystemPromptPart(
                content=f'# Instance context\n{context_text}',
                cache_control={'type': 'ephemeral'},
            )
        )

    # Layer 3: dynamic context
    dynamic_parts: list[str] = [
        f'Current date: {datetime.now(UTC).strftime("%Y-%m-%d")}'
    ]

    if mode == PromptMode.PLAN:
        if capabilities:
            constraints = capabilities.format_constraints_for_prompt()
            if constraints:
                dynamic_parts.append(f'# Field constraints\n{constraints}')
        if past_plans_text and past_plans_text != '(no similar past plans)':
            dynamic_parts.append(f'# Past similar plans\n{past_plans_text}')

    layers.append(SystemPromptPart(content='\n\n'.join(dynamic_parts)))

    return layers


def flatten_system_prompt(parts: list[SystemPromptPart]) -> str:
    """Join all system prompt parts into a single string."""
    return '\n\n'.join(p.content for p in parts)
