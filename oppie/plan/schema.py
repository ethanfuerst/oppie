import json
import re
from pathlib import Path

from oppie.models.plan import Plan

PLAN_RESPONSE_SCHEMA: dict = {
    'type': 'object',
    'properties': {
        'operations': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'ticket_id': {'type': 'string'},
                    'field': {'type': 'string'},
                    'before_value': {},
                    'after_value': {},
                    'rationale': {'type': 'string'},
                },
                'required': [
                    'ticket_id',
                    'field',
                    'before_value',
                    'after_value',
                    'rationale',
                ],
            },
        },
        'risks': {
            'type': 'array',
            'items': {'type': 'string'},
        },
    },
    'required': ['operations', 'risks'],
}


def load_context(home: Path) -> dict[str, str]:
    """Read optional context docs from {home}/context/.

    Return a dict of filename stem -> content for each .md file that exists.
    Known files: vision.md, roadmap.md, metrics.md, prioritization.md.
    """
    context_dir = home / 'context'
    if not context_dir.is_dir():
        return {}
    context = {}
    for name in ('vision', 'roadmap', 'metrics', 'prioritization'):
        path = context_dir / f'{name}.md'
        if path.exists():
            content = path.read_text().strip()
            if content:
                context[name] = content
    return context


def find_similar_plans(
    home: Path,
    instruction: str,
    limit: int = 3,
) -> list[Plan]:
    """Find past plans with instruction keyword overlap.

    Read from the JSONL index for scoring, then load full Plan JSON
    only for the top matches.
    """
    from oppie.plan.persistence import _load_plan_index, load_plan

    plans_dir = home / 'artifacts' / 'plans'
    entries = _load_plan_index(plans_dir)

    instruction_words = set(re.findall(r'\w+', instruction.lower()))
    if not instruction_words:
        return []

    scored: list[tuple[float, dict]] = []
    for entry in entries:
        plan_words = set(re.findall(r'\w+', entry['instruction'].lower()))
        overlap = len(instruction_words & plan_words)
        if overlap > 0:
            score = overlap / max(len(instruction_words), len(plan_words))
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_entries = scored[:limit]

    plans: list[Plan] = []
    for _, entry in top_entries:
        try:
            plan = load_plan(entry['plan_id'], home)
            plans.append(plan)
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            continue
    return plans
