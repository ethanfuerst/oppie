from pathlib import Path

import click


@click.group()
@click.option(
    '--home',
    type=click.Path(path_type=Path),
    default=None,
    help='Instance home directory (overrides auto-detection).',
)
@click.pass_context
def cli(ctx: click.Context, home: Path | None) -> None:
    """oppie — project management operations CLI."""
    ctx.ensure_object(dict)
    ctx.obj['home'] = home


# Late imports: commands must be imported after cli group is defined
from oppie.cli.commands.config_cmd import config  # noqa: E402
from oppie.cli.commands.context import context  # noqa: E402
from oppie.cli.commands.init import init  # noqa: E402

cli.add_command(init)
cli.add_command(config)
cli.add_command(context)
