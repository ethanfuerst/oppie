import json

from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.plan import PLAN_INDEX_FILENAME
from tests.cli.conftest import setup_cli_instance


def test_repair_no_issues(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'])

    assert result.exit_code == 0
    assert 'No issues found' in result.output


def test_repair_dry_run(tmp_path):
    home = setup_cli_instance(tmp_path)
    (home / 'logs' / 'runs.jsonl').write_text('bad line\n')

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair', '--dry-run'])

    assert result.exit_code == 0
    assert 'Dry run' in result.output
    # File should NOT be modified
    assert (home / 'logs' / 'runs.jsonl').read_text() == 'bad line\n'


def test_repair_confirm_yes(tmp_path):
    home = setup_cli_instance(tmp_path)
    (home / 'logs' / 'runs.jsonl').write_text('bad line\n')

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    assert 'Run log' in result.output
    # Bad line should be gone
    assert (home / 'logs' / 'runs.jsonl').read_text().strip() == ''


def test_repair_confirm_no(tmp_path):
    home = setup_cli_instance(tmp_path)
    (home / 'logs' / 'runs.jsonl').write_text('bad line\n')

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='n\n')

    assert result.exit_code == 0
    # File should NOT be modified
    assert (home / 'logs' / 'runs.jsonl').read_text() == 'bad line\n'


def test_repair_malformed_run_log(tmp_path):
    home = setup_cli_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\nbad line\n'
    )

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    repaired = log_path.read_text().splitlines()
    assert len(repaired) == 1
    assert json.loads(repaired[0])['run_id'] == 'r1'


def test_repair_missing_schema_version(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket_path = home / 'tickets' / 'T-1.json'
    ticket_path.write_text(json.dumps({'id': 'T-1', 'title': 'test'}))

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    repaired = json.loads(ticket_path.read_text())
    assert repaired['schema_version'] == 'v1'


def test_repair_stale_plan_index(tmp_path):
    home = setup_cli_instance(tmp_path)
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
    (plans_dir / PLAN_INDEX_FILENAME).write_text('')

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    assert 'Plan index' in result.output
    index_content = (plans_dir / PLAN_INDEX_FILENAME).read_text().strip()
    assert 'abc123' in index_content


def test_repair_dead_artifact_refs(tmp_path):
    home = setup_cli_instance(tmp_path)
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

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    repaired_entry = json.loads(log_path.read_text().strip())
    assert repaired_entry['artifact_paths'] == []


def test_repair_unfixable_reported(tmp_path):
    home = setup_cli_instance(tmp_path)
    (home / 'tickets' / 'BAD.json').write_text('not json')

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'])

    assert result.exit_code == 0
    assert 'unfixable' in result.output.lower()
    assert 'Corrupt ticket JSON' in result.output


def test_repair_combined(tmp_path):
    home = setup_cli_instance(tmp_path)

    # Malformed run log
    (home / 'logs' / 'runs.jsonl').write_text(
        '{"run_id":"r1","command":"plan","timestamp":"t","duration":1}\nbad\n'
    )

    # Ticket missing schema_version
    (home / 'tickets' / 'T-1.json').write_text(json.dumps({'id': 'T-1'}))

    result = CliRunner().invoke(cli, ['--home', str(home), 'repair'], input='y\n')

    assert result.exit_code == 0
    assert 'Run log' in result.output
    assert 'Ticket versions' in result.output

    # Verify both repairs applied
    log_lines = (home / 'logs' / 'runs.jsonl').read_text().splitlines()
    assert len(log_lines) == 1

    ticket_data = json.loads((home / 'tickets' / 'T-1.json').read_text())
    assert ticket_data['schema_version'] == 'v1'
