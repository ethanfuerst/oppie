import logging
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class InstanceType(Enum):
    REPO = 'repo'
    PORTFOLIO = 'portfolio'


class ProviderType(Enum):
    LOCAL = 'local'
    LINEAR = 'linear'


class LLMBackend(Enum):
    OPENAI_COMPATIBLE = 'openai-compatible'
    ANTHROPIC = 'anthropic'


class LLMConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')

    backend: LLMBackend
    model: str
    endpoint: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.7

    @field_validator('max_tokens')
    @classmethod
    def max_tokens_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f'llm.max_tokens must be a positive integer, got {v}')
        return v

    @field_validator('temperature')
    @classmethod
    def temperature_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError(f'llm.temperature must be between 0.0 and 2.0, got {v}')
        return v


class ProviderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra='ignore')

    provider_type: ProviderType = Field(alias='type')
    api_key: str | None = None

    def to_dict(self) -> dict:
        """Serialize to dict. Exclude api_key — never write credentials to oppie.yaml."""
        return {'type': self.provider_type.value}


class OppieConfig(BaseModel):
    model_config = ConfigDict(extra='ignore')

    instance_type: InstanceType
    provider: ProviderConfig
    llm: LLMConfig


def resolve_api_key(config: ProviderConfig) -> str:
    """Resolve API key from config (provider.yaml), then env var fallback.

    Env var name is derived from provider type: e.g. LINEAR -> LINEAR_API_KEY.
    """
    logger.debug('Resolving API key for %s', config.provider_type.value)
    if config.api_key:
        return config.api_key
    env_var = f'{config.provider_type.value.upper()}_API_KEY'
    env_key = os.environ.get(env_var)
    if env_key:
        return env_key
    raise ValueError(
        f'{config.provider_type.value.capitalize()} API key not found. '
        f'Set it in config/provider.yaml or the {env_var} environment variable.'
    )


def load_oppie_config(config_dir: Path) -> OppieConfig:
    """Load and validate oppie.yaml from the given config directory."""
    config_path = config_dir / 'oppie.yaml'
    logger.debug('Loading config from %s', config_path)
    if not config_path.exists():
        raise FileNotFoundError(f'Config file not found: {config_path}')

    with open(config_path) as f:
        data = yaml.safe_load(f)

    if data is None:
        raise ValueError(f'Config file is empty: {config_path}')

    # Dispatch provider config to the right subclass
    provider_data = data.get('provider', {})
    provider_type = provider_data.get('type', 'local')
    if provider_type == 'linear':
        # Deferred import: circular dependency (config <- providers.linear.config)
        from oppie.providers.linear.config import LinearProviderConfig

        data['provider'] = LinearProviderConfig(**provider_data)

    config = OppieConfig(**data)
    logger.debug(
        'Config loaded: instance_type=%s provider=%s',
        config.instance_type.value,
        config.provider.provider_type.value,
    )
    return config


def load_provider_credentials(config_dir: Path) -> dict[str, Any]:
    """Load provider.yaml credentials. Return empty dict if file missing or empty."""
    creds_path = config_dir / 'provider.yaml'
    logger.debug(
        'Loading provider credentials from %s (found=%s)',
        creds_path,
        creds_path.exists(),
    )
    if not creds_path.exists():
        return {}

    with open(creds_path) as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}

    return dict(data)


def load_config(config_dir: Path) -> OppieConfig:
    """Load oppie.yaml and merge provider.yaml credentials."""
    config = load_oppie_config(config_dir)
    credentials = load_provider_credentials(config_dir)
    if 'api_key' in credentials:
        config.provider.api_key = credentials['api_key']
    return config


def save_oppie_config(config_dir: Path, config: OppieConfig) -> Path:
    """Write oppie.yaml to the config directory. Atomic write."""
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / 'oppie.yaml'
    logger.debug('Saving config to %s', target)

    data: dict[str, Any] = {
        'instance_type': config.instance_type.value,
        'provider': config.provider.to_dict(),
        'llm': {
            'backend': config.llm.backend.value,
            'model': config.llm.model,
        },
    }
    if config.llm.endpoint:
        data['llm']['endpoint'] = config.llm.endpoint
    if config.llm.max_tokens != 2000:
        data['llm']['max_tokens'] = config.llm.max_tokens
    if config.llm.temperature != 0.7:
        data['llm']['temperature'] = config.llm.temperature

    fd, tmp = tempfile.mkstemp(dir=config_dir, suffix='.tmp')
    try:
        with open(fd, 'w') as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
        Path(tmp).replace(target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    return target


def save_provider_credentials(config_dir: Path, credentials: dict[str, Any]) -> Path:
    """Write provider.yaml credentials. Atomic write."""
    config_dir.mkdir(parents=True, exist_ok=True)
    target = config_dir / 'provider.yaml'
    logger.debug('Saving provider credentials to %s', target)

    fd, tmp = tempfile.mkstemp(dir=config_dir, suffix='.tmp')
    try:
        with open(fd, 'w') as f:
            yaml.safe_dump(credentials, f, default_flow_style=False, sort_keys=False)
        Path(tmp).replace(target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise

    return target
