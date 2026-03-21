import json
import tempfile
from pathlib import Path

from oppie.models.plan import Plan

PLAN_INDEX_FILENAME = '.plan-index.jsonl'


def _append_plan_index(plans_dir: Path, plan: Plan) -> None:
    """Append a plan entry to the JSONL index."""
    entry = {
        'plan_id': plan.plan_id,
        'instruction': plan.instruction,
        'created_at': plan.created_at,
    }
    index_path = plans_dir / PLAN_INDEX_FILENAME
    with open(index_path, 'a') as f:
        f.write(json.dumps(entry, separators=(',', ':')) + '\n')


def _rebuild_plan_index(plans_dir: Path) -> list[dict]:
    """Rebuild the JSONL index by scanning all plan JSON files.

    Write the rebuilt index and return the entries.
    """
    entries: list[dict] = []
    for path in sorted(plans_dir.glob('plan-*.json')):
        try:
            data = json.loads(path.read_text())
            entries.append(
                {
                    'plan_id': data['plan_id'],
                    'instruction': data['instruction'],
                    'created_at': data.get('created_at', ''),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    index_path = plans_dir / PLAN_INDEX_FILENAME
    with open(index_path, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry, separators=(',', ':')) + '\n')
    return entries


def _load_plan_index(plans_dir: Path) -> list[dict]:
    """Load the plan index from JSONL. Rebuild if missing."""
    index_path = plans_dir / PLAN_INDEX_FILENAME
    if not index_path.exists():
        if not plans_dir.exists():
            return []
        return _rebuild_plan_index(plans_dir)

    entries: list[dict] = []
    for line in index_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def save_plan(plan: Plan, home: Path) -> Path:
    """Save plan as JSON to artifacts/plans/plan-{plan_id}.json.

    Use atomic write (temp file + rename).
    Return the path to the saved JSON file.
    """
    plans_dir = home / 'artifacts' / 'plans'
    plans_dir.mkdir(parents=True, exist_ok=True)
    target = plans_dir / f'plan-{plan.plan_id}.json'

    fd, tmp_path = tempfile.mkstemp(dir=plans_dir, suffix='.tmp')
    try:
        with open(fd, 'w') as f:
            json.dump(plan.to_dict(), f, indent=2)
            f.write('\n')
        Path(tmp_path).replace(target)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    _append_plan_index(plans_dir, plan)
    return target


def load_plan(plan_id: str, home: Path) -> Plan:
    """Load a plan by ID from artifacts/plans/plan-{plan_id}.json.

    Raise FileNotFoundError if not found.
    """
    path = home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
    if not path.exists():
        raise FileNotFoundError(f'Plan not found: {plan_id}')
    data = json.loads(path.read_text())
    return Plan.from_dict(data)
