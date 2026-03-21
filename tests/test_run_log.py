from oppie.run_log import RunLog, RunLogEntry, generate_run_id


def test_run_log_entry_roundtrip():
    entry = RunLogEntry(
        run_id='r-1',
        command='ask',
        timestamp='2026-03-21T14:30:22+00:00',
        duration=1.5,
        artifact_paths=['/artifacts/ask/ask-20260321T143022-r-1.md'],
        plan_id='p-1',
        apply_id=None,
        token_usage={'prompt_tokens': 100, 'completion_tokens': 50},
    )

    assert RunLogEntry.from_dict(entry.to_dict()) == entry


def test_run_log_entry_roundtrip_minimal():
    entry = RunLogEntry(run_id='r-2', command='ask', timestamp='t', duration=0.0)
    restored = RunLogEntry.from_dict(entry.to_dict())

    assert restored == entry
    assert restored.artifact_paths == []
    assert restored.plan_id is None
    assert restored.token_usage is None


def test_run_log_append_and_query(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    entry = RunLogEntry(run_id='r-1', command='ask', timestamp='t', duration=1.0)

    log.append(entry)
    results = log.query()

    assert len(results) == 1
    assert results[0] == entry


def test_run_log_append_is_additive(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    e1 = RunLogEntry(run_id='r-1', command='ask', timestamp='t1', duration=1.0)
    e2 = RunLogEntry(run_id='r-2', command='plan', timestamp='t2', duration=2.0)
    e3 = RunLogEntry(run_id='r-3', command='ask', timestamp='t3', duration=0.5)

    log.append(e1)
    log.append(e2)
    log.append(e3)
    results = log.query()

    assert len(results) == 3
    assert results[0] == e1
    assert results[1] == e2
    assert results[2] == e3


def test_run_log_query_filter_by_command(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    e1 = RunLogEntry(run_id='r-1', command='ask', timestamp='t1', duration=1.0)
    e2 = RunLogEntry(run_id='r-2', command='plan', timestamp='t2', duration=2.0)
    e3 = RunLogEntry(run_id='r-3', command='ask', timestamp='t3', duration=0.5)
    log.append(e1)
    log.append(e2)
    log.append(e3)

    results = log.query(command_type='ask')

    assert len(results) == 2
    assert results[0] == e1
    assert results[1] == e3


def test_run_log_query_with_limit(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    for i in range(5):
        log.append(
            RunLogEntry(
                run_id=f'r-{i}', command='ask', timestamp=f't{i}', duration=float(i)
            )
        )

    results = log.query(limit=2)

    assert len(results) == 2
    assert results[0].run_id == 'r-3'
    assert results[1].run_id == 'r-4'


def test_run_log_query_filter_and_limit(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    log.append(RunLogEntry(run_id='r-1', command='ask', timestamp='t1', duration=1.0))
    log.append(RunLogEntry(run_id='r-2', command='plan', timestamp='t2', duration=2.0))
    log.append(RunLogEntry(run_id='r-3', command='ask', timestamp='t3', duration=0.5))
    log.append(RunLogEntry(run_id='r-4', command='ask', timestamp='t4', duration=0.3))

    results = log.query(command_type='ask', limit=1)

    assert len(results) == 1
    assert results[0].run_id == 'r-4'


def test_run_log_query_empty_log(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)

    assert log.query() == []


def test_run_log_query_no_file(tmp_path):
    log = RunLog(tmp_path)

    assert log.query() == []


def test_generate_run_id_unique():
    ids = {generate_run_id() for _ in range(100)}

    assert len(ids) == 100


def test_run_log_entry_with_token_usage(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    entry = RunLogEntry(
        run_id='r-1',
        command='ask',
        timestamp='t',
        duration=1.0,
        token_usage={'prompt_tokens': 200, 'completion_tokens': 100},
    )

    log.append(entry)
    results = log.query()

    assert results[0].token_usage == {'prompt_tokens': 200, 'completion_tokens': 100}


def test_run_log_entry_with_plan_and_apply_ids(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    entry = RunLogEntry(
        run_id='r-1',
        command='apply',
        timestamp='t',
        duration=3.0,
        plan_id='p-abc123',
        apply_id='a-def456',
    )

    log.append(entry)
    results = log.query()

    assert results[0].plan_id == 'p-abc123'
    assert results[0].apply_id == 'a-def456'


def test_run_log_query_skips_blank_lines(tmp_path):
    (tmp_path / 'logs').mkdir()
    log = RunLog(tmp_path)
    entry = RunLogEntry(run_id='r-1', command='ask', timestamp='t', duration=1.0)
    log.append(entry)

    # Inject a blank line into the JSONL file
    log_path = tmp_path / 'logs' / 'runs.jsonl'
    log_path.write_text(log_path.read_text() + '\n')
    results = log.query()

    assert len(results) == 1
    assert results[0] == entry
