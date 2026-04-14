import asyncio

import click

from oppie.cli.console import console, error, info, success
from oppie.cli.extras import extras_available
from oppie.config import ProviderType
from oppie.llm import create_llm_provider


@click.group('config')
def config() -> None:
    """Manage instance configuration."""


@config.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Validate instance configuration."""
    home = ctx.obj['resolved_home']

    info('Validating configuration...\n')

    _print_check('Instance home', str(home), 'ok')

    # Config file
    config_path = home / 'config' / 'oppie.yaml'
    if config_path.exists():
        _print_check('Config file', str(config_path.relative_to(home)), 'ok')
    else:
        _print_check('Config file', 'oppie.yaml', 'MISSING')
        error("No configuration found. Run 'oppie init' to create an instance.")
        raise SystemExit(1)

    # Load and validate config
    config = ctx.obj.get('config')
    if config is None:
        _print_check('Config validation', '', 'INVALID')
        error('Config loaded but is None.')
        raise SystemExit(1)
    _print_check('Config validation', '', 'ok')

    # Provider config
    provider_yaml = home / 'config' / 'provider.yaml'
    if config.provider.provider_type != ProviderType.LOCAL:
        if provider_yaml.exists():
            _print_check('Provider config', 'provider.yaml', 'ok')
        else:
            _print_check('Provider config', 'provider.yaml', 'MISSING')
    _print_check('Provider', config.provider.provider_type.value.capitalize(), 'ok')

    # LLM backend
    endpoint = config.llm.endpoint or config.llm.backend.value
    try:
        provider = create_llm_provider(config.llm)
        connected = asyncio.run(_test_llm_connection(provider))
        status = 'ok' if connected else 'UNREACHABLE'
    except Exception:
        status = 'UNREACHABLE'
    _print_check('LLM backend', endpoint, status)

    # Context docs
    context_dir = home / 'context'
    context_files = list(context_dir.glob('*.md')) if context_dir.exists() else []
    if context_files:
        _print_check('Context docs', f'{len(context_files)} document(s)', 'ok')
    else:
        _print_check('Context docs', 'not configured', 'ok (optional)')

    # Installed extras
    extras = extras_available()
    installed = [name for name, ok in extras.items() if ok]
    extras_str = ', '.join(installed) if installed else 'none'
    _print_check('Installed extras', extras_str, 'ok')

    success('\nConfiguration is valid.')


async def _test_llm_connection(provider) -> bool:  # type: ignore[no-untyped-def]
    async with provider:
        result: bool = await provider.test_connection()
        return result


def _print_check(label: str, value: str, status: str) -> None:
    """Print an aligned validation check line."""
    if status == 'ok' or status.startswith('ok'):
        styled = f'[green]{status}[/green]'
    elif status in ('MISSING', 'INVALID', 'NOT FOUND', 'UNREACHABLE'):
        styled = f'[red]{status}[/red]'
    else:
        styled = status
    console.print(f'  {label + ":":<20s} {value:<35s} {styled}')
