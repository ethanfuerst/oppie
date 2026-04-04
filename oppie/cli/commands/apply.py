import json
import logging
import time

import click

from oppie.artifacts import ArtifactStore, ArtifactType
from oppie.cli.console import console, error, info, setup_provider, success, warn
from oppie.models.apply import ApplyResult, OperationStatus
from oppie.models.drift import DriftResolution, DriftResult
from oppie.plan import PreApplyCheck, check_apply, execute_apply
from oppie.run_log import generate_run_id
from oppie.session import Session

logger = logging.getLogger(__name__)


@click.command()
@click.argument('plan_id', required=False, default=None)
@click.option(
    '--force',
    is_flag=True,
    default=False,
    help='Overwrite drifted values without prompting.',
)
@click.pass_context
def apply(ctx: click.Context, plan_id: str | None, force: bool) -> None:
    """Apply a plan's operations to tickets."""
    home = ctx.obj['resolved_home']
    no_sync = ctx.obj.get('no_sync', False)

    # Resolve plan_id from session if not provided
    if plan_id is None:
        session = Session.load_latest(home)
        plan_id = session.get_active_plan() if session else None
        if plan_id is None:
            error('No plan specified and no active plan in session.')
            console.print('Provide a plan ID: [bold]oppie apply <plan_id>[/bold]')
            raise SystemExit(1)

    provider, sync_result = setup_provider(home, no_sync=no_sync)

    # Phase 1: Pre-apply checks
    info(f'Loading plan {plan_id}...')
    try:
        check = check_apply(provider, plan_id)
    except FileNotFoundError:
        error(f'Plan not found: {plan_id}')
        raise SystemExit(1) from None

    # Handle error states
    if not check.integrity_ok:
        _handle_integrity_failure(check, plan_id)

    if check.already_applied:
        _handle_already_applied(plan_id, home)

    if check.capability_errors:
        _handle_capability_errors(check)

    if check.drift.deleted_tickets:
        _handle_deleted_tickets(check, plan_id)

    # Handle drift
    resolutions = None
    if check.drift.has_any:
        _display_informational_drift(check.drift)

    if check.drift.has_critical:
        if force:
            _display_force_drift(check.drift)
        else:
            resolutions = _resolve_drift_interactive(check)

    # Display operations and confirm
    _display_operations(check, resolutions)

    if not click.confirm('Apply this plan?', default=False):
        console.print('Apply cancelled.')
        raise SystemExit(0)

    # Phase 2: Execute
    info('Applying...')
    start_time = time.monotonic()
    result = execute_apply(provider, plan_id, force=force, resolutions=resolutions)
    apply_duration = time.monotonic() - start_time

    # Write drift artifact if resolutions were made
    if resolutions:
        _write_drift_artifact(home, plan_id, check.drift, resolutions)

    # Display results
    _display_results(result)

    # Stats line
    _display_stats(
        sync_result.duration if sync_result.synced else None, apply_duration, result
    )

    # Update session
    session = Session.load_latest(home) or Session.create(home)
    session.set_active_plan(plan_id)


def _handle_integrity_failure(check: PreApplyCheck, plan_id: str) -> None:
    """Display integrity failure error and exit."""
    error('Verifying plan integrity... FAILED')
    console.print()
    console.print('Plan file has been modified since creation.')
    recomputed = check.plan.__class__.compute_id(check.plan.operations)
    console.print(f'  Expected hash: {check.plan.plan_id}')
    console.print(f'  Actual hash:   {recomputed}')
    console.print()
    console.print('Plans are immutable. If you need changes, use:')
    console.print(f'  [bold]oppie amend {plan_id}[/bold]')
    raise SystemExit(1)


def _handle_already_applied(plan_id: str, home) -> None:
    """Display already-applied error and exit."""
    error(f'Plan {plan_id} was already applied.')

    # Try to find the apply artifact via ArtifactStore
    store = ArtifactStore(home)
    for path in store.list_artifacts(ArtifactType.APPLY):
        content = store.read_artifact(path)
        if plan_id in content:
            data = json.loads(content)
            console.print(f'  Apply ID: {data.get("apply_id", "unknown")}')
            console.print(f'  Artifact: [dim]{path}[/dim]')
            break

    raise SystemExit(1)


def _handle_capability_errors(check: PreApplyCheck) -> None:
    """Display capability errors and exit."""
    error('Provider does not support some planned operations:')
    for err in check.capability_errors:
        console.print(f'  {err}')
    console.print()
    console.print('Amend the plan to remove unsupported operations.')
    raise SystemExit(1)


