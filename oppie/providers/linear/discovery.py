from __future__ import annotations

from typing import Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

_GRAPHQL_ENDPOINT = 'https://api.linear.app/graphql'

_TEAMS_QUERY = """
query Teams {
  teams {
    nodes { id name key }
  }
}
"""

_TEAM_PROJECTS_QUERY = """
query TeamProjects($teamId: String!) {
  team(id: $teamId) {
    projects {
      nodes { id name }
    }
  }
}
"""


def _graphql(api_key: str, query: str, variables: dict | None = None) -> dict:
    """Execute a GraphQL query against Linear. Raise on errors."""
    if httpx is None:
        raise ImportError(
            "Linear provider requires the 'linear' extra. "
            "Install with: pip install 'oppie[linear]'"
        )
    payload: dict[str, Any] = {'query': query}
    if variables:
        payload['variables'] = variables

    resp = httpx.post(
        _GRAPHQL_ENDPOINT,
        json=payload,
        headers={'Authorization': api_key},
        timeout=30.0,
    )

    if resp.status_code == 401:
        raise ValueError('Invalid Linear API key (HTTP 401).')
    resp.raise_for_status()

    body = resp.json()
    if 'errors' in body:
        msgs = [e.get('message', str(e)) for e in body['errors']]
        raise ValueError(f'Linear API error: {"; ".join(msgs)}')

    return dict(body.get('data', {}))


def test_api_key(api_key: str) -> bool:
    """Test whether a Linear API key is valid by fetching teams."""
    try:
        _graphql(api_key, _TEAMS_QUERY)
        return True
    except (ValueError, Exception):
        return False


def list_teams(api_key: str) -> list[dict[str, str]]:
    """List teams in the workspace. Returns [{'id': ..., 'name': ..., 'key': ...}]."""
    data = _graphql(api_key, _TEAMS_QUERY)
    result: list[dict[str, str]] = data.get('teams', {}).get('nodes', [])
    return result


def list_projects(api_key: str, team_id: str) -> list[dict[str, str]]:
    """List projects for a team. Returns [{'id': ..., 'name': ...}]."""
    data = _graphql(api_key, _TEAM_PROJECTS_QUERY, {'teamId': team_id})
    result: list[dict[str, str]] = (
        data.get('team', {}).get('projects', {}).get('nodes', [])
    )
    return result
