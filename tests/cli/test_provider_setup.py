import pytest

from oppie.cli.provider_setup import setup_provider
from oppie.config import load_oppie_config
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.sync import SyncResult
from oppie.providers.base import ExternalProvider, ProviderNetworkError
from oppie.providers.local import LocalProvider
from tests.cli.conftest import setup_cli_instance


def _setup_linear_instance(tmp_path):
    home = setup_cli_instance(tmp_path)
    (home / 'config' / 'oppie.yaml').write_text(
        'instance_type: repo\n'
        'provider:\n'
        '  type: linear\n'
        '  team_id: TEAM1\n'
        '  api_key: dummy-key\n'
        'llm:\n'
        '  backend: openai-compatible\n'
        '  model: test\n'
    )
    return home


class FakeLinearProvider(ExternalProvider):
    """ExternalProvider subclass so auto_sync's isinstance check fires."""

    instances: list['FakeLinearProvider'] = []
    sync_exc: Exception | None = None

    def __init__(self, home=None, cache=None, config=None) -> None:
        self._home = home
        self.cache = cache
        self.config = config
        self.sync_calls = 0
        self.close_called = 0
        FakeLinearProvider.instances.append(self)

    @property
    def home(self):
        return self._home

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities()

    @property
    def version(self) -> str:
        return 'v1'

    def read_ticket(self, ticket_id):
        return None

    def update_ticket(self, ticket_id, updates):
        raise NotImplementedError

    def list_tickets(self):
        return []

    def sync(self, checkpoint=None):
        self.sync_calls += 1
        if FakeLinearProvider.sync_exc:
            raise FakeLinearProvider.sync_exc
        return SyncResult(tickets_upserted=0)

    def apply(self, operations):
        return []

    def test_connection(self) -> None:
        return None

    def flush_outbox(self):
        return []

    def close(self) -> None:
        self.close_called += 1


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch):
    FakeLinearProvider.instances = []
    FakeLinearProvider.sync_exc = None
    monkeypatch.setattr(
        'oppie.providers.linear.LinearProvider', FakeLinearProvider, raising=False
    )
    yield


def test_local_dispatch_yields_local_provider(tmp_path):
    home = setup_cli_instance(tmp_path)
    config = load_oppie_config(home / 'config')

    with setup_provider(home, config) as (provider, result):
        assert isinstance(provider, LocalProvider)
        assert result.synced is False
        assert result.error is None


def test_no_sync_prints_cached_message(tmp_path, capsys):
    home = setup_cli_instance(tmp_path)
    config = load_oppie_config(home / 'config')

    with setup_provider(home, config, no_sync=True) as (_, result):
        assert result.synced is False

    out = capsys.readouterr().out

    assert 'Using cached data' in out


def test_linear_dispatch_runs_sync_and_closes(tmp_path, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')

    with setup_provider(home, config) as (provider, result):
        assert isinstance(provider, FakeLinearProvider)
        assert provider.sync_calls == 1
        assert result.synced is True

    inst = FakeLinearProvider.instances[-1]
    out = capsys.readouterr().out

    assert inst.close_called == 1
    assert 'Synced' in out


def test_linear_sync_failure_warns_and_closes(tmp_path, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    FakeLinearProvider.sync_exc = ProviderNetworkError('unreachable')

    with setup_provider(home, config) as (_, result):
        assert result.synced is False
        assert result.error == 'unreachable'

    inst = FakeLinearProvider.instances[-1]
    out = capsys.readouterr().out

    assert inst.close_called == 1
    assert 'Sync failed' in out
    assert 'unreachable' in out


def test_linear_missing_extra_exits(tmp_path, monkeypatch, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    monkeypatch.setattr(
        'oppie.cli.provider_setup.extras_available',
        lambda: {'linear': False, 'llm': False, 'tui': False},
    )

    with pytest.raises(SystemExit) as excinfo, setup_provider(home, config):
        pass

    assert excinfo.value.code == 1
    out = capsys.readouterr().out

    assert 'pip install' in out
    assert "'oppie[linear]'" in out


def test_linear_value_error_falls_back_to_cache(tmp_path, monkeypatch, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')

    def _raise(*args, **kwargs):
        raise ValueError('no api key')

    monkeypatch.setattr('oppie.providers.factory.create_external_provider', _raise)

    with setup_provider(home, config) as (provider, result):
        assert isinstance(provider, LocalProvider)
        assert result.synced is False

    out = capsys.readouterr().out

    assert 'Linear provider unavailable' in out
    assert 'no api key' in out


def test_print_sync_success_false_suppresses_synced_line(tmp_path, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')

    with setup_provider(home, config, print_sync_success=False) as (_, result):
        assert result.synced is True

    out = capsys.readouterr().out

    assert 'Synced' not in out


def test_print_sync_success_false_still_prints_error(tmp_path, capsys):
    home = _setup_linear_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    FakeLinearProvider.sync_exc = ProviderNetworkError('boom')

    with setup_provider(home, config, print_sync_success=False) as (_, result):
        assert result.synced is False

    out = capsys.readouterr().out

    assert 'Sync failed' in out


def test_unsupported_provider_type_raises(tmp_path, monkeypatch):
    home = setup_cli_instance(tmp_path)
    config = load_oppie_config(home / 'config')
    monkeypatch.setattr(config.provider, 'provider_type', 'bogus', raising=False)

    with (
        pytest.raises(ValueError, match='Unsupported provider type'),
        setup_provider(home, config),
    ):
        pass
