from __future__ import annotations

import logging
import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oppie.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class Intent(Enum):
    QUESTION = 'question'
    INSTRUCTION = 'instruction'
    APPLY = 'apply'
    AMBIGUOUS = 'ambiguous'


# Patterns that strongly indicate a question
_QUESTION_MARKERS = re.compile(
    r'(?:'
    r'\?'  # contains question mark
    r'|^(?:how|what|which|who|where|when|why|is|are|do|does|can|could|will|would|should|has|have)\b'
    r'|^(?:list|show|count|tell me|summarize|describe)\b'
    r')',
    re.IGNORECASE,
)

# Patterns that indicate apply intent (apply an existing plan)
_APPLY_MARKERS = re.compile(
    r'(?:'
    r'^(?:force\s+)?apply(?:\s+(?:it|the\s+plan|plan-[a-f0-9]+))?(?:\s+--force)?$'
    r'|^(?:run|execute)\s+the\s+plan\b'
    r'|^go\s+ahead\b'
    r')',
    re.IGNORECASE,
)

# Patterns that strongly indicate an instruction
_INSTRUCTION_MARKERS = re.compile(
    r'^(?:move|close|finish|complete|reopen|open|start|begin|block|'
    r'prioritize|deprioritize|assign|unassign|set|change|update|'
    r'add|remove|delete|create|rename|merge|split|'
    r'triage|clean|fix|resolve|escalate|defer|archive|label|tag)\b',
    re.IGNORECASE,
)


def classify_intent(prompt: str) -> Intent:
    """Classify a prompt as question, instruction, apply, or ambiguous using local heuristics."""
    stripped = prompt.strip()
    if not stripped:
        return Intent.AMBIGUOUS

    has_apply = bool(_APPLY_MARKERS.search(stripped))
    has_question = bool(_QUESTION_MARKERS.search(stripped))
    has_instruction = bool(_INSTRUCTION_MARKERS.search(stripped))

    # Question markers override everything (e.g., "can I apply?" → question)
    if has_question and not has_apply:
        return Intent.QUESTION
    if has_question and has_apply:
        return Intent.QUESTION

    # Apply takes priority over instruction
    if has_apply:
        return Intent.APPLY

    if has_instruction:
        return Intent.INSTRUCTION

    # No strong signal either way
    return Intent.AMBIGUOUS


async def classify_intent_llm(
    prompt: str,
    llm: LLMProvider,
    max_tokens: int = 50,
) -> Intent:
    """Classify intent using an LLM call. Returns Intent enum."""
    messages = [
        {
            'role': 'system',
            'content': (
                'Classify the user prompt as exactly one of: question, instruction, apply, ambiguous.\n'
                'A question asks for information about tickets. '
                'An instruction asks to change or act on tickets. '
                'An apply prompt asks to execute/apply an existing plan. '
                'Respond with a single JSON object: {"intent": "question"|"instruction"|"apply"|"ambiguous"}'
            ),
        },
        {'role': 'user', 'content': prompt},
    ]
    classify_schema = {
        'type': 'object',
        'properties': {
            'intent': {
                'type': 'string',
                'enum': ['question', 'instruction', 'apply', 'ambiguous'],
            },
        },
        'required': ['intent'],
    }
    response = await llm.generate(
        messages=messages,
        response_schema=classify_schema,
        max_tokens=max_tokens,
        temperature=0.0,
    )
    if response.json and 'intent' in response.json:
        try:
            return Intent(response.json['intent'])
        except ValueError:
            pass
    logger.warning('LLM classification failed, falling back to heuristics')
    return classify_intent(prompt)
