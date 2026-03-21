import pytest
import yaml
from pydantic import ValidationError

from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    ProviderType,
    load_config,
    load_oppie_config,
    load_provider_credentials,
)

# --- Enum tests ---


def test_instance_type_values():
    assert InstanceType.REPO.value == 'repo'
    assert InstanceType.PORTFOLIO.value == 'portfolio'


def test_provider_type_values():
    assert ProviderType.LOCAL.value == 'local'
    assert ProviderType.LINEAR.value == 'linear'


def test_llm_backend_values():
    assert LLMBackend.OPENAI_COMPATIBLE.value == 'openai-compatible'
    assert LLMBackend.ANTHROPIC.value == 'anthropic'


# --- Model tests ---


def test_llm_config_defaults():
    config = LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3')

    assert config.endpoint is None
    assert config.max_tokens == 2000
    assert config.temperature == 0.7


def test_provider_config_defaults():
    config = ProviderConfig(provider_type=ProviderType.LOCAL)

    assert config.api_key is None


def test_provider_config_to_dict_excludes_api_key():
    config = ProviderConfig(provider_type=ProviderType.LINEAR, api_key='sk-secret')
    d = config.to_dict()

    assert d == {'type': 'linear'}
    assert 'api_key' not in d


def test_oppie_config_without_llm():
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(provider_type=ProviderType.LOCAL),
    )

    assert config.llm is None


def test_oppie_config_with_llm():
    llm = LLMConfig(
        backend=LLMBackend.OPENAI_COMPATIBLE,
        model='llama-3.2-8b',
        endpoint='http://localhost:8080/v1',
        max_tokens=4000,
        temperature=0.5,
    )
    config = OppieConfig(
        instance_type=InstanceType.PORTFOLIO,
        provider=ProviderConfig(provider_type=ProviderType.LINEAR),
        llm=llm,
    )

    assert config.llm.backend == LLMBackend.OPENAI_COMPATIBLE
    assert config.llm.model == 'llama-3.2-8b'
    assert config.llm.endpoint == 'http://localhost:8080/v1'
    assert config.llm.max_tokens == 4000
    assert config.llm.temperature == 0.5


def test_oppie_config_ignores_extra_fields():
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(provider_type=ProviderType.LOCAL),
        future_feature=True,
    )

    assert config.instance_type == InstanceType.REPO
    assert not hasattr(config, 'future_feature')


def test_oppie_config_json_schema():
    schema = OppieConfig.model_json_schema()

    assert 'properties' in schema
    assert 'instance_type' in schema['properties']
    assert 'provider' in schema['properties']
    assert 'llm' in schema['properties']


# --- Validation tests ---


def test_validate_max_tokens_zero():
    with pytest.raises(ValidationError, match='max_tokens'):
        LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3', max_tokens=0)


def test_validate_max_tokens_negative():
    with pytest.raises(ValidationError, match='max_tokens'):
        LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3', max_tokens=-1)


def test_validate_temperature_too_high():
    with pytest.raises(ValidationError, match='temperature'):
        LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3', temperature=2.1)


def test_validate_temperature_too_low():
    with pytest.raises(ValidationError, match='temperature'):
        LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3', temperature=-0.1)


def test_validate_valid_config():
    config = LLMConfig(backend=LLMBackend.ANTHROPIC, model='claude-3')

    assert config.max_tokens == 2000
    assert config.temperature == 0.7


def test_validate_no_llm_is_valid():
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(provider_type=ProviderType.LOCAL),
    )

    assert config.llm is None


# --- YAML loading tests ---


def _write_yaml(path, data):
    """Helper to write YAML data to a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f)


def test_load_oppie_config_minimal(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {'instance_type': 'repo', 'provider': {'type': 'local'}},
    )
    config = load_oppie_config(tmp_path)

    assert config.instance_type == InstanceType.REPO
    assert config.provider.provider_type == ProviderType.LOCAL
    assert config.llm is None


def test_load_oppie_config_full(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {
            'instance_type': 'portfolio',
            'provider': {'type': 'linear'},
            'llm': {
                'backend': 'openai-compatible',
                'model': 'llama-3.2-8b',
                'endpoint': 'http://localhost:8080/v1',
                'max_tokens': 4000,
                'temperature': 0.5,
            },
        },
    )
    config = load_oppie_config(tmp_path)

    assert config.instance_type == InstanceType.PORTFOLIO
    assert config.provider.provider_type == ProviderType.LINEAR
    assert config.llm is not None
    assert config.llm.backend == LLMBackend.OPENAI_COMPATIBLE
    assert config.llm.model == 'llama-3.2-8b'
    assert config.llm.endpoint == 'http://localhost:8080/v1'
    assert config.llm.max_tokens == 4000
    assert config.llm.temperature == 0.5


def test_load_oppie_config_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match='Config file not found'):
        load_oppie_config(tmp_path)


def test_load_oppie_config_empty_file(tmp_path):
    (tmp_path / 'oppie.yaml').write_text('')

    with pytest.raises(ValueError, match='Config file is empty'):
        load_oppie_config(tmp_path)


def test_load_oppie_config_invalid_instance_type(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {'instance_type': 'banana', 'provider': {'type': 'local'}},
    )

    with pytest.raises(ValidationError, match='instance_type'):
        load_oppie_config(tmp_path)


def test_load_oppie_config_invalid_provider_type(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {'instance_type': 'repo', 'provider': {'type': 'jira'}},
    )

    with pytest.raises(ValidationError, match='provider'):
        load_oppie_config(tmp_path)


def test_load_oppie_config_invalid_llm_backend(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {
            'instance_type': 'repo',
            'provider': {'type': 'local'},
            'llm': {'backend': 'gpt', 'model': 'x'},
        },
    )

    with pytest.raises(ValidationError, match='backend'):
        load_oppie_config(tmp_path)


def test_load_oppie_config_ignores_unknown_keys(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {
            'instance_type': 'repo',
            'provider': {'type': 'local'},
            'future_feature': True,
        },
    )
    config = load_oppie_config(tmp_path)

    assert config.instance_type == InstanceType.REPO


def test_load_oppie_config_invalid_temperature(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {
            'instance_type': 'repo',
            'provider': {'type': 'local'},
            'llm': {
                'backend': 'anthropic',
                'model': 'claude-3',
                'temperature': 5.0,
            },
        },
    )

    with pytest.raises(ValidationError, match='temperature'):
        load_oppie_config(tmp_path)


def test_load_provider_credentials_with_api_key(tmp_path):
    _write_yaml(tmp_path / 'provider.yaml', {'api_key': 'sk-test'})
    creds = load_provider_credentials(tmp_path)

    assert creds == {'api_key': 'sk-test'}


def test_load_provider_credentials_missing_file(tmp_path):
    creds = load_provider_credentials(tmp_path)

    assert creds == {}


def test_load_provider_credentials_empty_file(tmp_path):
    (tmp_path / 'provider.yaml').write_text('')
    creds = load_provider_credentials(tmp_path)

    assert creds == {}


def test_load_config_merges_credentials(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {'instance_type': 'repo', 'provider': {'type': 'linear'}},
    )
    _write_yaml(tmp_path / 'provider.yaml', {'api_key': 'sk-merged'})
    config = load_config(tmp_path)

    assert config.provider.api_key == 'sk-merged'


def test_load_config_no_credentials(tmp_path):
    _write_yaml(
        tmp_path / 'oppie.yaml',
        {'instance_type': 'repo', 'provider': {'type': 'local'}},
    )
    config = load_config(tmp_path)

    assert config.provider.api_key is None
