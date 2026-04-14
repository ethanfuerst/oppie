from click.testing import CliRunner

from oppie.cli import cli
from oppie.run_log import RunLog, RunLogEntry
from tests.cli.conftest import setup_cli_instance


def _append_entries(home, count=3):
    run_log = RunLog(home)
    for i in range(count):
        run_log.append(
            RunLogEntry(
                run_id=f'run-{i:04d}',
                command='plan',
                timestamp=f'2026-01-{i + 1:02d}T00:00:00Z',
                duration=1.0 + i,
                plan_id=f'plan-{i:04d}',
            )
        )


def test_history_empty(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'history'])

    assert result.exit_code == 0
    assert 'No run history' in result.output


def test_history_shows_entries(tmp_path):
    home = setup_cli_instance(tmp_path)
    _append_entries(home, count=3)

    result = CliRunner().invoke(cli, ['--home', str(home), 'history'])

    assert result.exit_code == 0
    assert 'run-0000' in result.output
    assert 'plan' in result.output
    assert '2026-01-01' in result.output
    # Rich table headers are present
    assert 'Run' in result.output
    assert 'Command' in result.output
    assert 'Duration' in result.output


def test_history_limit(tmp_path):
    home = setup_cli_instance(tmp_path)
    _append_entries(home, count=10)

    result = CliRunner().invoke(cli, ['--home', str(home), 'history', '--limit', '3'])

    assert result.exit_code == 0
    assert 'Showing 3 of 10' in result.output
    # Should show last 3 entries (run-0007 through run-0009)
    assert 'run-0007' in result.output
    assert 'run-0009' in result.output
    # Should not show first entry
    assert 'run-0000' not in result.output


def test_history_default_limit_no_footer(tmp_path):
    home = setup_cli_instance(tmp_path)
    _append_entries(home, count=3)

    result = CliRunner().invoke(cli, ['--home', str(home), 'history'])

    assert result.exit_code == 0
    assert 'Showing' not in result.output
