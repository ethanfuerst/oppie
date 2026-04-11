import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from oppie.models.plan import PLAN_INDEX_FILENAME
from oppie.models.ticket import SCHEMA_VERSION

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RepairIssue:
    name: str
    description: str
    fixable: bool
    detail: str | None = None


@dataclass(slots=True)
class RepairResult:
    name: str
    success: bool
    message: str


def scan_run_log(home: Path) -> tuple[list[RepairIssue], dict]:
    """Scan run log for malformed entries and dead artifact refs.

    Return (issues, context_dict) where context_dict has data needed for repair.
    """
    log_path = home / 'logs' / 'runs.jsonl'
    issues: list[RepairIssue] = []
    ctx: dict = {'log_path': log_path}

    if not log_path.exists():
        return issues, ctx

    valid_lines: list[str] = []
    malformed_count = 0
    dead_ref_count = 0

    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            malformed_count += 1
            continue

        # Check artifact references
        artifact_paths = entry.get('artifact_paths', [])
        live_paths = [p for p in artifact_paths if (home / p).exists()]
        if len(live_paths) < len(artifact_paths):
            dead_ref_count += len(artifact_paths) - len(live_paths)
            entry['artifact_paths'] = live_paths

        valid_lines.append(json.dumps(entry, separators=(',', ':')))

    ctx['valid_lines'] = valid_lines

    if malformed_count > 0:
        issues.append(
            RepairIssue(
                'Malformed run log entries',
                f'{malformed_count} malformed line(s)',
                fixable=True,
            )
        )
    if dead_ref_count > 0:
        issues.append(
            RepairIssue(
                'Invalid artifact references',
                f'{dead_ref_count} dead reference(s) in run log',
                fixable=True,
            )
        )

    return issues, ctx


def scan_tickets(home: Path) -> tuple[list[RepairIssue], dict]:
    """Scan tickets for missing schema_version and corrupt JSON."""
    tickets_dir = home / 'tickets'
    issues: list[RepairIssue] = []
    ctx: dict = {'missing_version': [], 'corrupt': []}

    if not tickets_dir.exists():
        return issues, ctx

    for path in sorted(tickets_dir.glob('*.json')):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            ctx['corrupt'].append(path)
            continue

        if 'schema_version' not in data:
            ctx['missing_version'].append(path)

    if ctx['missing_version']:
        issues.append(
            RepairIssue(
                'Missing schema_version',
                f'{len(ctx["missing_version"])} ticket(s) missing schema_version',
                fixable=True,
            )
        )
    if ctx['corrupt']:
        issues.append(
            RepairIssue(
                'Corrupt ticket JSON',
                f'{len(ctx["corrupt"])} ticket(s) with invalid JSON',
                fixable=False,
                detail='Manual fix required: '
                + ', '.join(p.name for p in ctx['corrupt']),
            )
        )

    return issues, ctx


def scan_plan_index(home: Path) -> tuple[list[RepairIssue], dict]:
    """Check if plan index is stale."""
    plans_dir = home / 'artifacts' / 'plans'
    issues: list[RepairIssue] = []
    ctx: dict = {'plans_dir': plans_dir}

    if not plans_dir.exists():
        return issues, ctx

    index_path = plans_dir / PLAN_INDEX_FILENAME
    plan_files = {p.stem.replace('plan-', '') for p in plans_dir.glob('plan-*.json')}

    if not plan_files:
        return issues, ctx

    indexed_ids: set[str] = set()
    if index_path.exists():
        for line in index_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                indexed_ids.add(entry.get('plan_id', ''))
            except json.JSONDecodeError:
                pass

    if indexed_ids != plan_files:
        issues.append(
            RepairIssue(
                'Stale plan index',
                f'Index has {len(indexed_ids)} entries,'
                f' {len(plan_files)} plan files exist',
                fixable=True,
            )
        )

    return issues, ctx


