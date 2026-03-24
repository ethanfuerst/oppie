import yaml
from click.testing import CliRunner

from oppie.cli import cli


def test_init_local_minimal(tmp_path):
    home = tmp_path / '.oppie'
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), 'init'],
        input='1\n1\n3\nn\n',
    )

    assert result.exit_code == 0, result.output
    assert (home / '.oppie-marker').exists()
    config = yaml.safe_load((home / 'config' / 'oppie.yaml').read_text())
    assert config['instance_type'] == 'repo'
    assert config['provider']['type'] == 'local'
    assert 'llm' not in config
    assert 'oppie is ready' in result.output


def test_init_fails_if_instance_exists(tmp_path):
    home = tmp_path / '.oppie'
    home.mkdir()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), 'init'],
    )

    assert result.exit_code != 0
    assert 'Instance already exists' in result.output


def test_init_portfolio_type(tmp_path):
    home = tmp_path / '.oppie'
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), 'init'],
        input='2\n1\n3\nn\n',
    )

    assert result.exit_code == 0, result.output
    config = yaml.safe_load((home / 'config' / 'oppie.yaml').read_text())
    assert config['instance_type'] == 'portfolio'


def test_init_with_llm_skip(tmp_path):
    home = tmp_path / '.oppie'
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), 'init'],
        input='1\n1\n3\nn\n',
    )

    assert result.exit_code == 0, result.output
    config = yaml.safe_load((home / 'config' / 'oppie.yaml').read_text())
    assert 'llm' not in config


def test_init_with_context_docs(tmp_path):
    home = tmp_path / '.oppie'
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ['--home', str(home), 'init'],
        input='1\n1\n3\ny\n',
    )

    assert result.exit_code == 0, result.output
    context_dir = home / 'context'
    assert (context_dir / 'vision.md').exists()
    assert (context_dir / 'roadmap.md').exists()
    assert (context_dir / 'metrics.md').exists()
    assert (context_dir / 'prioritization.md').exists()


def test_init_linear_provider(tmp_path, monkeypatch):
    home = tmp_path / '.oppie'
    from unittest.mock import MagicMock, patch

    from oppie.providers.linear.config import LinearProviderConfig

    # Mock extras to report linear available
    monkeypatch.setattr(
        'oppie.cli.commands.init.extras_available',
        lambda: {'linear': True, 'llm': True, 'tui': False},
    )

    mock_config = LinearProviderConfig(
        type='linear',
        team_id='team-123',
        project_id='proj-456',
        api_key='lin_api_test',
    )
    mock_provider = MagicMock()
    mock_provider._config = mock_config

    with patch(
        'oppie.providers.linear.provider.LinearProvider.setup',
        return_value=mock_provider,
    ):
        runner = CliRunner()
        # Choose: repo, linear provider, no sync, skip LLM, no context
        result = runner.invoke(
            cli,
            ['--home', str(home), 'init'],
            input='1\n2\nn\n3\nn\n',
        )

    assert result.exit_code == 0, result.output
    config = yaml.safe_load((home / 'config' / 'oppie.yaml').read_text())
    assert config['provider']['type'] == 'linear'
    assert config['provider']['team_id'] == 'team-123'
    mock_provider.close.assert_called_once()
