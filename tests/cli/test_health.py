from click.testing import CliRunner

from oppie.cli import cli
from oppie.llm import LLMNotConfiguredError
from tests.cli.conftest import setup_cli_instance
from tests.helpers import make_ticket, write_ticket


def test_health_clean_instance(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert 'All checks passed' in result.output


def test_health_corrupt_run_log(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    log_path = home / 'logs' / 'runs.jsonl'
    log_path.write_text('not json\n')

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert 'malformed' in result.output.lower()


def test_health_corrupt_ticket(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    (home / 'tickets' / 'BAD.json').write_text('not json')

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert 'corrupt' in result.output.lower()


def test_health_suggests_repair(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    (home / 'tickets' / 'BAD.json').write_text('not json')

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert 'oppie repair' in result.output


def test_health_llm_not_configured(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert 'n/a' in result.output.lower()


def test_health_provider_connectivity_local(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    # Provider connectivity should show n/a for local
    assert 'local provider' in result.output.lower()


def test_health_with_valid_tickets(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    ticket = make_ticket('T-1')
    write_ticket(home, ticket)

    def _raise(cfg):
        raise LLMNotConfiguredError('no config')

    monkeypatch.setattr('oppie.llm.create_llm_provider', _raise)

    result = CliRunner().invoke(cli, ['--home', str(home), 'health'])

    assert result.exit_code == 0
    assert '1 tickets' in result.output
