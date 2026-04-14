from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from oppie.cli import cli
from oppie.events import PlanResultEvent
from oppie.intent import Intent
from oppie.models.operation import Operation
from oppie.models.plan import Plan, PlanStatus
from oppie.run_log import RunLog
from tests.helpers import make_ticket, write_ticket

_INIT_INPUT = '1\n1\n1\nllama-3.2-8b\nhttp://localhost:8080/v1\nn\nn\n'


def _plan_for(home) -> Plan:
    op = Operation(
        ticket_id='T-1',
        field='status',
        before_value='open',
        after_value='done',
        rationale='closing',
    )
    plan = Plan(
        instruction='close T-1',
        operations=[op],
        risks=[],
        created_at=datetime.now(UTC).isoformat(),
        status=PlanStatus.SAVED,
    )
    return plan


async def _mock_plan_gen(provider, config, prompt, save=True):
    plan = _plan_for(provider.home)
    yield PlanResultEvent(plan=plan)


def test_full_init_prompt_apply_workflow(tmp_path):
    """init → prompt (INSTRUCTION → saved plan) → apply."""
    home = tmp_path / '.oppie'
    runner = CliRunner()

    # Step 1: init
    init_result = runner.invoke(cli, ['--home', str(home), 'init'], input=_INIT_INPUT)

    assert init_result.exit_code == 0, init_result.output
    assert (home / '.oppie-marker').exists()

    # Seed a ticket so apply has something concrete to mutate
    write_ticket(home, make_ticket('T-1', status='open'))

    # Step 2: prompt (INSTRUCTION) — mock classifier + plan generation
    with (
        patch(
            'oppie.cli.commands.prompt.classify_intent',
            new_callable=AsyncMock,
            return_value=Intent.INSTRUCTION,
        ),
        patch('oppie.cli.commands.prompt.generate_plan', side_effect=_mock_plan_gen),
    ):
        prompt_result = runner.invoke(
            cli,
            ['--home', str(home), 'close T-1'],
            input='n\ny\n',  # review? no; save? yes
        )

    assert prompt_result.exit_code == 0, prompt_result.output
    assert 'Plan saved' in prompt_result.output

    plan_id = _plan_for(home).plan_id

    # Step 3: apply the saved plan (active plan set via session fallback)
    apply_result = runner.invoke(cli, ['--home', str(home), 'apply'], input='y\n')

    assert apply_result.exit_code == 0, apply_result.output
    assert 'All operations applied successfully' in apply_result.output

    # Verify apply artifact + run log both updated
    run_log = RunLog(home)
    entries = run_log.query()

    assert any(e.plan_id == plan_id for e in entries)
    assert any(e.apply_id is not None for e in entries)
