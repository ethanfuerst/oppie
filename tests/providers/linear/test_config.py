import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from oppie.config import ProviderType, resolve_api_key
from oppie.providers.linear.config import LinearProviderConfig


def test_linear_config_parses_from_dict():
    config = LinearProviderConfig(type='linear', team_id='team-123')

    assert config.team_id == 'team-123'
    assert config.project_id is None


def test_linear_config_missing_team_id_raises():
    with pytest.raises(ValidationError):
        LinearProviderConfig(type='linear')


def test_linear_config_inherits_provider_type():
    config = LinearProviderConfig(type='linear', team_id='team-123')

    assert config.provider_type == ProviderType.LINEAR


def test_sync_statuses_config():
    config = LinearProviderConfig(
        type='linear',
        team_id='team-123',
        sync_statuses=['Todo', 'In Progress'],
    )

    assert config.sync_statuses == ['Todo', 'In Progress']


def test_sync_labels_config():
    config = LinearProviderConfig(
        type='linear',
        team_id='team-123',
        sync_labels=['backend', 'urgent'],
    )

    assert config.sync_labels == ['backend', 'urgent']


def test_api_key_from_config():
    config = LinearProviderConfig(
        type='linear',
        team_id='t-1',
        api_key='sk-from-config',
    )

    assert resolve_api_key(config) == 'sk-from-config'


def test_api_key_from_env_var():
    config = LinearProviderConfig(type='linear', team_id='t-1')
    with patch.dict(os.environ, {'LINEAR_API_KEY': 'sk-from-env'}):
        result = resolve_api_key(config)

    assert result == 'sk-from-env'


def test_api_key_missing_raises():
    config = LinearProviderConfig(type='linear', team_id='t-1')
    with (
        patch.dict(os.environ, {}, clear=True),
        pytest.raises(ValueError, match='Linear API key not found'),
    ):
        resolve_api_key(config)
