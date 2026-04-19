import json
from dataclasses import dataclass, field

import pytest
from click.testing import CliRunner

from oppie.models.plan import Plan, PlanStatus
from tests.helpers import setup_instance


@dataclass
class FakeStatus:
    """Test stand-in for `rich.status.Status` — records label updates."""

    label: str
    spinner: str = 'dots'
    updates: list[str] = field(default_factory=list)
    started: bool = False
    stopped: bool = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def update(self, status: str | None = None, **_: object) -> None:
        if status is not None:
            self.updates.append(status)
            self.label = status


def install_fake_status(monkeypatch, console):
    """Patch `console.status` to return FakeStatus instances; return the list."""
    created: list[FakeStatus] = []

    def _status(label, spinner='dots', **_):
        fake = FakeStatus(label=label, spinner=spinner)
        created.append(fake)
        return fake

    monkeypatch.setattr(console, 'status', _status)
    return created


def setup_cli_instance(tmp_path):
    """Create a minimal instance with marker and config for CLI tests."""
    home = setup_instance(tmp_path)

    # Write .oppie-marker (required by Instance.detect)
    marker = {'version': '0.0.1', 'instance_type': 'repo'}
    (home / '.oppie-marker').write_text(json.dumps(marker, indent=2) + '\n')

    # Write minimal config
    config_dir = home / 'config'
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / 'oppie.yaml').write_text(
        'instance_type: repo\n'
        'provider:\n  type: local\n'
        'llm:\n  backend: openai-compatible\n  model: test\n'
    )

    return home


@pytest.fixture
def home(tmp_path):
    return setup_cli_instance(tmp_path)


@pytest.fixture
def runner():
    return CliRunner()


def make_and_save_plan(
    home,
    operations,
    status=PlanStatus.SAVED,
    ticket_snapshots=None,
    checked=False,
):
    """Create a plan with auto-computed plan_id and save it."""
    plan = Plan(
        instruction='test instruction',
        operations=operations,
        risks=[],
        created_at='2026-01-01T00:00:00Z',
        status=status,
        ticket_snapshots=ticket_snapshots,
        checked=checked,
    )
    plan.save(home)
    return plan
