import asyncio
import logging

import click

from oppie.ask import generate_ask
from oppie.cli.console import console, error, info, setup_provider
from oppie.config import IntentClassification
from oppie.intent import Intent, classify_intent, classify_intent_llm
from oppie.llm import LLMNotConfiguredError, create_llm_provider
from oppie.session import Session

logger = logging.getLogger(__name__)


@click.command(hidden=True)
@click.argument('prompt')
@click.pass_context
def handle_prompt(ctx: click.Context, prompt: str) -> None:
    """Handle a bare prompt — classify intent and route to ask or plan."""
    home = ctx.obj['resolved_home']
    config = ctx.obj['config']
    no_sync = ctx.obj.get('no_sync', False)

    provider, _ = setup_provider(home, no_sync=no_sync)

    # Classify intent
    intent_strategy = IntentClassification.LOCAL
    if config and config.intent_classification:
        intent_strategy = config.intent_classification

    if intent_strategy == IntentClassification.LLM and config and config.llm:
        try:
            llm = create_llm_provider(config.llm)

            async def _classify() -> Intent:
                async with llm:
                    return await classify_intent_llm(prompt, llm)

            intent = asyncio.run(_classify())
        except (LLMNotConfiguredError, Exception):
            logger.debug('LLM classification failed, falling back to local')
            intent = classify_intent(prompt)
    else:
        intent = classify_intent(prompt)

    logger.info('Classified prompt as %s', intent.value)

    # 5. Route
    if intent == Intent.AMBIGUOUS:
        error('Could not determine intent. Please be more specific:')
        console.print('  [dim]"what bugs are open?"[/dim]         (question)')
        console.print('  [dim]"triage the open bugs"[/dim]        (instruction)')
        raise SystemExit(1)

    if intent == Intent.QUESTION:
        _handle_ask(provider, config, prompt)
    else:
        _handle_plan(provider, config, prompt)


def _handle_ask(provider, config, prompt: str) -> None:
    """Route to ask behavior."""
    info('Thinking...')
    result = asyncio.run(generate_ask(provider, config, prompt))

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


def _handle_plan(provider, config, prompt: str) -> None:
    """Route to plan behavior."""
    from oppie.plan import generate_plan

    info('Generating plan...')
    plan = asyncio.run(generate_plan(provider, config, prompt, save=False))

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
    console.print(f'Next: [bold]apply {plan.plan_id}[/bold]')

    # Update session
    home = provider.home
    session = Session.load_latest(home) or Session.create(home)
    session.set_active_plan(plan.plan_id)
