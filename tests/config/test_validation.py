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


def test_validate_no_llm_raises():
    with pytest.raises(ValidationError, match='llm'):
        OppieConfig(
            instance_type=InstanceType.REPO,
            provider=ProviderConfig(provider_type=ProviderType.LOCAL),
        )
