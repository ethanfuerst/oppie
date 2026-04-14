import asyncio
import logging
import re

import click

from oppie.ask import generate_ask
from oppie.cli.commands.apply import run_apply
from oppie.cli.console import console, error
from oppie.cli.provider_setup import setup_provider
from oppie.cli.render import EventRenderer, RenderMode, render_sync
from oppie.intent import Intent, classify_intent
from oppie.llm import create_llm_provider
from oppie.plan import generate_plan
from oppie.session import Session

logger = logging.getLogger(__name__)


@click.command(hidden=True)
@click.argument('prompt')
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Overwrite drifted values without prompting (apply only).',
)
@click.pass_context
def handle_prompt(ctx: click.Context, prompt: str, force: bool) -> None:
    """Handle a bare prompt — classify intent and route."""
    home = ctx.obj['resolved_home']
    config = ctx.obj['config']
    no_sync = ctx.obj.get('no_sync', False)

    if config is None or config.llm is None:
        error('LLM is not configured. Run "oppie init" to set up an LLM backend.')
        raise SystemExit(1)

    llm = create_llm_provider(config.llm)

    async def _classify() -> Intent:
        async with llm:
            return await classify_intent(prompt, llm)

    intent = asyncio.run(_classify())
    logger.info('Classified prompt as %s', intent.value)

    if intent == Intent.QUESTION:
        _handle_ask(home, config, prompt, no_sync=no_sync)
    elif intent == Intent.INSTRUCTION:
        _handle_plan(home, config, prompt, no_sync=no_sync)
    elif intent == Intent.APPLY:
        _handle_apply(home, config, prompt, no_sync=no_sync, force=force)


def _handle_ask(home, config, prompt: str, *, no_sync: bool) -> None:
    """Route to ask behavior using the event renderer."""
    renderer = EventRenderer(mode=RenderMode.ASK)
    with render_sync(renderer, home, config, no_sync=no_sync) as (provider, _):
        asyncio.run(renderer.consume(generate_ask(provider, config, prompt)))

    if renderer.ask_result is None:
        error('No result received.')
        raise SystemExit(1)

    result = renderer.ask_result
    if result.artifact_path:
        console.print(f'Artifact: [dim]{result.artifact_path}[/dim]')

    session = Session.load_latest(home) or Session.create(home)
    session.add_run_id(result.run_id)


def _handle_plan(home, config, prompt: str, *, no_sync: bool) -> None:
    """Route to plan behavior using the event renderer."""
    renderer = EventRenderer(mode=RenderMode.PLAN)
    with render_sync(renderer, home, config, no_sync=no_sync) as (provider, _):
        asyncio.run(
            renderer.consume(generate_plan(provider, config, prompt, save=False))
        )

    plan = renderer.plan
    if plan is None:
        error('No plan generated.')
        raise SystemExit(1)

    console.print()
    console.print(f'[bold]Plan: {plan.instruction}[/bold]')

    if not plan.operations:
        console.print('No operations needed. No plan saved.')
        return

    console.print(f'[dim]({len(plan.operations)} operations)[/dim]')
    if plan.risks:
        console.print()
        console.print('Risks:')
        for risk in plan.risks:
            console.print(f'  {risk}')
    console.print()

    if click.confirm('Review full plan?', default=False):
        import json

        console.print()
        console.print(json.dumps(plan.to_dict(), indent=2))
        console.print()

    if not click.confirm('Save this plan?', default=False):
        console.print('Plan discarded.')
        return

    plan.save(home)
    console.print()
    console.print(f'Plan saved: [bold]{plan.plan_id}[/bold]')
    console.print(f'Next: [bold]oppie apply {plan.plan_id}[/bold]')

    session = Session.load_latest(home) or Session.create(home)
    session.set_active_plan(plan.plan_id)


_PLAN_ID_RE = re.compile(r'plan-([a-f0-9]+)', re.IGNORECASE)


def _handle_apply(home, config, prompt: str, *, no_sync: bool, force: bool) -> None:
    """Route to apply behavior — extract plan_id from prompt text or session."""
    prompt_lower = prompt.lower()
    text_force = 'force' in prompt_lower or '--force' in prompt_lower
    effective_force = force or text_force

    plan_id_match = _PLAN_ID_RE.search(prompt)
    plan_id = plan_id_match.group(1) if plan_id_match else None

    if plan_id is None:
        session = Session.load_latest(home)
        plan_id = session.get_active_plan() if session else None
        if plan_id is None:
            error('No active plan. Generate a plan first, or specify a plan ID:')
            console.print('  [bold]oppie "apply plan-abc123"[/bold]')
            raise SystemExit(1)

    with setup_provider(home, config, no_sync=no_sync) as (provider, sync_result):
        sync_duration = sync_result.duration if sync_result.synced else None
        run_apply(provider, plan_id, force=effective_force, sync_duration=sync_duration)
