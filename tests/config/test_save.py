import yaml

from oppie.config import (
    InstanceType,
    LLMBackend,
    LLMConfig,
    OppieConfig,
    ProviderConfig,
    load_oppie_config,
    save_oppie_config,
    save_provider_credentials,
)


def test_save_oppie_config_writes_yaml(tmp_path):
    config_dir = tmp_path / 'config'
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
    )

    result = save_oppie_config(config_dir, config)

    assert result == config_dir / 'oppie.yaml'
    assert result.exists()

    loaded = load_oppie_config(config_dir)
    assert loaded.instance_type == InstanceType.REPO
    assert loaded.provider.provider_type.value == 'local'
    assert loaded.llm is None


def test_save_oppie_config_with_llm(tmp_path):
    config_dir = tmp_path / 'config'
    config = OppieConfig(
        instance_type=InstanceType.PORTFOLIO,
        provider=ProviderConfig(type='local'),
        llm=LLMConfig(
            backend=LLMBackend.ANTHROPIC,
            model='claude-sonnet-4-20250514',
        ),
    )

    save_oppie_config(config_dir, config)

    loaded = load_oppie_config(config_dir)
    assert loaded.llm is not None
    assert loaded.llm.backend == LLMBackend.ANTHROPIC
    assert loaded.llm.model == 'claude-sonnet-4-20250514'
    assert loaded.llm.endpoint is None


def test_save_oppie_config_with_llm_custom_values(tmp_path):
    config_dir = tmp_path / 'config'
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
        llm=LLMConfig(
            backend=LLMBackend.OPENAI_COMPATIBLE,
            model='llama-3.2-8b',
            endpoint='http://localhost:8080/v1',
            max_tokens=4000,
            temperature=0.5,
        ),
    )

    save_oppie_config(config_dir, config)

    loaded = load_oppie_config(config_dir)
    assert loaded.llm is not None
    assert loaded.llm.endpoint == 'http://localhost:8080/v1'
    assert loaded.llm.max_tokens == 4000
    assert loaded.llm.temperature == 0.5


def test_save_oppie_config_omits_default_llm_values(tmp_path):
    config_dir = tmp_path / 'config'
    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
        llm=LLMConfig(
            backend=LLMBackend.ANTHROPIC,
            model='claude-sonnet-4-20250514',
            max_tokens=2000,
            temperature=0.7,
        ),
    )

    save_oppie_config(config_dir, config)

    raw = yaml.safe_load((config_dir / 'oppie.yaml').read_text())
    assert 'max_tokens' not in raw['llm']
    assert 'temperature' not in raw['llm']


def test_save_provider_credentials(tmp_path):
    config_dir = tmp_path / 'config'
    creds = {'api_key': 'lin_api_test123'}

    result = save_provider_credentials(config_dir, creds)

    assert result == config_dir / 'provider.yaml'
    assert result.exists()

    loaded = yaml.safe_load(result.read_text())
    assert loaded['api_key'] == 'lin_api_test123'


def test_save_oppie_config_atomic_cleanup(tmp_path):
    config_dir = tmp_path / 'config'
    config_dir.mkdir(parents=True)

    config = OppieConfig(
        instance_type=InstanceType.REPO,
        provider=ProviderConfig(type='local'),
    )
    save_oppie_config(config_dir, config)

    # Verify no temp files left behind
    tmp_files = list(config_dir.glob('*.tmp'))

    assert tmp_files == []
