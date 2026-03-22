import re

import pytest

from oppie.artifacts import _TYPE_DIRS, ArtifactStore, ArtifactType
from tests.artifacts.conftest import create_artifact_dirs


def test_save_and_read_artifact(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)
    content = '# Ask artifact\nSome content here.'
    run_id = 'abc-123'

    path = store.save_artifact(ArtifactType.ASK, content, run_id)

    assert path.exists()
    assert path.parent == tmp_path / 'artifacts' / 'ask'
    assert 'ask-' in path.name
    assert run_id in path.name
    assert path.suffix == '.json'
    assert store.read_artifact(path) == content


def test_save_artifact_each_type(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)

    expected_dirs = {
        ArtifactType.ASK: 'ask',
        ArtifactType.PLAN: 'plans',
        ArtifactType.APPLY: 'applies',
        ArtifactType.REPORT: 'reports',
        ArtifactType.CONTEXT: 'context',
    }

    for artifact_type, subdir_name in expected_dirs.items():
        path = store.save_artifact(
            artifact_type, f'{artifact_type.value} content', 'r-1'
        )

        assert path.exists()
        assert path.parent == tmp_path / 'artifacts' / subdir_name
        assert path.name.startswith(f'{artifact_type.value}-')


def test_save_artifact_no_overwrite(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)

    path1 = store.save_artifact(ArtifactType.ASK, 'content one', 'run-1')
    path2 = store.save_artifact(ArtifactType.ASK, 'content two', 'run-2')

    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
    assert store.read_artifact(path1) == 'content one'
    assert store.read_artifact(path2) == 'content two'


def test_read_artifact_missing_file(tmp_path):
    store = ArtifactStore(tmp_path)

    with pytest.raises(FileNotFoundError):
        store.read_artifact(tmp_path / 'nonexistent.json')


def test_save_artifact_creates_subdir(tmp_path):
    store = ArtifactStore(tmp_path)

    path = store.save_artifact(ArtifactType.REPORT, 'report content', 'r-1')

    assert path.exists()
    assert path.parent == tmp_path / 'artifacts' / 'reports'


def test_artifact_filename_format(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)
    run_id = 'test-run-id'

    path = store.save_artifact(ArtifactType.ASK, 'content', run_id)

    # Pattern: {type}-{YYYYMMDDTHHMMSS}-{run_id}.json
    assert re.match(r'ask-\d{8}T\d{6}-test-run-id\.json', path.name)


def test_type_dirs_covers_all_artifact_types():
    for artifact_type in ArtifactType:
        assert artifact_type in _TYPE_DIRS


def test_save_artifact_empty_content(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)

    path = store.save_artifact(ArtifactType.ASK, '', 'r-1')

    assert path.exists()
    assert store.read_artifact(path) == ''


def test_save_artifact_cleans_up_on_error(tmp_path, monkeypatch):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)

    def failing_replace(self, target):
        raise OSError('disk full')

    monkeypatch.setattr(type(tmp_path), 'replace', failing_replace)

    with pytest.raises(OSError, match='disk full'):
        store.save_artifact(ArtifactType.ASK, 'content', 'r-1')

    # No .tmp files left behind
    tmp_files = list((tmp_path / 'artifacts' / 'ask').glob('*.tmp'))

    assert tmp_files == []
