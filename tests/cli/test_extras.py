from unittest.mock import patch

from oppie.cli.extras import extras_available


def test_extras_available_all_installed():
    with patch('oppie.cli.extras._try_import', return_value=True):
        result = extras_available()

    assert result == {'linear': True, 'llm': True, 'tui': True}


def test_extras_available_none_installed():
    with patch('oppie.cli.extras._try_import', return_value=False):
        result = extras_available()

    assert result == {'linear': False, 'llm': False, 'tui': False}


def test_extras_httpx_controls_linear_and_llm():
    def mock_import(name):
        return name == 'httpx'

    with patch('oppie.cli.extras._try_import', side_effect=mock_import):
        result = extras_available()

    assert result['linear'] is True
    assert result['llm'] is True
    assert result['tui'] is False
