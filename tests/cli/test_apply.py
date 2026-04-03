import json

from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.session import Session
from tests.cli.conftest import make_and_save_plan, setup_cli_instance
from tests.helpers import make_ticket, write_ticket


def test_apply_happy_path(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='y\n'
    )

    assert result.exit_code == 0
    assert 'ok' in result.output
    assert 'All operations applied successfully' in result.output


def test_apply_defaults_to_session_plan(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    session = Session.create(home)
    session.set_active_plan(plan.plan_id)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply'], input='y\n')

    assert result.exit_code == 0
    assert 'All operations applied successfully' in result.output


def test_apply_no_plan_id_no_session(tmp_path):
    home = setup_cli_instance(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply'])

    assert result.exit_code == 1
    assert 'No plan specified' in result.output


def test_apply_plan_not_found(tmp_path):
    home = setup_cli_instance(tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply', 'nonexistent'])

    assert result.exit_code == 1
    assert 'Plan not found' in result.output


def test_apply_integrity_failure(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    make_and_save_plan(home, ops)

    # Tamper with plan file
    plan_id = Plan.compute_id(ops)
    plan_path = home / 'artifacts' / 'plans' / f'plan-{plan_id}.json'
    data = json.loads(plan_path.read_text())
    data['plan_id'] = 'tampered'
    tampered_path = home / 'artifacts' / 'plans' / 'plan-tampered.json'
    tampered_path.write_text(json.dumps(data, indent=2) + '\n')

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply', 'tampered'])

    assert result.exit_code == 1
    assert 'modified since creation' in result.output
    assert 'amend' in result.output


def test_apply_already_applied(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, status=PlanStatus.APPLIED, checked=True)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply', plan.plan_id])

    assert result.exit_code == 1
    assert 'already applied' in result.output


def test_apply_deleted_ticket(tmp_path):
    home = setup_cli_instance(tmp_path)
    ops = [Operation('T-GONE', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply', plan.plan_id])

    # Capability check catches missing ticket before drift check
    assert result.exit_code == 1
    assert 'Ticket not found' in result.output or 'no longer exists' in result.output


def test_apply_force_mode(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', '--force', plan.plan_id], input='y\n'
    )

    assert result.exit_code == 0
    assert 'overwriting' in result.output
    assert 'All operations applied successfully' in result.output


def test_apply_critical_drift_keep_plan(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    # Choose 'a' (keep plan value), then 'y' (confirm apply)
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='a\ny\n'
    )

    assert result.exit_code == 0
    assert 'ok' in result.output


def test_apply_critical_drift_keep_current(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    # Choose 'b' (keep current), then 'y' (confirm apply)
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='b\ny\n'
    )

    assert result.exit_code == 0
    assert 'skipped' in result.output.lower()


def test_apply_critical_drift_skip_operation(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-1', 'priority', 'medium', 'high', 'escalate'),
    ]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    # Choose 'c' (skip entire operation for T-1), then 'y'
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='c\ny\n'
    )

    assert result.exit_code == 0
    # Both ops for T-1 should be skipped
    assert result.output.lower().count('skipped') >= 2


def test_apply_partial_failure(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    t1 = make_ticket('T-1', status='open')
    t2 = make_ticket('T-2', status='open')
    write_ticket(home, t1)
    write_ticket(home, t2)
    ops = [
        Operation('T-1', 'status', 'open', 'done', 'closing'),
        Operation('T-2', 'status', 'open', 'done', 'closing'),
    ]
    plan = make_and_save_plan(home, ops, checked=True)

    # Patch update_ticket to fail on T-2
    from oppie.providers.local.provider import LocalProvider

    original_update = LocalProvider.update_ticket

    def failing_update(self, ticket_id, updates):
        if ticket_id == 'T-2':
            raise RuntimeError('Simulated API error')
        return original_update(self, ticket_id, updates)

    monkeypatch.setattr(LocalProvider, 'update_ticket', failing_update)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='y\n'
    )

    assert result.exit_code == 0
    assert 'FAILED' in result.output
    assert 'partially failed' in result.output


def test_apply_user_cancels(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='n\n'
    )

    assert result.exit_code == 0
    assert 'cancelled' in result.output.lower()


def test_apply_writes_drift_artifact(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='in_progress')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='a\ny\n'
    )

    assert result.exit_code == 0

    # Drift report written via ArtifactStore — find it in applies dir
    applies_dir = home / 'artifacts' / 'applies'
    artifact_files = list(applies_dir.glob('apply-*.json'))
    drift_artifacts = [f for f in artifact_files if 'drift_report' in f.read_text()]

    assert len(drift_artifacts) >= 1
    content = json.loads(drift_artifacts[0].read_text())
    assert content['plan_id'] == plan.plan_id
    assert content['type'] == 'drift_report'


def test_apply_stats_line(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='y\n'
    )

    assert result.exit_code == 0
    assert '1/1 ops' in result.output


def test_apply_informational_drift(tmp_path):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open', priority='high')
    write_ticket(home, ticket)
    snapshot_ticket = make_ticket('T-1', status='open', priority='medium')
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(
        home, ops, checked=True, ticket_snapshots={'T-1': snapshot_ticket}
    )

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), 'apply', plan.plan_id], input='y\n'
    )

    assert result.exit_code == 0
    assert 'Informational drift' in result.output
    assert 'All operations applied successfully' in result.output
