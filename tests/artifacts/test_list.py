from oppie.artifacts import ArtifactStore, ArtifactType
from tests.artifacts.conftest import create_artifact_dirs


def test_list_artifacts_returns_paths_sorted_by_mtime(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)
    path1 = store.save_artifact(ArtifactType.ASK, 'first', 'r-1')
    path2 = store.save_artifact(ArtifactType.ASK, 'second', 'r-2')

    result = store.list_artifacts(ArtifactType.ASK)

    assert len(result) == 2
    # Newest first
    assert result[0] == path2
    assert result[1] == path1


def test_list_artifacts_empty_directory(tmp_path):
    create_artifact_dirs(tmp_path)
    store = ArtifactStore(tmp_path)

    result = store.list_artifacts(ArtifactType.REPORT)

    assert result == []


def test_list_artifacts_missing_directory(tmp_path):
    store = ArtifactStore(tmp_path)

    result = store.list_artifacts(ArtifactType.REPORT)

    assert result == []
