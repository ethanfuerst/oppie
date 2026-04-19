from click.testing import CliRunner

import oppie
from oppie.cli import cli


def test_version_flag_prints_version():
    runner = CliRunner()

    result = runner.invoke(cli, ['--version'])

    assert result.exit_code == 0
    assert oppie.__version__ in result.output
    assert 'oppie' in result.output


def test_version_short_flag_prints_version():
    runner = CliRunner()

    result = runner.invoke(cli, ['-V'])

    assert result.exit_code == 0
    assert oppie.__version__ in result.output
