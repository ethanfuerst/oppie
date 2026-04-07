from click.testing import CliRunner

from oppie.cli import cli
from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    save_oppie_config,
)
from oppie.instance import Instance


def _setup_valid_instance(tmp_path):
    """Create a fully valid instance for config validate tests."""
    home = tmp_path / '.oppie'
    Instance.create(home, InstanceType.REPO)
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
        llm=LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test'),
    )
    save_oppie_config(home / 'config', config)
    return home


def test_config_validate_happy_path(tmp_path):
    home = _setup_valid_instance(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'config', 'validate'])

    assert result.exit_code == 0, result.output
    assert 'Configuration is valid' in result.output


def test_config_validate_no_instance(tmp_path):
    home = tmp_path / '.oppie'
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'config', 'validate'])

    assert result.exit_code != 0
    assert 'No oppie instance' in result.output


def test_config_validate_missing_config(tmp_path):
    home = tmp_path / '.oppie'
    Instance.create(home, InstanceType.REPO)
    # Don't write oppie.yaml
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'config', 'validate'])

    assert result.exit_code != 0
    assert 'MISSING' in result.output


def test_config_validate_shows_extras(tmp_path):
    home = _setup_valid_instance(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ['--home', str(home), 'config', 'validate'])

    assert result.exit_code == 0, result.output
    assert 'Installed extras' in result.output