def _handle_deleted_tickets(check: PreApplyCheck, plan_id: str) -> None:
    """Display deleted ticket error and exit."""
    error('Drift detected \u2014 cannot resolve.')
    console.print()
    for tid in check.drift.deleted_tickets:
        console.print(f'  {tid}  Ticket no longer exists (deleted or archived)')
    console.print()
    console.print('Cannot apply operations to deleted tickets.')
    console.print('Recommended: re-plan with current state.')
    console.print(f'  [bold]oppie amend {plan_id}[/bold]')
    raise SystemExit(1)


def _display_informational_drift(drift: DriftResult) -> None:
    """Display informational (non-blocking) drift warnings."""
    if not drift.informational_drifts:
        return
    console.print()
    warn('Informational drift detected (does not affect planned changes):')
    console.print()
    for d in drift.informational_drifts:
        line = f'  {d.ticket_id}  {d.field}: {d.expected_value} -> {d.current_value}'
        if d.updated_at:
            line += f' ({d.updated_at})'
        console.print(line)
    console.print()
    console.print("These changes don't conflict with planned operations.")
    console.print()


def _display_force_drift(drift: DriftResult) -> None:
    """Display critical drift summary in force mode."""
    console.print()
    warn(
        f'Critical drift detected on {len(drift.critical_drifts)} operation(s) '
        f'(--force: overwriting).'
    )
    console.print()
    for d in drift.critical_drifts:
        console.print(
            f'  {d.ticket_id}  {d.field}: '
            f'{d.current_value} (current) -> {d.expected_value} (plan)'
        )
    console.print()


def _resolve_drift_interactive(
    check: PreApplyCheck,
) -> dict[tuple[str, str], DriftResolution]:
    """Prompt user for drift resolution on each critical drift.

    When user picks (c) SKIP_OPERATION, expand to all operations for that ticket.
    """
    resolutions: dict[tuple[str, str], DriftResolution] = {}
    skipped_tickets: set[str] = set()

    # Collect all operations per ticket for SKIP_OPERATION expansion
    ops_by_ticket: dict[str, list[str]] = {}
    for op in check.plan.operations:
        ops_by_ticket.setdefault(op.ticket_id, []).append(op.field)

    console.print()
    error(
        f'Critical drift detected on {len(check.drift.critical_drifts)} operation(s):'
    )

    for drift in check.drift.critical_drifts:
        if drift.ticket_id in skipped_tickets:
            # Already skipped this ticket via choice (c) on a previous drift
            resolutions[(drift.ticket_id, drift.field)] = DriftResolution.SKIP_OPERATION
            continue

        console.print()
        console.print(f'  {drift.ticket_id}  {drift.field}')
        console.print(f'           Plan expected: {drift.expected_value}')
        console.print(f'           Current value: {drift.current_value}')
        if drift.updated_at:
            console.print(f'           Changed at: {drift.updated_at}')
        if drift.updated_by:
            console.print(f'           Changed by: {drift.updated_by}')

        # Find the plan's after_value for this operation
        after_value = None
        for op in check.plan.operations:
            if op.ticket_id == drift.ticket_id and op.field == drift.field:
                after_value = op.after_value
                break

        console.print()
        console.print('  Resolution:')
        console.print(f'    a) Keep plan value (set to {after_value})')
        console.print(
            f'    b) Keep current value ({drift.current_value}), skip this change'
        )
        console.print(f'    c) Skip entire operation for {drift.ticket_id}')
        console.print()

        choice = click.prompt(
            '  Choice', type=click.Choice(['a', 'b', 'c'], case_sensitive=False)
        )

        if choice == 'a':
            resolutions[(drift.ticket_id, drift.field)] = (
                DriftResolution.KEEP_PLAN_VALUE
            )
        elif choice == 'b':
            resolutions[(drift.ticket_id, drift.field)] = (
                DriftResolution.KEEP_CURRENT_VALUE
            )
        elif choice == 'c':
            skipped_tickets.add(drift.ticket_id)
            # Expand to all operations for this ticket
            for field_name in ops_by_ticket.get(drift.ticket_id, []):
                resolutions[(drift.ticket_id, field_name)] = (
                    DriftResolution.SKIP_OPERATION
                )

    # Summary
    overwrite_count = sum(
        1 for r in resolutions.values() if r == DriftResolution.KEEP_PLAN_VALUE
    )
    skip_count = sum(
        1 for r in resolutions.values() if r != DriftResolution.KEEP_PLAN_VALUE
    )
    console.print()
    console.print(
        f'Resolved {len(check.drift.critical_drifts)} drift conflict(s) '
        f'({overwrite_count} overwrite, {skip_count} skipped).'
    )

    return resolutions


