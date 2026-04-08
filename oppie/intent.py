from __future__ import annotations

import logging
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from oppie.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class Intent(Enum):
    QUESTION = 'question'
    INSTRUCTION = 'instruction'
    APPLY = 'apply'


async def classify_intent(
    prompt: str,
    llm: LLMProvider,
    max_tokens: int = 50,
) -> Intent:
    """Classify intent using an LLM call. Returns Intent enum."""
    messages = [
        {
            'role': 'system',
            'content': (
                'Classify the user prompt as exactly one of: question, instruction, apply.\n'
                'An instruction asks to change or act on tickets '
                '(move, close, assign, prioritize, create, etc.). '
                'An apply prompt asks to execute/apply an existing plan. '
                'Everything else is a question — including vague prompts, '
                'off-topic requests, and information queries about tickets. '
                'If unsure, classify as question. '
                'Respond with a single JSON object: {"intent": "question"|"instruction"|"apply"}'
            ),
        },
        {'role': 'user', 'content': prompt},
    ]
    classify_schema = {
        'type': 'object',
        'properties': {
            'intent': {
                'type': 'string',
                'enum': ['question', 'instruction', 'apply'],
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
    logger.warning('LLM classification failed, defaulting to question')
    return Intent.QUESTION
