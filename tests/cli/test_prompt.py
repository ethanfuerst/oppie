from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from oppie.cli import cli


def test_prompt_no_instance(tmp_path):
    runner = CliRunner()

    result = runner.invoke(cli, ['--home', str(tmp_path), 'what is blocking?'])

    assert result.exit_code != 0
    assert 'No oppie instance' in result.output


def test_prompt_ambiguous():
    """Single word with no clear intent shows ambiguous error."""
    runner = CliRunner()

    with patch('oppie.instance.Instance') as mock_instance_cls:
        mock_instance_cls.detect.return_value = '/fake/home'
        mock_instance_cls.load.return_value = MagicMock(config=None)

        with patch('oppie.providers.local.LocalProvider') as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.list_tickets.return_value = []
            mock_provider_cls.setup.return_value = mock_provider

            with patch('oppie.sync.auto_sync') as mock_sync:
                mock_sync.return_value = MagicMock(
                    synced=False, error=None, ticket_count=0
                )

                result = runner.invoke(cli, ['bugs'])

    assert result.exit_code != 0
    assert 'Could not determine intent' in result.output