def _display_operations(
    check: PreApplyCheck,
    resolutions: dict[tuple[str, str], DriftResolution] | None,
) -> None:
    """Display the operations that will be applied."""
    ops = check.plan.operations
    # Count effective operations (not skipped by resolution)
    skipped_keys: set[tuple[str, str]] = set()
    if resolutions:
        skipped_keys = {
            k
            for k, v in resolutions.items()
            if v in (DriftResolution.KEEP_CURRENT_VALUE, DriftResolution.SKIP_OPERATION)
        }

    effective_count = sum(
        1 for op in ops if (op.ticket_id, op.field) not in skipped_keys
    )

    console.print()
    console.print(f'Operations to apply ({effective_count}):')
    console.print()
    for i, op in enumerate(ops, 1):
        key = (op.ticket_id, op.field)
        skip_marker = ' [dim](skipped)[/dim]' if key in skipped_keys else ''
        console.print(
            f'  {i}. {op.ticket_id}  {op.field}: '
            f'{op.before_value} -> {op.after_value}{skip_marker}'
        )
    console.print()


def _display_results(result: ApplyResult) -> None:
    """Display per-operation results after apply execution."""
    total = len(result.results)
    fail_count = sum(1 for r in result.results if r.status == OperationStatus.FAILED)
    ok_count = sum(1 for r in result.results if r.status == OperationStatus.OK)

    console.print()
    for i, r in enumerate(result.results, 1):
        op = r.operation
        if r.status == OperationStatus.OK:
            console.print(
                f'  {i}/{total}  {op.ticket_id}  {op.field} updated'
                f'         [green]ok[/green]'
            )
        elif r.status == OperationStatus.FAILED:
            console.print(
                f'  {i}/{total}  {op.ticket_id}  {op.field} updated'
                f'         [red]FAILED[/red]'
            )
            console.print(f'       Error: {r.error}')
        elif r.status == OperationStatus.SKIPPED:
            if r.error and 'drift' in r.error.lower():
                console.print(
                    f'  {i}/{total}  {op.ticket_id}  {op.field}'
                    f'                  [dim]skipped (drift)[/dim]'
                )
            else:
                console.print(
                    f'  {i}/{total}  {op.ticket_id}  {op.field}'
                    f'                  [dim]skipped[/dim]'
                )
    console.print()

    if fail_count > 0:
        warn(f'Apply partially failed. {ok_count} of {total} operations succeeded.')
        console.print()
        console.print('Applied operations cannot be automatically rolled back.')
        console.print('Review the apply artifact for details on what was applied.')
    else:
        success('All operations applied successfully.')

    console.print()
    console.print(f'Apply ID: {result.apply_id}')


def _display_stats(
    sync_duration: float | None,
    apply_duration: float,
    result: ApplyResult,
) -> None:
    """Print the stats line."""
    ok_count = sum(1 for r in result.results if r.status == OperationStatus.OK)
    total = len(result.results)
    skip_count = sum(1 for r in result.results if r.status == OperationStatus.SKIPPED)
    fail_count = sum(1 for r in result.results if r.status == OperationStatus.FAILED)

    parts = []
    if sync_duration is not None:
        parts.append(f'sync {sync_duration:.1f}s')
    parts.append(f'apply {apply_duration:.1f}s')
    parts.append(f'{ok_count}/{total} ops')

    suffix_parts = []
    if skip_count > 0:
        suffix_parts.append(f'{skip_count} skipped')
    if fail_count > 0:
        suffix_parts.append(f'{fail_count} failed')
    if suffix_parts:
        parts[-1] += f' ({", ".join(suffix_parts)})'

    console.print(f'[dim]* {" \u00b7 ".join(parts)}[/dim]')


def _write_drift_artifact(
    home,
    plan_id: str,
    drift: DriftResult,
    resolutions: dict[tuple[str, str], DriftResolution],
) -> None:
    """Write drift resolution report via ArtifactStore."""
    content = {
        'type': 'drift_report',
        'plan_id': plan_id,
        'drift': drift.to_dict(),
        'resolutions': {
            f'{tid}:{field}': res.value for (tid, field), res in resolutions.items()
        },
    }

    store = ArtifactStore(home)
    run_id = generate_run_id()
    path = store.save_artifact(
        ArtifactType.APPLY, json.dumps(content, indent=2), run_id
    )
    console.print(f'Drift report: [dim]{path}[/dim]')
