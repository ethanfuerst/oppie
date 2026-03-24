from unittest.mock import patch

from click.testing import CliRunner

from oppie.cli import cli
from oppie.config import InstanceType, OppieConfig, ProviderConfig, save_oppie_config
from oppie.instance import Instance


def _setup_instance_with_context(tmp_path):
    """Create an instance with context docs."""
    home = tmp_path / '.oppie'
    Instance.create(home, InstanceType.REPO)
    save_oppie_config(
        home / 'config',
        OppieConfig(
            instance_type=InstanceType.REPO,
            provider=ProviderConfig(type='local'),
        ),
    )
    context_dir = home / 'context'
    (context_dir / 'vision.md').write_text('# Vision\n\nOur vision.\n')
    (context_dir / 'roadmap.md').write_text('# Roadmap\n\nOur roadmap.\n')
    return home


def test_context_show_lists_docs(tmp_path):
    home = _setup_instance_with_context(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'context', 'show'])

    assert result.exit_code == 0, result.output
    assert 'vision.md' in result.output
    assert 'roadmap.md' in result.output
    assert 'metrics.md' in result.output
    assert 'Not configured' in result.output


def test_context_show_specific_doc(tmp_path):
    home = _setup_instance_with_context(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'context', 'show', 'vision'])

    assert result.exit_code == 0, result.output
    assert '# Vision' in result.output
    assert 'Our vision.' in result.output


def test_context_show_missing_doc(tmp_path):
    home = _setup_instance_with_context(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'context', 'show', 'nonexistent'])

    assert result.exit_code != 0
    assert 'not found' in result.output


def test_context_edit_saves_artifact(tmp_path):
    home = _setup_instance_with_context(tmp_path)
    edited_content = '# Vision\n\nUpdated vision.\n'

    with patch('oppie.cli.commands.context.click.edit', return_value=edited_content):
        runner = CliRunner()
        result = runner.invoke(cli, ['--home', str(home), 'context', 'edit', 'vision'])

    assert result.exit_code == 0, result.output
    assert 'Context document updated' in result.output
    assert (home / 'context' / 'vision.md').read_text() == edited_content

    # Check that the old version was saved as artifact
    artifact_dir = home / 'artifacts' / 'context'
    artifacts = list(artifact_dir.glob('*.json'))
    assert len(artifacts) == 1


def test_context_edit_no_changes(tmp_path):
    home = _setup_instance_with_context(tmp_path)

    with patch('oppie.cli.commands.context.click.edit', return_value=None):
        runner = CliRunner()
        result = runner.invoke(cli, ['--home', str(home), 'context', 'edit', 'vision'])

    assert result.exit_code == 0, result.output
    assert 'No changes made' in result.output


def test_context_validate_happy_path(tmp_path):
    home = _setup_instance_with_context(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'context', 'validate'])

    assert result.exit_code == 0, result.output
    assert 'vision.md' in result.output
    assert 'ok' in result.output
    assert 'Context is valid' in result.output
