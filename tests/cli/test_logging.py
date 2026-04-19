import logging

from click.testing import CliRunner

from oppie.cli import cli
from oppie.logging import configure_logging


def test_default_level_is_warning():
    configure_logging(debug=False)

    assert logging.getLogger().level == logging.WARNING


def test_debug_flag_sets_debug_level():
    configure_logging(debug=True)

    assert logging.getLogger().level == logging.DEBUG


def test_env_var_overrides_debug_flag(monkeypatch):
    monkeypatch.setenv('OPPIE_LOG_LEVEL', 'INFO')
    configure_logging(debug=True)

    assert logging.getLogger().level == logging.INFO


def test_env_var_works_without_debug_flag(monkeypatch):
    monkeypatch.setenv('OPPIE_LOG_LEVEL', 'ERROR')
    configure_logging(debug=False)

    assert logging.getLogger().level == logging.ERROR


def test_invalid_env_var_warns_and_falls_back(monkeypatch, capsys):
    monkeypatch.setenv('OPPIE_LOG_LEVEL', 'BANANA')
    configure_logging(debug=False)
    captured = capsys.readouterr()

    assert 'BANANA' in captured.err
    assert logging.getLogger().level == logging.WARNING


def test_debug_flag_via_cli():
    runner = CliRunner()
    result = runner.invoke(cli, ['--debug', '--help'])

    assert result.exit_code == 0


def test_log_file_created_without_debug_flag(tmp_path):
    (tmp_path / 'logs').mkdir()
    configure_logging(debug=False, home=tmp_path)
    logs = list((tmp_path / 'logs').glob('oppie-*.log'))

    assert len(logs) == 1


def test_log_file_created_when_home_provided(tmp_path):
    (tmp_path / 'logs').mkdir()
    configure_logging(debug=True, home=tmp_path)
    logs = list((tmp_path / 'logs').glob('oppie-*.log'))

    assert len(logs) == 1


def test_log_file_receives_messages(tmp_path):
    (tmp_path / 'logs').mkdir()
    configure_logging(debug=True, home=tmp_path)
    test_logger = logging.getLogger('test_file_output')
    test_logger.debug('hello from test')
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_files = list((tmp_path / 'logs').glob('oppie-*.log'))
    contents = log_files[0].read_text()

    assert 'hello from test' in contents


def test_stderr_fallback_when_home_has_no_logs_dir(tmp_path):
    configure_logging(debug=True, home=tmp_path)
    root = logging.getLogger()

    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )


def test_stderr_fallback_when_no_home():
    configure_logging(debug=True, home=None)
    root = logging.getLogger()

    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )


def test_default_emits_no_stdout(capsys):
    configure_logging(debug=False)
    test_logger = logging.getLogger('oppie.test_default_stdout')
    test_logger.info('should be filtered')
    test_logger.warning('should reach stderr')
    for handler in logging.getLogger().handlers:
        handler.flush()
    captured = capsys.readouterr()

    assert captured.out == ''
    assert 'should be filtered' not in captured.err
    assert 'should reach stderr' in captured.err


def test_debug_emits_no_stdout(capsys):
    configure_logging(debug=True)
    test_logger = logging.getLogger('oppie.test_debug_stdout')
    test_logger.debug('debug line')
    test_logger.info('info line')
    for handler in logging.getLogger().handlers:
        handler.flush()
    captured = capsys.readouterr()

    assert captured.out == ''
    assert 'debug line' in captured.err
    assert 'info line' in captured.err


def test_httpx_logger_capped_with_debug():
    configure_logging(debug=True)

    assert logging.getLogger('httpx').level == logging.WARNING


def test_httpcore_logger_capped_with_debug():
    configure_logging(debug=True)

    assert logging.getLogger('httpcore').level == logging.WARNING


def test_urllib3_logger_capped_with_debug():
    configure_logging(debug=True)

    assert logging.getLogger('urllib3').level == logging.WARNING
