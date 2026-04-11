import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckStatus:
    OK = 'ok'
    FAILED = 'failed'
    WARNING = 'warning'
    NA = 'n/a'


@dataclass(slots=True)
class CheckResult:
    name: str
    status: str
    message: str
    detail: str | None = None


def check_config(home: Path) -> CheckResult:
    """Check if config loads without errors."""
    from oppie.config import load_config

    try:
        load_config(home / 'config')
        return CheckResult('Config valid', CheckStatus.OK, 'ok')
    except Exception as e:
        return CheckResult('Config valid', CheckStatus.FAILED, str(e))


def check_state_cache(home: Path) -> CheckResult:
    """Check state directory is accessible."""
    state_dir = home / 'state'
    if not state_dir.is_dir():
        return CheckResult(
            'State cache', CheckStatus.FAILED, 'state/ directory missing'
        )
    if not os.access(state_dir, os.R_OK):
        return CheckResult('State cache', CheckStatus.FAILED, 'state/ not readable')
    return CheckResult('State cache', CheckStatus.OK, 'ok')


def check_tickets(home: Path) -> CheckResult:
    """Check if tickets are readable."""
    from oppie.models.ticket import Ticket

    tickets_dir = home / 'tickets'
    if not tickets_dir.exists():
        return CheckResult('Tickets readable', CheckStatus.OK, 'ok (0 tickets)')

    count = 0
    errors = []
    for path in sorted(tickets_dir.glob('*.json')):
        try:
            data = json.loads(path.read_text())
            Ticket.from_dict(data)
            count += 1
        except Exception as e:
            errors.append(f'{path.name}: {e}')

    if errors:
        return CheckResult(
            'Tickets readable',
            CheckStatus.FAILED,
            f'{len(errors)} corrupt ticket(s)',
            detail='\n'.join(errors),
        )
    return CheckResult('Tickets readable', CheckStatus.OK, f'ok ({count} tickets)')


def check_outbox(home: Path, provider: object | None) -> CheckResult:
    """Check outbox for ExternalProvider."""
    from oppie.providers.base import ExternalProvider

    if provider is None or not isinstance(provider, ExternalProvider):
        return CheckResult('Outbox', CheckStatus.NA, 'n/a (local provider)')

    outbox_path = home / 'state' / 'linear' / 'outbox.jsonl'
    if not outbox_path.exists():
        return CheckResult('Outbox', CheckStatus.OK, 'ok (0 pending)')

    line_count = sum(1 for line in outbox_path.read_text().splitlines() if line.strip())
    if line_count > 0:
        return CheckResult('Outbox', CheckStatus.WARNING, f'{line_count} pending')
    return CheckResult('Outbox', CheckStatus.OK, 'ok (0 pending)')


def check_artifacts(home: Path) -> CheckResult:
    """Check artifacts directory is writable."""
    artifacts_dir = home / 'artifacts'
    if not artifacts_dir.is_dir():
        return CheckResult('Artifacts', CheckStatus.FAILED, 'artifacts/ missing')

    subdirs = ['ask', 'plans', 'applies', 'reports', 'context']
    unwritable = [
        d
        for d in subdirs
        if (artifacts_dir / d).exists() and not os.access(artifacts_dir / d, os.W_OK)
    ]
    if unwritable:
        return CheckResult(
            'Artifacts',
            CheckStatus.FAILED,
            f'not writable: {", ".join(unwritable)}',
        )
    return CheckResult('Artifacts', CheckStatus.OK, 'ok')


def check_run_log(home: Path) -> CheckResult:
    """Parse run log, count valid/invalid lines."""
    log_path = home / 'logs' / 'runs.jsonl'
    if not log_path.exists():
        return CheckResult('Run log', CheckStatus.OK, 'ok (0 entries)')

    valid = 0
    malformed = 0
    for line in log_path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            json.loads(line)
            valid += 1
        except json.JSONDecodeError:
            malformed += 1

    if malformed > 0:
        return CheckResult(
            'Run log',
            CheckStatus.WARNING,
            f'{malformed} malformed entries',
            detail=f'{valid} valid, {malformed} malformed',
        )
    return CheckResult('Run log', CheckStatus.OK, f'ok ({valid} entries)')


def check_provider_connectivity(provider: object | None) -> CheckResult:
    """Test external provider connectivity with real API call."""
    from oppie.providers.base import ExternalProvider

    if provider is None:
        return CheckResult(
            'Provider connectivity', CheckStatus.FAILED, 'provider failed to initialize'
        )
    if not isinstance(provider, ExternalProvider):
        return CheckResult(
            'Provider connectivity', CheckStatus.NA, 'n/a (local provider)'
        )

    try:
        provider.test_connection()
        return CheckResult('Provider connectivity', CheckStatus.OK, 'ok')
    except Exception as e:
        return CheckResult('Provider connectivity', CheckStatus.FAILED, str(e))


def check_llm_connectivity(config: object | None) -> CheckResult:
    """Test LLM backend connectivity."""
    import asyncio

    from oppie.llm import LLMNotConfiguredError, create_llm_provider

    try:
        llm = create_llm_provider(config.llm if config else None)  # type: ignore[attr-defined]
    except LLMNotConfiguredError:
        return CheckResult('LLM connectivity', CheckStatus.NA, 'n/a (not configured)')

    try:

        async def _test() -> bool:
            async with llm:
                return await llm.test_connection()

        reachable = asyncio.run(_test())
        if reachable:
            return CheckResult('LLM connectivity', CheckStatus.OK, 'ok')
        return CheckResult('LLM connectivity', CheckStatus.FAILED, 'unreachable')
    except Exception as e:
        return CheckResult('LLM connectivity', CheckStatus.FAILED, str(e))


def check_extras() -> CheckResult:
    """Report installed extras."""
    from oppie.cli.extras import extras_available

    extras = extras_available()
    installed = [k for k, v in extras.items() if v]
    missing = [k for k, v in extras.items() if not v]

    parts = []
    if installed:
        parts.append(f'installed: {", ".join(installed)}')
    if missing:
        parts.append(f'missing: {", ".join(missing)}')
    return CheckResult('Installed extras', CheckStatus.OK, '; '.join(parts))


def check_missing_deps(config: object | None) -> CheckResult:
    """Cross-reference config with installed extras."""
    from oppie.cli.extras import extras_available
    from oppie.config import ProviderType

    extras = extras_available()
    warnings = []

    if (
        config
        and hasattr(config, 'provider')
        and config.provider.provider_type == ProviderType.LINEAR  # type: ignore[union-attr]
        and not extras['linear']
    ):
        warnings.append(
            'Linear provider configured but httpx not installed'
            ' (pip install oppie[linear])'
        )
    if config and hasattr(config, 'llm') and config.llm and not extras['llm']:  # type: ignore[union-attr]
        warnings.append(
            'LLM configured but httpx not installed (pip install oppie[llm])'
        )

    if warnings:
        return CheckResult(
            'Missing dependencies',
            CheckStatus.WARNING,
            '; '.join(warnings),
        )
    return CheckResult('Missing dependencies', CheckStatus.OK, 'ok')


def run_all_checks(
    home: Path, config: object | None, provider: object | None
) -> list[CheckResult]:
    """Run all health checks and return results."""
    return [
        check_config(home),
        check_state_cache(home),
        check_tickets(home),
        check_outbox(home, provider),
        check_artifacts(home),
        check_run_log(home),
        check_provider_connectivity(provider),
        check_llm_connectivity(config),
        check_extras(),
        check_missing_deps(config),
    ]
