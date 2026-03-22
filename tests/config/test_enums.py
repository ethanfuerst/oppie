from oppie.config import InstanceType, LLMBackend, ProviderType


def test_instance_type_values():
    assert InstanceType.REPO.value == 'repo'
    assert InstanceType.PORTFOLIO.value == 'portfolio'


def test_provider_type_values():
    assert ProviderType.LOCAL.value == 'local'
    assert ProviderType.LINEAR.value == 'linear'


def test_llm_backend_values():
    assert LLMBackend.OPENAI_COMPATIBLE.value == 'openai-compatible'
    assert LLMBackend.ANTHROPIC.value == 'anthropic'
