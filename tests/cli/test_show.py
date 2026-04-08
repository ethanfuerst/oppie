from click.testing import CliRunner

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.cli import cli
from oppie.models.apply import ApplyResult, OperationResult, OperationStatus
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.run_log import generate_run_id
from tests.cli.conftest import setup_cli_instance


def _make_operation(ticket_id='TICK-1', field='priority', before='low', after='high'):
    return Operation(
        ticket_id=ticket_id,
        field=field,
        before_value=before,
        after_value=after,
        rationale='test rationale',
    )


def _save_plan(home, ops=None, status=PlanStatus.SAVED):
    ops = ops or [_make_operation()]
    plan = Plan(
        instruction='test instruction',
        operations=ops,
        risks=['risk one'],
        created_at='2026-01-01T00:00:00Z',
        status=status,
    )
    plan.save(home)
    return plan


def _save_apply(home, plan):
    result = ApplyResult(
        apply_id='apply-abc123',
        plan=plan,
        results=[
            OperationResult(operation=plan.operations[0], status=OperationStatus.OK)
        ],
        duration=1.5,
        created_at='2026-01-02T00:00:00Z',
    )
    store = ArtifactStore(home)
    run_id = generate_run_id()
    store.save_artifact(ArtifactType.APPLY, result.build_artifact(), run_id)
    return result


def test_show_plan(tmp_path):
    home = setup_cli_instance(tmp_path)
    plan = _save_plan(home)

    result = CliRunner().invoke(cli, ['--home', str(home), 'show', plan.plan_id])

    assert result.exit_code == 0
    assert plan.plan_id in result.output
    assert 'test instruction' in result.output
    assert 'TICK-1' in result.output
    assert 'risk one' in result.output


def test_show_plan_with_prefix(tmp_path):
    home = setup_cli_instance(tmp_path)
    plan = _save_plan(home)

    result = CliRunner().invoke(
        cli, ['--home', str(home), 'show', f'plan-{plan.plan_id}']
    )

    assert result.exit_code == 0
    assert plan.plan_id in result.output


def test_show_apply(tmp_path):
    home = setup_cli_instance(tmp_path)
    plan = _save_plan(home, status=PlanStatus.APPLIED)
    _save_apply(home, plan)

    result = CliRunner().invoke(cli, ['--home', str(home), 'show', 'apply-abc123'])

    assert result.exit_code == 0
    assert 'apply-abc123' in result.output
    assert plan.plan_id in result.output
    assert 'success' in result.output


def test_show_not_found(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'show', 'nonexistent'])

    assert result.exit_code == 1
    assert 'No plan or apply found' in result.output
    assert 'oppie history' in result.output


def test_show_apply_partial(tmp_path):
    home = setup_cli_instance(tmp_path)
    op = _make_operation()
    plan = _save_plan(home, ops=[op], status=PlanStatus.APPLIED)
    result_obj = ApplyResult(
        apply_id='apply-partial',
        plan=plan,
        results=[
            OperationResult(
                operation=op, status=OperationStatus.FAILED, error='timeout'
            )
        ],
        duration=2.0,
        created_at='2026-01-02T00:00:00Z',
    )
    store = ArtifactStore(home)
    store.save_artifact(
        ArtifactType.APPLY, result_obj.build_artifact(), generate_run_id()
    )

    result = CliRunner().invoke(cli, ['--home', str(home), 'show', 'apply-partial'])

    assert result.exit_code == 0
    assert 'partial' in result.output
    assert 'FAILED' in result.output
