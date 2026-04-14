import pytest
from click.testing import CliRunner

from oppie.cli import cli
from oppie.models.apply import OperationResult, OperationStatus
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult
from oppie.providers.base import (
    ProviderAPIError,
    ProviderAuthError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from tests.cli.conftest import setup_cli_instance


def setup_linear_instance(tmp_path):
    """Create a CLI instance configured as a Linear provider."""
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


class FakeLinearProvider:
    """Replacement for LinearProvider that records calls and stages responses."""

    instances: list['FakeLinearProvider'] = []

    flush_results: list[OperationResult] = []
    sync_result: SyncResult | None = None
    sync_exc: Exception | None = None
    flush_exc: Exception | None = None

    def __init__(self, home=None, cache=None, config=None) -> None:
        self.home = home
        self.cache = cache
        self.config = config
        self.flush_called = False
        self.sync_calls: list[dict] = []
        self.close_called = 0
        FakeLinearProvider.instances.append(self)

    def flush_outbox(self):
        self.flush_called = True
        if FakeLinearProvider.flush_exc:
            raise FakeLinearProvider.flush_exc
        return list(FakeLinearProvider.flush_results)

    def sync(self, checkpoint=None):
        self.sync_calls.append({'checkpoint': checkpoint})
        if FakeLinearProvider.sync_exc:
            raise FakeLinearProvider.sync_exc
        return FakeLinearProvider.sync_result or SyncResult(tickets_upserted=0)

    def close(self):
        self.close_called += 1


@pytest.fixture(autouse=True)
def _reset_fake(monkeypatch):
    FakeLinearProvider.instances = []
    FakeLinearProvider.flush_results = []
    FakeLinearProvider.sync_result = None
    FakeLinearProvider.sync_exc = None
    FakeLinearProvider.flush_exc = None
    # Patch the source module — the command imports from there.
    monkeypatch.setattr(
        'oppie.providers.linear.LinearProvider', FakeLinearProvider, raising=False
    )
    yield


def _op():
    return Operation(
        ticket_id='T-1',
        field='status',
        before_value='todo',
        after_value='done',
        rationale='test',
    )


def test_sync_local_instance_no_op(tmp_path):
    home = setup_cli_instance(tmp_path)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 0
    assert 'Nothing to sync' in result.output
    assert FakeLinearProvider.instances == []


def test_sync_linear_missing_extra(tmp_path, monkeypatch):
    home = setup_linear_instance(tmp_path)
    monkeypatch.setattr(
        'oppie.cli.commands.sync.extras_available', lambda: {'linear': False}
    )

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 1
    assert "Linear sync requires the 'linear' extra" in result.output
    assert "pip install 'oppie[linear]'" in result.output


def test_sync_incremental_happy_path(tmp_path):
    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_result = SyncResult(tickets_upserted=3)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 0
    assert 'Sync complete: 3 tickets' in result.output
    inst = FakeLinearProvider.instances[-1]

    assert inst.sync_calls == [{'checkpoint': None}]
    assert inst.close_called == 1


def test_sync_full_passes_empty_checkpoint(tmp_path):
    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_result = SyncResult(tickets_upserted=5)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync', '--full'])

    assert result.exit_code == 0
    assert 'Full sync complete' in result.output
    inst = FakeLinearProvider.instances[-1]

    assert inst.sync_calls == [{'checkpoint': ''}]


def test_sync_no_flush_skips_outbox(tmp_path):
    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_result = SyncResult(tickets_upserted=0)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync', '--no-flush'])

    assert result.exit_code == 0
    inst = FakeLinearProvider.instances[-1]

    assert inst.flush_called is False


def test_sync_flush_reports_failures(tmp_path):
    home = setup_linear_instance(tmp_path)
    op = _op()
    FakeLinearProvider.flush_results = [
        OperationResult(operation=op, status=OperationStatus.OK),
        OperationResult(operation=op, status=OperationStatus.FAILED, error='boom'),
    ]
    FakeLinearProvider.sync_result = SyncResult(tickets_upserted=0)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 0
    assert 'Flushed outbox: 1 ok, 1 failed' in result.output


def test_sync_flush_success_message(tmp_path):
    home = setup_linear_instance(tmp_path)
    op = _op()
    FakeLinearProvider.flush_results = [
        OperationResult(operation=op, status=OperationStatus.OK),
        OperationResult(operation=op, status=OperationStatus.OK),
    ]
    FakeLinearProvider.sync_result = SyncResult(tickets_upserted=0)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 0
    assert 'Flushed outbox: 2 operations' in result.output


def test_sync_auth_error_exit_2(tmp_path):
    from oppie.providers.linear.provider import LinearAuthError

    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = LinearAuthError('bad token')

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 2
    assert 'Authentication failed' in result.output
    assert 'oppie config' in result.output


def test_sync_rate_limit_exit_3(tmp_path):
    from oppie.providers.linear.provider import LinearRateLimitError

    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = LinearRateLimitError('slow down', retry_after=5.0)

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 3
    assert 'Rate limited' in result.output
    assert 'Retry after 5s' in result.output


def test_sync_network_error_exit_4(tmp_path):
    from oppie.providers.base import ProviderNetworkError

    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = ProviderNetworkError('unreachable')

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 4
    assert 'Network error' in result.output


def test_sync_api_error_exit_5(tmp_path):
    from oppie.providers.linear.provider import LinearAPIError

    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = LinearAPIError('bad request')

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 5
    assert 'Provider error' in result.output


def test_sync_closes_provider_on_error(tmp_path):
    from oppie.providers.linear.provider import LinearAPIError

    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = LinearAPIError('fail')

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 5
    inst = FakeLinearProvider.instances[-1]

    assert inst.close_called == 1


def test_sync_reports_result_errors(tmp_path):
    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_result = SyncResult(
        tickets_upserted=1, errors=['partial failure']
    )

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == 0
    assert 'partial failure' in result.output


@pytest.mark.parametrize(
    'exc, expected_exit',
    [
        (ProviderAuthError('nope'), 2),
        (ProviderRateLimitError('slow', retry_after=2.0), 3),
        (ProviderNetworkError('down'), 4),
        (ProviderAPIError('boom'), 5),
    ],
)
def test_sync_abstract_exit_codes(tmp_path, exc, expected_exit):
    home = setup_linear_instance(tmp_path)
    FakeLinearProvider.sync_exc = exc

    result = CliRunner().invoke(cli, ['--home', str(home), 'sync'])

    assert result.exit_code == expected_exit
