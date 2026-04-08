import asyncio
import logging
import re

import click

from oppie.ask import generate_ask
from oppie.cli.commands.apply import run_apply
from oppie.cli.console import console, error, info, setup_provider
from oppie.events import AskResultEvent, PlanResultEvent
from oppie.intent import Intent, classify_intent
from oppie.llm import create_llm_provider
from oppie.session import Session

logger = logging.getLogger(__name__)


@click.command(hidden=True)
@click.argument('prompt')
@click.pass_context
def handle_prompt(ctx: click.Context, prompt: str) -> None:
    """Handle a bare prompt — classify intent and route."""
    home = ctx.obj['resolved_home']
    config = ctx.obj['config']
    no_sync = ctx.obj.get('no_sync', False)

    # LLM required for classification
    if config is None or config.llm is None:
        error('LLM is not configured. Run "oppie init" to set up an LLM backend.')
        raise SystemExit(1)

    # Classify intent
    llm = create_llm_provider(config.llm)

    async def _classify() -> Intent:
        async with llm:
            return await classify_intent(prompt, llm)

    intent = asyncio.run(_classify())
    logger.info('Classified prompt as %s', intent.value)

    provider, _ = setup_provider(home, no_sync=no_sync)

    # Route
    if intent == Intent.QUESTION:
        _handle_ask(provider, config, prompt)
    elif intent == Intent.INSTRUCTION:
        _handle_plan(provider, config, prompt)
    elif intent == Intent.APPLY:
        _handle_apply(provider, prompt)


def _handle_ask(provider, config, prompt: str) -> None:
    """Route to ask behavior."""

    async def _run():
        result_event = None
        async for event in generate_ask(provider, config, prompt):
            if isinstance(event, AskResultEvent):
                result_event = event
        return result_event

    info('Thinking...')
    result_event = asyncio.run(_run())

    if result_event is None:
        error('No result received.')
        raise SystemExit(1)

    result = result_event.result

    console.print()
    console.print(result.answer)
    console.print()

    if result.artifact_path:
        console.print(f'Artifact: [dim]{result.artifact_path}[/dim]')

    # Stats line
    stats_parts = []
    if result.usage:
        total = result.usage.prompt_tokens + result.usage.completion_tokens
        stats_parts.append(f'{total / 1000:.1f}k tokens')
    stats_parts.append(f'{result.duration:.1f}s')
    console.print(f'[dim]* {" \u00b7 ".join(stats_parts)}[/dim]')

    # Update session
    home = provider.home
    session = Session.load_latest(home) or Session.create(home)
    session.add_run_id(result.run_id)


_PLAN_ID_RE = re.compile(r'plan-([a-f0-9]+)', re.IGNORECASE)


def _handle_apply(provider, prompt: str) -> None:
    """Route to apply behavior — extract plan_id and force from prompt text."""
    home = provider.home
    prompt_lower = prompt.lower()

    # Extract force flag
    force = 'force' in prompt_lower or '--force' in prompt_lower

    # Extract plan_id from prompt text
    plan_id_match = _PLAN_ID_RE.search(prompt)
    plan_id = plan_id_match.group(1) if plan_id_match else None

    # Fall back to session active plan
    if plan_id is None:
        session = Session.load_latest(home)
        plan_id = session.get_active_plan() if session else None
        if plan_id is None:
            error('No active plan. Generate a plan first, or specify a plan ID:')
            console.print('  [bold]oppie "apply plan-abc123"[/bold]')
            raise SystemExit(1)

    run_apply(provider, plan_id, force=force)


def _handle_plan(provider, config, prompt: str) -> None:
    """Route to plan behavior."""
    from oppie.plan import generate_plan

    async def _run():
        result_event = None
        async for event in generate_plan(provider, config, prompt, save=False):
            if isinstance(event, PlanResultEvent):
                result_event = event
        return result_event

    info('Generating plan...')
    result_event = asyncio.run(_run())

    if result_event is None:
        error('No plan generated.')
        raise SystemExit(1)

    plan = result_event.plan

    console.print()
    console.print(f'[bold]Plan: {plan.instruction}[/bold]')
    console.print()

    if not plan.operations:
        console.print('No operations needed. No plan saved.')
        return

    console.print(f'Operations ({len(plan.operations)}):')
    console.print()
    for i, op in enumerate(plan.operations, 1):
        console.print(
            f'  {i}. {op.ticket_id}  {op.field}: {op.before_value} -> {op.after_value}'
        )
        console.print(f'     Rationale: {op.rationale}')
    console.print()

    if plan.risks:
        console.print('Risks:')
        for risk in plan.risks:
            console.print(f'  {risk}')
        console.print()

    # Interactive: review full plan
    review = click.confirm('Review full plan?', default=False)
    if review:
        import json

        console.print()
        console.print(json.dumps(plan.to_dict(), indent=2))
        console.print()

    # Interactive: save plan
    save = click.confirm('Save this plan?', default=False)
    if not save:
        console.print('Plan discarded.')
        return

    plan.save(provider.home)
    console.print()
    console.print(f'Plan saved: [bold]{plan.plan_id}[/bold]')
    console.print(f'Next: [bold]oppie apply {plan.plan_id}[/bold]')

    # Update session
    home = provider.home
    session = Session.load_latest(home) or Session.create(home)
    session.set_active_plan(plan.plan_id)
