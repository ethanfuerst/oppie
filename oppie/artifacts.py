import tempfile
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path

from oppie.models import RunId


class ArtifactType(Enum):
    ASK = 'ask'
    PLAN = 'plan'
    APPLY = 'apply'
    REPORT = 'report'
    CONTEXT = 'context'


# Map artifact types to their subdirectory names under artifacts/
_TYPE_DIRS: dict[ArtifactType, str] = {
    ArtifactType.ASK: 'ask',
    ArtifactType.PLAN: 'plans',
    ArtifactType.APPLY: 'applies',
    ArtifactType.REPORT: 'reports',
    ArtifactType.CONTEXT: 'context',
}


class ArtifactStore:
    """Manage artifact files under an instance home's artifacts/ directory."""

    def __init__(self, home: Path) -> None:
        self._artifacts_dir = home / 'artifacts'

    def save_artifact(
        self, artifact_type: ArtifactType, content: str, run_id: RunId
    ) -> Path:
        """Write a markdown artifact and return its path.

        Filename: {type}-{timestamp}-{run_id}.md
        Uses atomic write (temp file + rename) to prevent partial files.
        """
        subdir = self._artifacts_dir / _TYPE_DIRS[artifact_type]
        subdir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S')
        filename = f'{artifact_type.value}-{timestamp}-{run_id}.md'
        target = subdir / filename

        fd, tmp_path = tempfile.mkstemp(dir=subdir, suffix='.tmp')
        try:
            with open(fd, 'w') as f:
                f.write(content)
            Path(tmp_path).replace(target)
        except BaseException:
            Path(tmp_path).unlink(missing_ok=True)
            raise

        return target

    def list_artifacts(self, artifact_type: ArtifactType) -> list[Path]:
        """List artifact files for the given type, sorted by modification time (newest first).

        Returns paths to all files in the artifact type's subdirectory.
        """
        subdir = self._artifacts_dir / _TYPE_DIRS[artifact_type]
        if not subdir.exists():
            return []
        return sorted(subdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

    def read_artifact(self, path: Path) -> str:
        """Read and return the content of an artifact file."""
        if not path.exists():
            raise FileNotFoundError(f'Artifact not found: {path}')
        return path.read_text()
