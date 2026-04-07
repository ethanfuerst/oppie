import pytest
from pydantic import ValidationError

from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    ProviderType,
)


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


def test_oppie_config_requires_llm():
    with pytest.raises(ValidationError, match='llm'):
        OppieConfig(
            instance_type=InstanceType.REPO,
            provider=ProviderConfig(provider_type=ProviderType.LOCAL),
        )


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
        llm=LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test'),
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
