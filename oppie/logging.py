import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

LOG_FORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'

_NOISY_THIRD_PARTY_LOGGERS = ('httpx', 'httpcore', 'urllib3')


def configure_logging(debug: bool = False, home: Path | None = None) -> None:
    """Configure root logger based on --debug flag and OPPIE_LOG_LEVEL env var.

    Precedence: OPPIE_LOG_LEVEL env var > --debug flag > default (WARNING).
    Invalid OPPIE_LOG_LEVEL values produce a warning and fall back to WARNING.
    Always writes to {home}/logs/oppie-{timestamp}.log when an initialized
    instance exists. Falls back to stderr otherwise. Noisy HTTP loggers
    (httpx, httpcore, urllib3) are always capped at WARNING, even with --debug.
    """
    env_level = os.environ.get('OPPIE_LOG_LEVEL')

    if env_level is not None:
        numeric = getattr(logging, env_level.upper(), None)
        if numeric is None or not isinstance(numeric, int):
            click.echo(
                f'Warning: invalid OPPIE_LOG_LEVEL={env_level!r}, '
                f'falling back to WARNING.',
                err=True,
            )
            level = logging.WARNING
        else:
            level = numeric
    elif debug:
        level = logging.DEBUG
    else:
        level = logging.WARNING

    handlers: list[logging.Handler] = []
    # Only write to file if home exists and has a logs/ directory (initialized instance).
    # This avoids creating directories before `oppie init` has run.
    if home is not None and (home / 'logs').is_dir():
        logs_dir = home / 'logs'
        timestamp = datetime.now(UTC).strftime('%Y-%m-%dT%H-%M-%S')
        log_path = logs_dir / f'oppie-{timestamp}.log'
        handlers.append(logging.FileHandler(log_path))
    else:
        handlers.append(logging.StreamHandler(sys.stderr))

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )

    for name in _NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
