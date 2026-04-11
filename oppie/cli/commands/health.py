import click

from oppie.cli.console import console, error, success, warn
from oppie.health import CheckStatus, run_all_checks


@click.command()
@click.pass_context
def health(ctx: click.Context) -> None:
    """Check instance health."""
    home = ctx.obj['resolved_home']
    config = ctx.obj.get('config')

    provider = _make_provider(home, config)

    results = run_all_checks(home, config, provider)

    console.print('[bold]Health checks[/bold]')
    console.print()

    has_issues = False
    for result in results:
        if result.status == CheckStatus.OK:
            success(f'{result.name}: {result.message}')
        elif result.status == CheckStatus.NA:
            console.print(f'  [dim]—[/dim] {result.name}: [dim]{result.message}[/dim]')
        elif result.status == CheckStatus.WARNING:
            warn(f'{result.name}: {result.message}')
            has_issues = True
        else:
            error(f'{result.name}: {result.message}')
            has_issues = True

        if result.detail:
            console.print(f'    [dim]{result.detail}[/dim]')

    console.print()
    if has_issues:
        console.print('Run [bold]oppie repair[/bold] to fix detected issues.')
    else:
        console.print('[green]All checks passed.[/green]')


def _make_provider(home, config):
    """Create a provider instance without syncing. Return None if construction fails."""
    from oppie.config import ProviderType

    if config and config.provider.provider_type == ProviderType.LINEAR:
        try:
            from oppie.providers.linear import LinearProvider

            return LinearProvider.setup(home)
        except Exception:
            return None
    from oppie.providers.local import LocalProvider

    return LocalProvider(home)
