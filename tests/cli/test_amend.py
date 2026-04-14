from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.session import Session
from tests.cli.conftest import make_and_save_plan, setup_cli_instance
from tests.helpers import make_ticket, write_ticket


def _new_amended_plan(parent_id: str) -> Plan:
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='open',
        after_value='done',
        rationale='still closing',
    )
    plan = Plan(
        instruction='test instruction',
        operations=[op],
        risks=[],
        created_at=datetime.now(UTC).isoformat(),
        status=PlanStatus.SAVED,
        parent_plan_id=parent_id,
    )
    return plan


def test_amend_happy_path_saves_and_sets_active(tmp_path):
    home = setup_cli_instance(tmp_path)
    write_ticket(home, make_ticket('T-1', status='open'))
    original = make_and_save_plan(
        home, [Operation('T-1', 'status', 'open', 'done', 'closing')]
    )
    amended = _new_amended_plan(original.plan_id)

    with patch(
        'oppie.cli.commands.amend.amend_plan', new_callable=AsyncMock
    ) as mock_amend:
        mock_amend.return_value = amended
        result = CliRunner().invoke(
            cli, ['--home', str(home), 'amend', original.plan_id], input='y\n'
        )

    assert result.exit_code == 0, result.output
    assert f'Amended plan (based on {original.plan_id})' in result.output
    assert 'Plan saved' in result.output
    session = Session.load_latest(home)

    assert session is not None
    assert session.get_active_plan() == amended.plan_id


def test_amend_missing_plan_id(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'amend', 'nonexistent'])

    assert result.exit_code != 0
    assert 'Plan not found' in result.output


def test_amend_discard_does_not_set_active(tmp_path):
    home = setup_cli_instance(tmp_path)
    write_ticket(home, make_ticket('T-1', status='open'))
    original = make_and_save_plan(
        home, [Operation('T-1', 'status', 'open', 'done', 'closing')]
    )
    amended = _new_amended_plan(original.plan_id)

    with patch(
        'oppie.cli.commands.amend.amend_plan', new_callable=AsyncMock
    ) as mock_amend:
        mock_amend.return_value = amended
        result = CliRunner().invoke(
            cli, ['--home', str(home), 'amend', original.plan_id], input='n\n'
        )

    assert result.exit_code == 0, result.output
    assert 'Plan discarded.' in result.output
    session = Session.load_latest(home)

    assert session is None or session.get_active_plan() != amended.plan_id


def test_amend_already_applied_declines_continue(tmp_path):
    home = setup_cli_instance(tmp_path)
    write_ticket(home, make_ticket('T-1', status='done'))
    original = make_and_save_plan(
        home,
        [Operation('T-1', 'status', 'open', 'done', 'closing')],
        status=PlanStatus.APPLIED,
    )

    with patch(
        'oppie.cli.commands.amend.amend_plan', new_callable=AsyncMock
    ) as mock_amend:
        result = CliRunner().invoke(
            cli, ['--home', str(home), 'amend', original.plan_id], input='n\n'
        )

        assert result.exit_code == 0
        assert 'already applied' in result.output
        mock_amend.assert_not_called()
