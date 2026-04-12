import json
import os
import sqlite3

import yaml

from oppie.health import (
    CheckStatus,
    apply_repairs,
    check_artifacts,
    check_config,
    check_extras,
    check_llm_connectivity,
    check_missing_deps,
    check_outbox,
    check_provider_connectivity,
    check_run_log,
    check_state_cache,
    check_tickets,
    repair_plan_index,
    repair_run_log,
    repair_ticket_versions,
    scan_all,
    scan_permissions,
    scan_plan_index,
    scan_run_log,
    scan_sqlite,
    scan_tickets,
)
from oppie.models.plan import PLAN_INDEX_FILENAME
from tests.helpers import make_ticket, setup_instance, write_ticket


def _setup_config(home):
    """Write minimal valid config files."""
    config_dir = home / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / 'oppie.yaml').write_text(
        yaml.dump(
            {
                'instance_type': 'repo',
                'provider': {'type': 'local'},
                'llm': {'backend': 'openai-compatible', 'model': 'test'},
            }
        )
    )


def _setup_full_artifacts(home):
    """Ensure all artifact subdirs exist."""
    for sub in ['ask', 'plans', 'applies', 'reports', 'context']:
        (home / 'artifacts' / sub).mkdir(parents=True, exist_ok=True)


# --- check_config ---


def test_check_config_valid(tmp_path):
    home = setup_instance(tmp_path)
    _setup_config(home)

    result = check_config(home)

    assert result.status == CheckStatus.OK


def test_check_config_missing(tmp_path):
    home = setup_instance(tmp_path)

    result = check_config(home)

    assert result.status == CheckStatus.FAILED
    assert 'not found' in result.message.lower()


def test_check_config_invalid(tmp_path):
    home = setup_instance(tmp_path)
    config_dir = home / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / 'oppie.yaml').write_text('invalid: yaml: content: [')

    result = check_config(home)

    assert result.status == CheckStatus.FAILED


# --- check_state_cache ---


def test_check_state_cache_ok(tmp_path):
    home = setup_instance(tmp_path)

    result = check_state_cache(home)

    assert result.status == CheckStatus.OK


def test_check_state_cache_missing(tmp_path):
    home = tmp_path

    result = check_state_cache(home)

    assert result.status == CheckStatus.FAILED
    assert 'missing' in result.message


# --- check_tickets ---


