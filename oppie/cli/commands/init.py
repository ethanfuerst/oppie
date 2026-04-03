import asyncio
from pathlib import Path

import click

from oppie.cli.console import console, success, warn
from oppie.cli.extras import extras_available
from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    save_oppie_config,
)
from oppie.instance import Instance
from oppie.llm import create_llm_provider
from oppie.providers.linear.provider import LinearProvider
from oppie.providers.local import LocalProvider


@click.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a new oppie instance."""
    home_override = ctx.obj.get('home')
    home = home_override or (Path.cwd() / '.oppie')

    if home.exists():
        raise click.ClickException(
            f'Instance already exists at {home}. '
            'Run "config validate" to check it, or remove it to start fresh.'
        )

    extras = extras_available()

    # Step 1: Instance type
    console.print('\n[bold]Instance type:[/bold]')
    console.print('  1. Repo (scoped to this repository)')
    console.print('  2. Portfolio (spans multiple repos/projects)')
    type_choice = click.prompt('Choice', type=click.IntRange(1, 2), default=1)
    instance_type = InstanceType.REPO if type_choice == 1 else InstanceType.PORTFOLIO

    Instance.create(home, instance_type)

    # Step 2: Provider
    console.print('\n[bold]Provider:[/bold]')
    console.print('  1. Local only')
    if extras['linear']:
        console.print('  2. Linear')
    else:
        console.print(
            '  2. Linear [dim](not installed — pip install oppie[linear])[/dim]'
        )
    prov_choice = click.prompt('Choice', type=click.IntRange(1, 2), default=1)

    provider_config: ProviderConfig
    if prov_choice == 2 and extras['linear']:
        cache = LocalProvider(home)
        linear_provider = LinearProvider.setup(home, cache)
        provider_config = linear_provider._config

        # Step 2b: Initial sync
        if click.confirm('\nRun initial sync?', default=True):
            with console.status('Syncing from Linear...'):
                result = linear_provider.sync()
            if result.errors:
                warn(
                    f'Synced {result.tickets_upserted} tickets '
                    f'({len(result.errors)} errors)'
                )
            else:
                success(f'Synced {result.tickets_upserted} tickets')
        linear_provider.close()
        cache.close()
    else:
        provider_config = ProviderConfig(type='local')  # type: ignore[arg-type]

    # Step 3: LLM backend (optional)
    llm_config = None
    if extras['llm']:
        llm_config = _prompt_llm_config()

    # Step 4: Context docs (optional)
    if click.confirm(
        '\nSet up context documents? (vision, roadmap, etc.)', default=False
    ):
        _setup_context_docs(home)

    # Save oppie.yaml
    config = OppieConfig(
        instance_type=instance_type,
        provider=provider_config,
        llm=llm_config,
    )
    save_oppie_config(home / 'config', config)

    # Summary
    console.print('\n[bold green]oppie is ready.[/bold green]\n')
    console.print(f'  Instance home:  {home}')
    console.print(f'  Provider:       {provider_config.provider_type.value}')
    if llm_config:
        console.print(
            f'  LLM:            {llm_config.model} ({llm_config.backend.value})'
        )
    else:
        console.print('  LLM:            [dim]not configured[/dim]')
    console.print('\n[bold]Next steps — just type what you want:[/bold]')
    console.print('  [dim]"what\'s the status of the auth project?"[/dim]   (question)')
    console.print(
        '  [dim]"prioritize security work"[/dim]                 (instruction → plan)'
    )
    console.print(
        '  [dim]report[/dim]                                     (status report)'
    )


def _prompt_llm_config() -> LLMConfig | None:
    """Prompt for LLM backend configuration. Return None if skipped."""
    console.print('\n[bold]LLM backend (optional):[/bold]')
    console.print('  1. Local (OpenAI-compatible endpoint)')
    console.print('  2. Anthropic Claude API')
    console.print('  3. Skip')
    llm_choice = click.prompt('Choice', type=click.IntRange(1, 3), default=3)

    if llm_choice == 3:
        return None

    if llm_choice == 1:
        backend = LLMBackend.OPENAI_COMPATIBLE
        model = click.prompt('Model name', default='llama-3.2-8b')
        endpoint = click.prompt('Endpoint', default='http://localhost:8080/v1')
    else:
        backend = LLMBackend.ANTHROPIC
        model = click.prompt('Model name', default='claude-sonnet-4-20250514')
        endpoint = None

    llm_config = LLMConfig(backend=backend, model=model, endpoint=endpoint)

    if click.confirm('Test LLM connection?', default=True):
        try:
            provider = create_llm_provider(llm_config)
            with console.status('Testing LLM connection...'):
                connected = asyncio.run(_test_llm(provider))
            if connected:
                success('LLM connection successful.')
            else:
                warn('LLM connection failed. Config saved anyway.')
        except Exception as e:
            warn(f'LLM test failed: {e}. Config saved anyway.')

    return llm_config


async def _test_llm(provider) -> bool:  # type: ignore[no-untyped-def]
    """Test LLM connection in async context."""
    async with provider:
        result: bool = await provider.test_connection()
        return result


def _setup_context_docs(home: Path) -> None:
    """Create placeholder context documents."""
    context_dir = home / 'context'
    docs = {
        'vision': '# Vision\n\nDescribe your project/org vision and strategy here.\n',
        'roadmap': '# Roadmap\n\nDescribe your current roadmap here.\n',
        'metrics': '# Metrics\n\nDescribe your success metrics and KPIs here.\n',
        'prioritization': (
            '# Prioritization\n\nDescribe your prioritization rubric here.\n'
        ),
    }
    for name, content in docs.items():
        path = context_dir / f'{name}.md'
        if not path.exists():
            path.write_text(content)
    success('Context documents created in .oppie/context/')
