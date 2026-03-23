from unittest.mock import MagicMock, patch

from oppie.providers.linear.discovery import list_projects, list_teams
from oppie.providers.linear.discovery import test_api_key as check_api_key


def _mock_response(status_code=200, json_data=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = MagicMock()
    return resp


def test_list_teams():
    teams_data = {
        'data': {
            'teams': {
                'nodes': [
                    {'id': 't1', 'name': 'Engineering', 'key': 'ENG'},
                    {'id': 't2', 'name': 'Design', 'key': 'DES'},
                ]
            }
        }
    }
    with patch('oppie.providers.linear.discovery.httpx') as mock_httpx:
        mock_httpx.post.return_value = _mock_response(json_data=teams_data)
        result = list_teams('lin_api_test')

    assert len(result) == 2
    assert result[0]['name'] == 'Engineering'
    assert result[1]['key'] == 'DES'


def test_list_projects():
    projects_data = {
        'data': {
            'team': {
                'projects': {
                    'nodes': [
                        {'id': 'p1', 'name': 'Alpha'},
                        {'id': 'p2', 'name': 'Beta'},
                    ]
                }
            }
        }
    }
    with patch('oppie.providers.linear.discovery.httpx') as mock_httpx:
        mock_httpx.post.return_value = _mock_response(json_data=projects_data)
        result = list_projects('lin_api_test', 't1')

    assert len(result) == 2
    assert result[0]['name'] == 'Alpha'
    assert result[1]['id'] == 'p2'


def test_api_key_valid():
    teams_data = {
        'data': {'teams': {'nodes': [{'id': 't1', 'name': 'Eng', 'key': 'ENG'}]}}
    }
    with patch('oppie.providers.linear.discovery.httpx') as mock_httpx:
        mock_httpx.post.return_value = _mock_response(json_data=teams_data)
        result = check_api_key('lin_api_valid')

    assert result is True


def test_api_key_invalid():
    with patch('oppie.providers.linear.discovery.httpx') as mock_httpx:
        resp = _mock_response(status_code=401)
        mock_httpx.post.return_value = resp
        result = check_api_key('lin_api_invalid')

    assert result is False
