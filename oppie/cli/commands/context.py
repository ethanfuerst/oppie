from datetime import UTC, datetime

import click

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.run_log import generate_run_id

CONTEXT_DOCS = ('vision', 'roadmap', 'metrics', 'prioritization')


@click.group()
def context() -> None:
    """Manage context documents."""


@context.command()
@click.argument('doc', required=False)
@click.pass_context
def show(ctx: click.Context, doc: str | None) -> None:
    """Show context documents. Optionally specify a document name."""
    home = ctx.obj['resolved_home']
    context_dir = home / 'context'

    if doc:
        path = context_dir / f'{doc}.md'
        if not path.exists():
            raise click.ClickException(f'Context document not found: {doc}.md')
        click.echo(path.read_text())
        return

    # List all context docs
    click.echo('Context documents:\n')
    for name in CONTEXT_DOCS:
        path = context_dir / f'{name}.md'
        if path.exists():
            stat = path.stat()
            size = f'{stat.st_size / 1024:.1f} KB'
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime('%Y-%m-%d')
            click.echo(f'  {name + ".md":<25s} Last updated: {mtime}    {size}')
        else:
            click.echo(f'  {name + ".md":<25s} Not configured')

    click.echo("\nUse 'context show <doc>' to view contents.")


@context.command()
@click.argument('doc')
@click.pass_context
def edit(ctx: click.Context, doc: str) -> None:
    """Edit a context document."""
    home = ctx.obj['resolved_home']
    context_dir = home / 'context'
    path = context_dir / f'{doc}.md'

    # Load existing content or create template
    if path.exists():
        original = path.read_text()
        # Save previous version as artifact
        store = ArtifactStore(home)
        run_id = generate_run_id()
        store.save_artifact(ArtifactType.CONTEXT, original, run_id)
    else:
        original = f'# {doc.title()}\n\n'

    # Open in editor via click.edit (handles EDITOR/VISUAL fallback)
    edited = click.edit(original)
    if edited is None:
        click.echo('No changes made.')
        return

    context_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(edited)
    click.echo(f'Context document updated: {doc}.md')


@context.command('validate')
@click.pass_context
def validate_cmd(ctx: click.Context) -> None:
    """Validate context documents."""
    home = ctx.obj['resolved_home']
    context_dir = home / 'context'

    click.echo('Validating context documents...\n')
    for name in CONTEXT_DOCS:
        path = context_dir / f'{name}.md'
        if path.exists():
            try:
                path.read_text()
                click.echo(f'  {name + ".md":<25s} ok')
            except Exception as e:
                click.echo(f'  {name + ".md":<25s} ERROR: {e}')
        else:
            click.echo(f'  {name + ".md":<25s} not configured (optional)')

    click.echo('\nContext is valid.')
