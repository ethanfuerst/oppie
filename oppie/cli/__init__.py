from pathlib import Path

import click

from oppie.logging import configure_logging


@click.group()
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
@click.pass_context
def cli(ctx: click.Context, home: Path | None, debug: bool) -> None:
    """oppie — project management operations CLI."""
    ctx.ensure_object(dict)
    ctx.obj['home'] = home
    ctx.obj['debug'] = debug
    configure_logging(debug, home=home)


# Late imports: commands must be imported after cli group is defined
from oppie.cli.commands.config_cmd import config  # noqa: E402
from oppie.cli.commands.context import context  # noqa: E402
from oppie.cli.commands.init import init  # noqa: E402

cli.add_command(init)
cli.add_command(config)
cli.add_command(context)