def test_check_tickets_ok(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1')
    write_ticket(home, ticket)

    result = check_tickets(home)

    assert result.status == CheckStatus.OK
    assert '1 tickets' in result.message


def test_check_tickets_empty(tmp_path):
    home = setup_instance(tmp_path)

    result = check_tickets(home)

    assert result.status == CheckStatus.OK
    assert '0 tickets' in result.message


def test_check_tickets_corrupt(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'tickets' / 'BAD-1.json').write_text('not json at all')

    result = check_tickets(home)

    assert result.status == CheckStatus.FAILED
    assert 'corrupt' in result.message.lower()


# --- check_outbox ---


def test_check_outbox_na_local(tmp_path):
    home = setup_instance(tmp_path)

    result = check_outbox(home, provider=object())

    assert result.status == CheckStatus.NA


def test_check_outbox_na_none(tmp_path):
    home = setup_instance(tmp_path)

    result = check_outbox(home, provider=None)

    assert result.status == CheckStatus.NA


def test_check_outbox_ok_no_file(tmp_path):
    home = setup_instance(tmp_path)

    class FakeExternal:
        pass

    # Verify NA for non-ExternalProvider
    result = check_outbox(home, provider=FakeExternal())

    assert result.status == CheckStatus.NA


def test_check_outbox_pending(tmp_path, monkeypatch):
    home = setup_instance(tmp_path)
    outbox_dir = home / 'state' / 'linear'
    outbox_dir.mkdir(parents=True, exist_ok=True)
    (outbox_dir / 'outbox.jsonl').write_text('{"op": "test"}\n{"op": "test2"}\n')

    from oppie.providers.base import ExternalProvider

    monkeypatch.setattr(
        'oppie.health.ExternalProvider', ExternalProvider, raising=False
    )

    # Create a mock that passes isinstance check
    class MockExternal(ExternalProvider):
        @property
        def home(self):
            return tmp_path

        @property
        def capabilities(self):
            return None

        @property
        def version(self):
            return 'v1'

        def read_ticket(self, ticket_id):
            return None

        def update_ticket(self, ticket_id, updates):
            return None

        def list_tickets(self):
            return []

        def sync(self, checkpoint=None):
            return None

        def apply(self, operations):
            return []

        def test_connection(self):
            pass

        def flush_outbox(self):
            return []

    result = check_outbox(home, provider=MockExternal())

    assert result.status == CheckStatus.WARNING
    assert '2' in result.message


# --- check_artifacts ---


def test_check_artifacts_ok(tmp_path):
    home = setup_instance(tmp_path)
    _setup_full_artifacts(home)

    result = check_artifacts(home)

    assert result.status == CheckStatus.OK


def test_check_artifacts_missing(tmp_path):
    home = tmp_path

    result = check_artifacts(home)

    assert result.status == CheckStatus.FAILED
    assert 'missing' in result.message


def test_check_artifacts_not_writable(tmp_path, monkeypatch):
    home = setup_instance(tmp_path)
    _setup_full_artifacts(home)

    original_access = os.access

    def _mock_access(path, mode):
        if 'plans' in str(path) and mode == os.W_OK:
            return False
        return original_access(path, mode)

    monkeypatch.setattr('os.access', _mock_access)

    result = check_artifacts(home)

    assert result.status == CheckStatus.FAILED
    assert 'plans' in result.message


# --- check_run_log ---


def test_check_run_log_ok(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\n'
    )

    result = check_run_log(home)

    assert result.status == CheckStatus.OK
    assert '1 entries' in result.message


def test_check_run_log_empty(tmp_path):
    home = setup_instance(tmp_path)

    result = check_run_log(home)

    assert result.status == CheckStatus.OK
    assert '0 entries' in result.message


def test_check_run_log_malformed(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\n'
        'not json\n'
        'also bad\n'
    )

    result = check_run_log(home)

    assert result.status == CheckStatus.WARNING
    assert '2' in result.message


# --- check_provider_connectivity ---


def test_check_provider_connectivity_na(tmp_path):
    from oppie.providers.local import LocalProvider

    home = setup_instance(tmp_path)
    provider = LocalProvider(home)

    result = check_provider_connectivity(provider)

    assert result.status == CheckStatus.NA
    provider.close()


def test_check_provider_connectivity_none():
    result = check_provider_connectivity(None)

    assert result.status == CheckStatus.FAILED
    assert 'failed to initialize' in result.message


def test_check_provider_connectivity_ok(monkeypatch):
    from oppie.providers.base import ExternalProvider

    class MockExternal(ExternalProvider):
        @property
        def home(self):
            return None

        @property
        def capabilities(self):
            return None

        @property
        def version(self):
            return 'v1'

        def read_ticket(self, ticket_id):
            return None

        def update_ticket(self, ticket_id, updates):
            return None

        def list_tickets(self):
            return []

        def sync(self, checkpoint=None):
            return None

        def apply(self, operations):
            return []

        def test_connection(self):
            pass

        def flush_outbox(self):
            return []

    result = check_provider_connectivity(MockExternal())

    assert result.status == CheckStatus.OK


def test_check_provider_connectivity_failed(monkeypatch):
    from oppie.providers.base import ExternalProvider

    class MockExternal(ExternalProvider):
        @property
        def home(self):
            return None

        @property
        def capabilities(self):
            return None

        @property
        def version(self):
            return 'v1'

        def read_ticket(self, ticket_id):
            return None

        def update_ticket(self, ticket_id, updates):
            return None

        def list_tickets(self):
            return []

        def sync(self, checkpoint=None):
            return None

        def apply(self, operations):
            return []

        def test_connection(self):
            raise ConnectionError('network down')

        def flush_outbox(self):
            return []

    result = check_provider_connectivity(MockExternal())

    assert result.status == CheckStatus.FAILED
    assert 'network down' in result.message


# --- check_llm_connectivity ---


def test_check_llm_connectivity_not_configured(monkeypatch):
    from oppie.llm import LLMNotConfiguredError

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = check_llm_connectivity(None)

    assert result.status == CheckStatus.NA


def test_check_llm_connectivity_ok(monkeypatch):
    class MockLLM:
        async def test_connection(self):
            return True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr('oppie.llm.create_llm_provider', lambda cfg: MockLLM())

    class FakeConfig:
        llm = 'something'

    result = check_llm_connectivity(FakeConfig())

    assert result.status == CheckStatus.OK


def test_check_llm_connectivity_failed(monkeypatch):
    class MockLLM:
        async def test_connection(self):
            raise ConnectionError('timeout')

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr('oppie.llm.create_llm_provider', lambda cfg: MockLLM())

    class FakeConfig:
        llm = 'something'

    result = check_llm_connectivity(FakeConfig())

    assert result.status == CheckStatus.FAILED
    assert 'timeout' in result.message


# --- check_extras ---


def test_check_extras(monkeypatch):
    monkeypatch.setattr(
        'oppie.cli.extras.extras_available',
        lambda: {'linear': True, 'llm': True, 'tui': False},
    )

    result = check_extras()

    assert result.status == CheckStatus.OK
    assert 'linear' in result.message
    assert 'tui' in result.message


# --- check_missing_deps ---


def test_check_missing_deps_ok(monkeypatch):
    monkeypatch.setattr(
        'oppie.cli.extras.extras_available',
        lambda: {'linear': True, 'llm': True, 'tui': True},
    )

    result = check_missing_deps(None)

    assert result.status == CheckStatus.OK


def test_check_missing_deps_warning(tmp_path, monkeypatch):
    _setup_config(tmp_path)

    monkeypatch.setattr(
        'oppie.cli.extras.extras_available',
        lambda: {'linear': True, 'llm': False, 'tui': True},
    )

    from oppie.config import load_config

    config = load_config(tmp_path / 'config')

    result = check_missing_deps(config)

    assert result.status == CheckStatus.WARNING
    assert 'LLM' in result.message


# --- scan_run_log ---


def test_scan_run_log_clean(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\n'
    )

    issues, ctx = scan_run_log(home)

    assert len(issues) == 0


def test_scan_run_log_malformed(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\nbad line\n'
    )

    issues, ctx = scan_run_log(home)

    assert len(issues) == 1
    assert issues[0].name == 'Malformed run log entries'
    assert issues[0].fixable is True


def test_scan_run_log_dead_refs(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    entry = json.dumps(
        {
            'run_id': 'r1',
            'command': 'plan',
            'timestamp': 't',
            'duration': 1,
            'artifact_paths': ['artifacts/plans/nonexistent.json'],
        }
    )
    log_path.write_text(entry + '\n')

    issues, ctx = scan_run_log(home)

    assert len(issues) == 1
    assert issues[0].name == 'Invalid artifact references'
    assert issues[0].fixable is True


def test_scan_run_log_no_file(tmp_path):
    home = setup_instance(tmp_path)

    issues, ctx = scan_run_log(home)

    assert len(issues) == 0


# --- scan_tickets ---


def test_scan_tickets_clean(tmp_path):
    home = setup_instance(tmp_path)
    ticket = make_ticket('T-1')
    write_ticket(home, ticket)

    issues, ctx = scan_tickets(home)

    assert len(issues) == 0


def test_scan_tickets_missing_version(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'tickets' / 'T-1.json').write_text(
        json.dumps({'id': 'T-1', 'title': 'test'})
    )

    issues, ctx = scan_tickets(home)

    assert len(issues) == 1
    assert issues[0].name == 'Missing schema_version'
    assert issues[0].fixable is True


def test_scan_tickets_corrupt(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'tickets' / 'BAD.json').write_text('not json')

    issues, ctx = scan_tickets(home)

    assert len(issues) == 1
    assert issues[0].name == 'Corrupt ticket JSON'
    assert issues[0].fixable is False


def test_scan_tickets_both(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'tickets' / 'T-1.json').write_text(json.dumps({'id': 'T-1'}))
    (home / 'tickets' / 'BAD.json').write_text('not json')

    issues, ctx = scan_tickets(home)

    assert len(issues) == 2
    names = {i.name for i in issues}

    assert 'Missing schema_version' in names
    assert 'Corrupt ticket JSON' in names


# --- scan_plan_index ---


def test_scan_plan_index_ok(tmp_path):
    home = setup_instance(tmp_path)
    plans_dir = home / 'artifacts' / 'plans'
    plan_data = {
        'plan_id': 'abc123',
        'instruction': 'test',
        'operations': [],
        'risks': [],
        'created_at': '2026-01-01T00:00:00Z',
        'status': 'saved',
    }
    (plans_dir / 'plan-abc123.json').write_text(json.dumps(plan_data))
    index_entry = json.dumps(
        {
            'plan_id': 'abc123',
            'instruction': 'test',
            'created_at': '2026-01-01T00:00:00Z',
        }
    )
    (plans_dir / PLAN_INDEX_FILENAME).write_text(index_entry + '\n')

    issues, ctx = scan_plan_index(home)

    assert len(issues) == 0


def test_scan_plan_index_stale(tmp_path):
    home = setup_instance(tmp_path)
    plans_dir = home / 'artifacts' / 'plans'
    plan_data = {
        'plan_id': 'abc123',
        'instruction': 'test',
        'operations': [],
        'risks': [],
        'created_at': '2026-01-01T00:00:00Z',
        'status': 'saved',
    }
    (plans_dir / 'plan-abc123.json').write_text(json.dumps(plan_data))
    # No index or empty index
    (plans_dir / PLAN_INDEX_FILENAME).write_text('')

    issues, ctx = scan_plan_index(home)

    assert len(issues) == 1
    assert issues[0].name == 'Stale plan index'
    assert issues[0].fixable is True


def test_scan_plan_index_no_plans(tmp_path):
    home = setup_instance(tmp_path)

    issues, ctx = scan_plan_index(home)

    assert len(issues) == 0


# --- scan_sqlite ---


def test_scan_sqlite_ok(tmp_path):
    home = setup_instance(tmp_path)
    db_path = home / 'state' / 'cache.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.execute('CREATE TABLE tickets (id TEXT)')
    conn.close()

    issues, ctx = scan_sqlite(home)

    assert len(issues) == 0


def test_scan_sqlite_corrupt(tmp_path):
    home = setup_instance(tmp_path)
    db_path = home / 'state' / 'cache.sqlite'
    db_path.write_text('this is not a sqlite database')

    issues, ctx = scan_sqlite(home)

    assert len(issues) == 1
    assert issues[0].name == 'SQLite corruption'
    assert issues[0].fixable is False


def test_scan_sqlite_missing_table(tmp_path):
    home = setup_instance(tmp_path)
    db_path = home / 'state' / 'cache.sqlite'
    conn = sqlite3.connect(str(db_path))
    conn.close()

    issues, ctx = scan_sqlite(home)

    assert len(issues) == 1
    assert issues[0].name == 'SQLite corruption'


def test_scan_sqlite_no_file(tmp_path):
    home = setup_instance(tmp_path)

    issues, ctx = scan_sqlite(home)

    assert len(issues) == 0


# --- scan_permissions ---


def test_scan_permissions_ok(tmp_path):
    home = setup_instance(tmp_path)

    issues, ctx = scan_permissions(home)

    assert len(issues) == 0


def test_scan_permissions_unwritable(tmp_path, monkeypatch):
    home = setup_instance(tmp_path)

    monkeypatch.setattr('os.access', lambda path, mode: 'state' not in str(path))

    issues, ctx = scan_permissions(home)

    assert len(issues) == 1
    assert issues[0].name == 'Permission errors'
    assert issues[0].fixable is False


# --- scan_all ---


def test_scan_all_clean(tmp_path):
    home = setup_instance(tmp_path)

    issues, ctx = scan_all(home)

    assert len(issues) == 0


def test_scan_all_with_issues(tmp_path):
    home = setup_instance(tmp_path)
    (home / 'tickets' / 'BAD.json').write_text('not json')
    (home / 'logs' / 'runs.jsonl').write_text('bad line\n')

    issues, ctx = scan_all(home)

    assert len(issues) >= 2


# --- repair_run_log ---


def test_repair_run_log(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\nbad line\n'
    )

    issues, ctx = scan_run_log(home)
    result = repair_run_log(home, ctx)

    assert result.success is True
    repaired = log_path.read_text().splitlines()
    assert len(repaired) == 1
    assert json.loads(repaired[0])['run_id'] == 'r1'


def test_repair_run_log_dead_refs(tmp_path):
    home = setup_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    entry = json.dumps(
        {
            'run_id': 'r1',
            'command': 'plan',
            'timestamp': 't',
            'duration': 1,
            'artifact_paths': ['artifacts/plans/nonexistent.json', 'logs/runs.jsonl'],
        }
    )
    log_path.write_text(entry + '\n')

    issues, ctx = scan_run_log(home)
    result = repair_run_log(home, ctx)

    assert result.success is True
    repaired_entry = json.loads(log_path.read_text().strip())
    # Only the existing path should remain
    assert repaired_entry['artifact_paths'] == ['logs/runs.jsonl']


# --- repair_ticket_versions ---


def test_repair_ticket_versions(tmp_path):
    home = setup_instance(tmp_path)
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_path.write_text(json.dumps({'id': 'T-1', 'title': 'test'}))

    issues, ctx = scan_tickets(home)
    result = repair_ticket_versions(home, ctx)

    assert result.success is True
    repaired = json.loads(ticket_path.read_text())
    assert repaired['schema_version'] == 'v1'


# --- repair_plan_index ---


def test_repair_plan_index(tmp_path):
    home = setup_instance(tmp_path)
    plans_dir = home / 'artifacts' / 'plans'
    plan_data = {
        'plan_id': 'abc123',
        'instruction': 'test',
        'operations': [],
        'risks': [],
        'created_at': '2026-01-01T00:00:00Z',
        'status': 'saved',
    }
    (plans_dir / 'plan-abc123.json').write_text(json.dumps(plan_data))
    # Empty stale index
    (plans_dir / PLAN_INDEX_FILENAME).write_text('')

    issues, ctx = scan_plan_index(home)
    result = repair_plan_index(home, ctx)

    assert result.success is True
    assert '1 entries' in result.message
    # Verify index was rebuilt
    index_content = (plans_dir / PLAN_INDEX_FILENAME).read_text().strip()
    index_entry = json.loads(index_content)
    assert index_entry['plan_id'] == 'abc123'


# --- apply_repairs ---


def test_apply_repairs_combined(tmp_path):
    home = setup_instance(tmp_path)

    # Set up malformed run log
    (home / 'logs' / 'runs.jsonl').write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\nbad\n'
    )

    # Set up ticket missing version
    (home / 'tickets' / 'T-1.json').write_text(json.dumps({'id': 'T-1'}))

    issues, ctx = scan_all(home)
    fixable = [i for i in issues if i.fixable]

    assert len(fixable) >= 2

    results = apply_repairs(home, issues, ctx)

    assert len(results) >= 2
    assert all(r.success for r in results)