def scan_sqlite(home: Path) -> tuple[list[RepairIssue], dict]:
    """Check SQLite cache for corruption."""
    import sqlite3

    db_path = home / 'state' / 'cache.sqlite'
    issues: list[RepairIssue] = []

    if not db_path.exists():
        return issues, {}

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute('SELECT count(*) FROM tickets')
        conn.close()
    except (sqlite3.DatabaseError, sqlite3.OperationalError) as e:
        issues.append(
            RepairIssue(
                'SQLite corruption',
                str(e),
                fixable=False,
                detail='Run oppie sync --full or delete state/cache.sqlite and re-sync',
            )
        )

    return issues, {}


def scan_permissions(home: Path) -> tuple[list[RepairIssue], dict]:
    """Check writability of key directories."""
    from oppie.instance import INSTANCE_DIRS

    issues: list[RepairIssue] = []
    unwritable = []

    for d in INSTANCE_DIRS:
        dir_path = home / d
        if dir_path.exists() and not os.access(dir_path, os.W_OK):
            unwritable.append(d)

    if unwritable:
        issues.append(
            RepairIssue(
                'Permission errors',
                f'{len(unwritable)} directory(ies) not writable:'
                f' {", ".join(unwritable)}',
                fixable=False,
                detail='Fix with: chmod u+w '
                + ' '.join(str(home / d) for d in unwritable),
            )
        )

    return issues, {}


def scan_all(home: Path) -> tuple[list[RepairIssue], dict]:
    """Run all repair scans. Return (issues, combined_context)."""
    all_issues: list[RepairIssue] = []
    combined_ctx: dict = {}

    for scan_fn, key in [
        (scan_run_log, 'run_log'),
        (scan_tickets, 'tickets'),
        (scan_plan_index, 'plan_index'),
        (scan_sqlite, 'sqlite'),
        (scan_permissions, 'permissions'),
    ]:
        issues, ctx = scan_fn(home)
        all_issues.extend(issues)
        combined_ctx[key] = ctx

    return all_issues, combined_ctx


def repair_run_log(home: Path, ctx: dict) -> RepairResult:
    """Rewrite run log with only valid lines (fixes malformed + dead refs)."""
    import tempfile

    log_path = ctx['log_path']
    valid_lines = ctx['valid_lines']

    fd, tmp = tempfile.mkstemp(dir=log_path.parent, suffix='.tmp')
    try:
        with open(fd, 'w') as f:
            for line in valid_lines:
                f.write(line + '\n')
        Path(tmp).replace(log_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    return RepairResult('Run log', True, 'rewritten with valid entries only')


def repair_ticket_versions(home: Path, ctx: dict) -> RepairResult:
    """Add schema_version to tickets missing it."""
    import tempfile

    fixed = 0
    for path in ctx['missing_version']:
        data = json.loads(path.read_text())
        data['schema_version'] = SCHEMA_VERSION

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                json.dump(data, f, indent=2)
                f.write('\n')
            Path(tmp).replace(path)
            fixed += 1
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    return RepairResult(
        'Ticket versions', True, f'added schema_version to {fixed} ticket(s)'
    )


def repair_plan_index(home: Path, ctx: dict) -> RepairResult:
    """Rebuild plan index by deleting it and triggering auto-rebuild."""
    from oppie.plan.engine import _load_plan_index

    plans_dir = ctx['plans_dir']
    index_path = plans_dir / PLAN_INDEX_FILENAME
    if index_path.exists():
        index_path.unlink()
    entries = _load_plan_index(plans_dir)
    return RepairResult('Plan index', True, f'rebuilt with {len(entries)} entries')


def apply_repairs(
    home: Path, issues: list[RepairIssue], ctx: dict
) -> list[RepairResult]:
    """Apply all fixable repairs. Return results."""
    results: list[RepairResult] = []

    fixable_names = {issue.name for issue in issues if issue.fixable}

    # Run log repairs (covers both malformed entries and dead artifact refs)
    run_log_fixes = {'Malformed run log entries', 'Invalid artifact references'}
    if fixable_names & run_log_fixes:
        results.append(repair_run_log(home, ctx['run_log']))

    if 'Missing schema_version' in fixable_names:
        results.append(repair_ticket_versions(home, ctx['tickets']))

    if 'Stale plan index' in fixable_names:
        results.append(repair_plan_index(home, ctx['plan_index']))

    return results
