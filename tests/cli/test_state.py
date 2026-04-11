from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.run_log import RunLog, RunLogEntry
from tests.cli.conftest import setup_cli_instance


def test_state_show_empty(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'state', 'show'])

    assert result.exit_code == 0
    assert 'Instance' in result.output
    assert 'Path:' in result.output
    assert 'Tickets:  0' in result.output
    assert 'Plans:    0' in result.output


def test_state_show_with_data(tmp_path):
    home = setup_cli_instance(tmp_path)

    # Add a ticket
    tickets_dir = home / 'tickets'
    tickets_dir.mkdir(parents=True, exist_ok=True)
    (tickets_dir / 'TICK-1.json').write_text('{}')

    # Add a plan
    op = Operation(
        ticket_id='TICK-1',
        field='priority',
        before_value='low',
        after_value='high',
        rationale='test',
    )
    plan = Plan(
        instruction='test',
        operations=[op],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)

    # Add a run log entry
    run_log = RunLog(home)
    run_log.append(
        RunLogEntry(
            run_id='run-0001',
            command='plan',
            timestamp='2026-01-01T00:00:00Z',
            duration=1.0,
        )
    )

    result = CliRunner().invoke(cli, ['--home', str(home), 'state', 'show'])

    assert result.exit_code == 0
    assert 'Tickets:  1' in result.output
    assert 'Plans:    1' in result.output
    assert 'Runs:     1' in result.output


def test_state_show_excludes_plan_index(tmp_path):
    home = setup_cli_instance(tmp_path)

    # Save a plan (this also creates .plan-index.jsonl)
    op = Operation(
        ticket_id='TICK-1',
        field='priority',
        before_value='low',
        after_value='high',
        rationale='test',
    )
    plan = Plan(
        instruction='test',
        operations=[op],
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=PlanStatus.SAVED,
    )
    plan.save(home)

    result = CliRunner().invoke(cli, ['--home', str(home), 'state', 'show'])

    assert result.exit_code == 0
    # Should be 1 plan, not 2 (excluding .plan-index.jsonl)
    assert 'Plans:    1' in result.output


def test_state_show_provider_type(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'state', 'show'])

    assert result.exit_code == 0
    assert 'Provider: local' in result.output
