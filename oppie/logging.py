import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import click

LOG_FORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'


def configure_logging(debug: bool = False, home: Path | None = None) -> None:
    """Configure root logger based on --debug flag and OPPIE_LOG_LEVEL env var.

    Precedence: OPPIE_LOG_LEVEL env var > --debug flag > default (INFO).
    Invalid OPPIE_LOG_LEVEL values produce a warning and fall back to INFO.
    Always writes to {home}/logs/oppie-{timestamp}.log when an initialized
    instance exists. Falls back to stderr otherwise.
    """
    env_level = os.environ.get('OPPIE_LOG_LEVEL')

    if env_level is not None:
        numeric = getattr(logging, env_level.upper(), None)
        if numeric is None or not isinstance(numeric, int):
            click.echo(
                f'Warning: invalid OPPIE_LOG_LEVEL={env_level!r}, '
                f'falling back to INFO.',
                err=True,
            )
            level = logging.INFO
        else:
            level = numeric
    elif debug:
        level = logging.DEBUG
    else:
        level = logging.INFO

    handlers: list[logging.Handler] = []
    # Only write to file if home exists and has a logs/ directory (initialized instance).
    # This avoids creating directories before `oppie init` has run.
    if home is not None and (home / 'logs').is_dir():
        logs_dir = home / 'logs'
        timestamp = datetime.now(UTC).strftime('%Y-%m-%dT%H-%M-%S')
        log_path = logs_dir / f'oppie-{timestamp}.log'
        handlers.append(logging.FileHandler(log_path))
    else:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )
