import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from oppie.ask.engine import AskResult
from oppie.cli import cli
from oppie.events import AskResultEvent
from oppie.intent import Intent
from oppie.models.operation import Operation
from oppie.session import Session
from tests.cli.conftest import make_and_save_plan, setup_cli_instance
from tests.helpers import make_ticket, setup_instance, write_ticket


def test_prompt_no_instance(tmp_path):
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(tmp_path), 'what is blocking?'])

    assert result.exit_code != 0
    assert 'No oppie instance' in result.output


def test_prompt_requires_llm_config(tmp_path):
    """Prompt command fails without LLM config."""
    home = setup_instance(tmp_path)
    marker = {'version': '0.0.1', 'instance_type': 'repo'}
    (home / '.oppie-marker').write_text(json.dumps(marker, indent=2) + '\n')
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(home), 'what is blocking?'])

    assert result.exit_code != 0
    assert 'LLM is not configured' in result.output


async def _mock_ask_generator(*args, **kwargs):
    """Async generator that yields a single AskResultEvent."""
    yield AskResultEvent(
        result=AskResult(
            answer='I handle project management.',
            artifact_path=None,
            run_id='test-run',
            duration=1.0,
            usage=None,
        )
    )


def test_prompt_unmatched_routes_to_ask(tmp_path):
    """Unmatched prompts default to QUESTION and route to ask."""
    home = setup_cli_instance(tmp_path)
    runner = CliRunner()

    with patch(
        'oppie.cli.commands.prompt.classify_intent', new_callable=AsyncMock
    ) as mock_classify:
        mock_classify.return_value = Intent.QUESTION
        with patch(
            'oppie.cli.commands.prompt.generate_ask',
            side_effect=_mock_ask_generator,
        ) as mock_ask:
            result = runner.invoke(cli, ['--home', str(home), 'hello there'])

    assert result.exit_code == 0
    mock_ask.assert_called_once()


def _mock_classify_as_apply():
    """Patch classify_intent to return APPLY for apply tests."""
    mock = AsyncMock(return_value=Intent.APPLY)
    return patch('oppie.cli.commands.prompt.classify_intent', mock)


def test_prompt_apply_no_active_plan(tmp_path):
    """Apply intent with no active plan shows error."""
    home = setup_cli_instance(tmp_path)
    runner = CliRunner()

    with _mock_classify_as_apply():
        result = runner.invoke(cli, ['--home', str(home), 'apply it'])

    assert result.exit_code != 0
    assert 'No active plan' in result.output


def test_prompt_apply_plan_not_found(tmp_path):
    """Apply intent with nonexistent plan ID shows error."""
    home = setup_cli_instance(tmp_path)
    runner = CliRunner()

    with _mock_classify_as_apply():
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
    with _mock_classify_as_apply():
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
    with _mock_classify_as_apply():
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
    with _mock_classify_as_apply():
        result = runner.invoke(
            cli, ['--home', str(home), f'apply plan-{plan.plan_id}'], input='n\n'
        )

    assert 'Apply cancelled' in result.output


def test_prompt_apply_force_in_text(tmp_path):
    """Force keyword in prompt text still triggers force apply."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    with _mock_classify_as_apply():
        result = runner.invoke(
            cli,
            ['--home', str(home), f'apply plan-{plan.plan_id} force'],
            input='y\n',
        )

    assert result.exit_code == 0


def test_prompt_apply_force_via_flag(tmp_path):
    """--force flag on handle_prompt threads through to apply."""
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1', status='open')
    write_ticket(home, ticket)
    ops = [Operation('T-1', 'status', 'open', 'done', 'closing')]
    plan = make_and_save_plan(home, ops, checked=True)

    runner = CliRunner()
    with _mock_classify_as_apply():
        result = runner.invoke(
            cli,
            ['--home', str(home), f'apply plan-{plan.plan_id}', '--force'],
            input='y\n',
        )

    assert result.exit_code == 0


def test_bare_oppie_prints_help_and_tui_hint(tmp_path):
    """Bare `oppie` (no args, no subcommand) prints help and TUI install hint."""
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(tmp_path)])

    assert result.exit_code == 0
    assert 'Usage:' in result.output
    assert 'oppie[tui]' in result.output
