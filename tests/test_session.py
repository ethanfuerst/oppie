import json

import pytest

from oppie.session import MAX_RECENT_RUNS, Session, SessionData, generate_session_id


def test_session_data_roundtrip():
    data = SessionData(
        session_id='s-abc',
        active_plan_id='p-abc',
        recent_run_ids=['r-1', 'r-2'],
        last_command_at='2026-03-21T14:30:00+00:00',
    )

    assert SessionData.from_dict(data.to_dict()) == data


def test_session_data_roundtrip_empty():
    data = SessionData()
    restored = SessionData.from_dict(data.to_dict())

    assert restored == data
    assert restored.session_id == ''
    assert restored.active_plan_id is None
    assert restored.recent_run_ids == []
    assert restored.last_command_at is None


def test_generate_session_id_unique():
    ids = {generate_session_id() for _ in range(100)}

    assert len(ids) == 100


def test_create_session(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    assert session.session_id
    assert (tmp_path / 'state' / f'session-{session.session_id}.json').exists()
    assert session.get_last_command_at() is not None


def test_load_session(tmp_path):
    (tmp_path / 'state').mkdir()
    created = Session.create(tmp_path)
    created.set_active_plan('p-abc')

    loaded = Session.load(tmp_path, created.session_id)

    assert loaded.get_active_plan() == 'p-abc'


def test_load_session_not_found(tmp_path):
    (tmp_path / 'state').mkdir()

    with pytest.raises(FileNotFoundError, match='Session not found'):
        Session.load(tmp_path, 'nonexistent-id')


def test_load_latest_returns_most_recent(tmp_path):
    (tmp_path / 'state').mkdir()
    Session.create(tmp_path)
    s2 = Session.create(tmp_path)
    # s2 was created last, so it's the latest
    s2.set_active_plan('p-latest')

    latest = Session.load_latest(tmp_path)

    assert latest is not None
    assert latest.session_id == s2.session_id
    assert latest.get_active_plan() == 'p-latest'


def test_load_latest_no_sessions(tmp_path):
    (tmp_path / 'state').mkdir()

    assert Session.load_latest(tmp_path) is None


def test_load_latest_no_state_dir(tmp_path):
    assert Session.load_latest(tmp_path) is None


def test_get_active_plan_no_file(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session(tmp_path, 'test-id')

    assert session.get_active_plan() is None


def test_set_and_get_active_plan(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    session.set_active_plan('p-abc123')

    assert session.get_active_plan() == 'p-abc123'


def test_set_active_plan_updates_last_command_at(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)
    first_ts = session.get_last_command_at()

    session.set_active_plan('p-abc')

    assert session.get_last_command_at() is not None
    assert session.get_last_command_at() >= first_ts


def test_active_plan_persists_no_expiry(tmp_path):
    """Active plan is sticky — no auto-expiry."""
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)
    session.set_active_plan('p-abc')

    # Re-load to prove persistence
    session2 = Session.load(tmp_path, session.session_id)

    assert session2.get_active_plan() == 'p-abc'


def test_add_run_id(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    session.add_run_id('r-1')
    session.add_run_id('r-2')

    assert session.get_recent_run_ids() == ['r-1', 'r-2']


def test_add_run_id_bounded(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)
    for i in range(MAX_RECENT_RUNS + 5):
        session.add_run_id(f'r-{i}')

    result = session.get_recent_run_ids()

    assert len(result) == MAX_RECENT_RUNS
    assert result[0] == f'r-{5}'
    assert result[-1] == f'r-{MAX_RECENT_RUNS + 4}'


def test_touch(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    session.touch()

    assert session.get_last_command_at() is not None


def test_clear_preserves_session_id(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)
    session.set_active_plan('p-abc')
    session.add_run_id('r-1')

    session.clear()

    assert session.session_id  # still has ID
    assert session.get_active_plan() is None
    assert session.get_recent_run_ids() == []
    assert session.get_last_command_at() is None


def test_corrupted_file_returns_defaults(tmp_path):
    (tmp_path / 'state').mkdir()
    session_id = 'corrupt-test'
    (tmp_path / 'state' / f'session-{session_id}.json').write_text('not json{{{')
    session = Session(tmp_path, session_id)

    assert session.get_active_plan() is None
    assert session.get_recent_run_ids() == []


def test_save_creates_state_dir(tmp_path):
    """_save creates state/ dir if missing."""
    session = Session.create(tmp_path)

    assert (tmp_path / 'state' / f'session-{session.session_id}.json').exists()


def test_save_cleans_up_on_error(tmp_path, monkeypatch):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    def failing_replace(self, target):
        raise OSError('disk full')

    monkeypatch.setattr(type(tmp_path), 'replace', failing_replace)

    with pytest.raises(OSError, match='disk full'):
        session.touch()

    tmp_files = list((tmp_path / 'state').glob('*.tmp'))

    assert tmp_files == []


def test_multiple_sessions_independent(tmp_path):
    """Two sessions in the same home don't interfere with each other."""
    (tmp_path / 'state').mkdir()
    s1 = Session.create(tmp_path)
    s2 = Session.create(tmp_path)

    s1.set_active_plan('p-plan-a')
    s2.set_active_plan('p-plan-b')

    assert s1.get_active_plan() == 'p-plan-a'
    assert s2.get_active_plan() == 'p-plan-b'


def test_session_file_contains_session_id(tmp_path):
    (tmp_path / 'state').mkdir()
    session = Session.create(tmp_path)

    raw = json.loads(
        (tmp_path / 'state' / f'session-{session.session_id}.json').read_text()
    )

    assert raw['session_id'] == session.session_id
