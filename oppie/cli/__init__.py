from pathlib import Path

import click

from oppie.cli.console import console, error
from oppie.logging import configure_logging

# Commands that do not require an initialized instance
_SKIP_INSTANCE = frozenset({'init'})

# Internal subcommand name for the bare-prompt path
_PROMPT_SUBCOMMAND = 'handle_prompt'


class PromptOrCommand(click.Group):
    """Click group that treats unrecognized arguments as a prompt.

    Rewrites a bare `oppie "<text>"` invocation into
    `oppie handle_prompt "<text>"` so trailing options (e.g. `--force`)
    bind to the hidden `handle_prompt` subcommand.
    """

    # Options that consume the next argument (i.e., have a value)
    _VALUE_OPTIONS = frozenset({'--home'})

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        skip_next = False
        for i, arg in enumerate(args):
            if skip_next:
                skip_next = False
                continue
            if arg in self._VALUE_OPTIONS:
                skip_next = True
                continue
            if arg.startswith('-'):
                continue
            if arg in self.commands:
                break
            # Not a known command — inject `handle_prompt` before it so
            # the bare prompt and any trailing options bind to that
            # subcommand.
            args = args[:i] + [_PROMPT_SUBCOMMAND] + args[i:]
            break
        return super().parse_args(ctx, args)


@click.group(cls=PromptOrCommand, invoke_without_command=True)
@click.option(
    '--home',
    type=click.Path(path_type=Path),
    default=None,
    help='Instance home directory (overrides auto-detection).',
)
@click.option(
    '--debug',
    is_flag=True,
    default=False,
    help='Enable debug logging.',
)
@click.option(
    '--no-sync',
    is_flag=True,
    default=False,
    help='Skip auto-sync, use cached data.',
)
@click.pass_context
def cli(
    ctx: click.Context,
    home: Path | None,
    debug: bool,
    no_sync: bool,
) -> None:
    """oppie — project management operations CLI."""
    from oppie.instance import Instance

    ctx.ensure_object(dict)
    ctx.obj['home'] = home
    ctx.obj['debug'] = debug
    ctx.obj['no_sync'] = no_sync
    configure_logging(debug, home=home)

    subcommand = ctx.invoked_subcommand

    # Bare `oppie` (no subcommand): print help + TUI hint, exit 0.
    if subcommand is None:
        click.echo(ctx.get_help())
        console.print()
        console.print(
            "[dim]Tip: install the TUI with 'pip install oppie\\[tui]' "
            '(coming soon).[/dim]'
        )
        return

    # Resolve instance for all commands except init
    if subcommand not in _SKIP_INSTANCE:
        try:
            resolved_home = Instance.detect(home)
            instance = Instance.load(resolved_home)
            ctx.obj['resolved_home'] = resolved_home
            ctx.obj['instance'] = instance
            ctx.obj['config'] = instance.config
        except FileNotFoundError:
            error('No oppie instance found.')
            console.print(
                "Run 'oppie init' to create one, or use --home to specify an instance."
            )
            raise SystemExit(1) from None


# Late imports: commands must be imported after cli group is defined
from oppie.cli.commands.amend import amend  # noqa: E402
from oppie.cli.commands.apply import apply  # noqa: E402
from oppie.cli.commands.config_cmd import config  # noqa: E402
from oppie.cli.commands.context import context  # noqa: E402
from oppie.cli.commands.health import health  # noqa: E402
from oppie.cli.commands.history import history  # noqa: E402
from oppie.cli.commands.init import init  # noqa: E402
from oppie.cli.commands.prompt import handle_prompt  # noqa: E402
from oppie.cli.commands.repair import repair  # noqa: E402
from oppie.cli.commands.show import show  # noqa: E402
from oppie.cli.commands.state import state  # noqa: E402
from oppie.cli.commands.sync import sync  # noqa: E402

cli.add_command(init)
cli.add_command(config)
cli.add_command(context)
cli.add_command(amend)
cli.add_command(apply)
cli.add_command(show)
cli.add_command(history)
cli.add_command(state)
cli.add_command(health)
cli.add_command(repair)
cli.add_command(sync)
cli.add_command(handle_prompt, name=_PROMPT_SUBCOMMAND)
