from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.operation import Operation
from oppie.session import Session
from tests.cli.conftest import make_and_save_plan, setup_cli_instance
from tests.helpers import make_ticket, write_ticket


def test_prompt_no_instance(tmp_path):
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(tmp_path), 'what is blocking?'])

    assert result.exit_code != 0
    assert 'No oppie instance' in result.output


def test_prompt_ambiguous():
    """Single word with no clear intent shows ambiguous error."""
    runner = CliRunner()

    with patch('oppie.instance.Instance') as mock_instance_cls:
        mock_instance_cls.detect.return_value = '/fake/home'
        mock_instance_cls.load.return_value = MagicMock(config=None)

        with patch('oppie.providers.local.LocalProvider') as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.list_tickets.return_value = []
            mock_provider_cls.setup.return_value = mock_provider

            with patch('oppie.sync.auto_sync') as mock_sync:
                mock_sync.return_value = MagicMock(
                    synced=False, error=None, ticket_count=0
                )

                result = runner.invoke(cli, ['bugs'])

    assert result.exit_code != 0
    assert 'Could not determine intent' in result.output


def test_prompt_ambiguous_shows_apply_hint():
    """Ambiguous error message includes apply hint."""
    runner = CliRunner()

    with patch('oppie.instance.Instance') as mock_instance_cls:
        mock_instance_cls.detect.return_value = '/fake/home'
        mock_instance_cls.load.return_value = MagicMock(config=None)

        with patch('oppie.providers.local.LocalProvider') as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.list_tickets.return_value = []
            mock_provider_cls.setup.return_value = mock_provider

            with patch('oppie.sync.auto_sync') as mock_sync:
                mock_sync.return_value = MagicMock(
                    synced=False, error=None, ticket_count=0
                )

                result = runner.invoke(cli, ['bugs'])

    assert 'apply plan' in result.output


def test_prompt_apply_no_active_plan(tmp_path):
    """Apply intent with no active plan shows error."""
    home = setup_cli_instance(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(home), 'apply it'])

    assert result.exit_code != 0
    assert 'No active plan' in result.output


def test_prompt_apply_plan_not_found(tmp_path):
    """Apply intent with nonexistent plan ID shows error."""
    home = setup_cli_instance(tmp_path)
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(home), 'apply plan-deadbeef'])

    assert result.exit_code != 0
    assert 'Plan not found' in result.output


def test_prompt_apply_with_plan_id(tmp_path):
    """Apply intent with plan_id in prompt loads and applies the plan."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), f'apply plan-{plan.plan_id}'], input='y\n'
    )

    assert result.exit_code == 0
    assert 'All operations applied successfully' in result.output


def test_prompt_apply_from_session(tmp_path):
    """Apply intent falls back to session active plan."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    session = Session.create(home)
    session.set_active_plan(plan.plan_id)

    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'apply it'], input='y\n')

    assert result.exit_code == 0
    assert 'All operations applied successfully' in result.output


def test_prompt_apply_cancelled(tmp_path):
    """Apply intent with user declining confirmation."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli, ['--home', str(home), f'apply plan-{plan.plan_id}'], input='n\n'
    )

    assert 'Apply cancelled' in result.output


def test_prompt_apply_force_flag(tmp_path):
    """Force flag is extracted from prompt text."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), f'apply plan-{plan.plan_id} --force'],
        input='y\n',
    )

    assert result.exit_code == 0
