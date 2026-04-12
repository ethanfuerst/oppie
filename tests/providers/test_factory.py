import pytest

from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    ProviderType,
)
from oppie.providers.factory import create_external_provider
from oppie.providers.linear.config import LinearProviderConfig
from oppie.providers.local import LocalProvider
from tests.helpers import setup_instance


def _llm():
    return LLMConfig(backend=LLMBackend.OPENAI_COMPATIBLE, model='test')


def test_create_external_provider_linear_returns_linear_provider(tmp_path):
    from oppie.providers.linear import LinearProvider

    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=LinearProviderConfig(
            type=ProviderType.LINEAR, team_id='TEAM1', api_key='dummy'
        ),
        llm=_llm(),
    )
    cache = LocalProvider(setup_instance(tmp_path))
    try:
        provider = create_external_provider(config, home=tmp_path, cache=cache)

        assert isinstance(provider, LinearProvider)
    finally:
        cache.close()


def test_create_external_provider_local_raises_value_error(tmp_path):
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type=ProviderType.LOCAL),
        llm=_llm(),
    )
    cache = LocalProvider(setup_instance(tmp_path))
    try:
        with pytest.raises(ValueError, match='local'):
            create_external_provider(config, home=tmp_path, cache=cache)
    finally:
        cache.close()
