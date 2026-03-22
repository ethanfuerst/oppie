import json
import os
from dataclasses import dataclass
from pathlib import Path

from oppie import __version__
from oppie.config import InstanceType, OppieConfig, load_config

MARKER_FILENAME = '.oppie-marker'

INSTANCE_DIRS = (
    'config',
    'state',
    'state/snapshots',
    'tickets',
    'context',
    'artifacts',
    'artifacts/ask',
    'artifacts/plans',
    'artifacts/applies',
    'artifacts/reports',
    'artifacts/context',
    'logs',
)


@dataclass(slots=True)
class Marker:
    version: str
    instance_type: InstanceType

    def to_dict(self) -> dict:
        return {
            'version': self.version,
            'instance_type': self.instance_type.value,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Marker':
        return cls(
            version=data['version'],
            instance_type=InstanceType(data['instance_type']),
        )

    def write(self, path: Path) -> None:
        """Write marker as JSON to path."""
        path.write_text(json.dumps(self.to_dict(), indent=2) + '\n')

    @classmethod
    def read(cls, path: Path) -> 'Marker':
        """Read and parse a marker JSON file."""
        if not path.exists():
            raise FileNotFoundError(f'Marker file not found: {path}')
        try:
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            raise ValueError(f'Malformed marker file {path}: {e}') from e


class Instance:
    """Manages an oppie instance home directory."""

    def __init__(
        self,
        home: Path,
        marker: Marker,
        config: OppieConfig | None = None,
    ) -> None:
        self.home = home.resolve()
        self.marker = marker
        self.config = config

    @classmethod
    def create(cls, home: Path, instance_type: InstanceType) -> 'Instance':
        """Scaffold a new instance home directory with marker file.

        Does NOT write oppie.yaml or provider.yaml — that is the job of
        `oppie init` (ETH-364).
        """
        if home.exists():
            raise FileExistsError(f'Instance already exists at {home}')

        # Create all directories first
        home.mkdir(parents=True)
        for d in INSTANCE_DIRS:
            (home / d).mkdir(parents=True, exist_ok=True)

        # Write marker last — a partial init won't be discoverable
        marker = Marker(version=__version__, instance_type=instance_type)
        marker.write(home / MARKER_FILENAME)

        return cls(home=home, marker=marker, config=None)

    @classmethod
    def load(cls, home: Path) -> 'Instance':
        """Load an existing instance from its home directory."""
        if not home.is_dir():
            raise FileNotFoundError(f'Instance home not found: {home}')

        marker = Marker.read(home / MARKER_FILENAME)

        config = None
        config_dir = home / 'config'
        if (config_dir / 'oppie.yaml').exists():
            config = load_config(config_dir)

        return cls(home=home, marker=marker, config=config)

    @staticmethod
    def detect(home: Path | None = None) -> Path:
        """Resolve the instance home path.

        Priority: explicit home > OPPIE_HOME env var > CWD walk.
        Returns the resolved .oppie/ directory path.
        """
        if home is not None:
            resolved = home.resolve()
            if not (resolved / MARKER_FILENAME).exists():
                raise FileNotFoundError(
                    f'No valid instance at {resolved} (missing {MARKER_FILENAME})'
                )
            return resolved

        env_home = os.environ.get('OPPIE_HOME')
        if env_home:
            resolved = Path(env_home).resolve()
            if not (resolved / MARKER_FILENAME).exists():
                raise FileNotFoundError(
                    f'No valid instance at {resolved} (missing {MARKER_FILENAME})'
                )
            return resolved

        current = Path.cwd()
        while True:
            candidate = current / '.oppie'
            if (candidate / MARKER_FILENAME).exists():
                return candidate.resolve()
            parent = current.parent
            if parent == current:
                break
            current = parent

        raise FileNotFoundError(
            "No oppie instance found. Run 'oppie init' to create one."
        )
