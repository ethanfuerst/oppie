from __future__ import annotations

import fcntl
import json
import logging
import tempfile
from datetime import UTC, datetime
from enum import IntEnum, StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Any

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from oppie.config import resolve_api_key
from oppie.models.apply import OperationResult, OperationStatus
from oppie.models.capabilities import ProviderCapabilities
from oppie.models.operation import Operation
from oppie.models.sync import SyncResult
from oppie.models.ticket import Ticket, TicketMetadata, TicketSource
from oppie.providers.base import ExternalProvider, TicketProvider

if TYPE_CHECKING:
    from oppie.providers.linear.config import LinearProviderConfig

logger = logging.getLogger(__name__)


class LinearPriority(IntEnum):
    NONE = 0
    URGENT = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def to_label(cls, value: int) -> str:
        try:
            return cls(value).label
        except ValueError:
            return 'none'

    @classmethod
    def from_label(cls, label: str) -> LinearPriority:
        for member in cls:
            if member.label == label:
                return member
        raise ValueError(f'Unknown priority label: {label!r}')


class _ResolveStrategy(StrEnum):
    LOOKUP_STATE = auto()
    LOOKUP_MEMBER = auto()
    LOOKUP_LABELS = auto()
    PRIORITY = auto()
    PASSTHROUGH = auto()


class LinearTicketSchema(StrEnum):
    """Maps oppie Ticket fields to Linear GraphQL mutation input keys."""

    STATUS = 'status'
    PRIORITY = 'priority'
    OWNER = 'owner'
    LABELS = 'labels'
    ESTIMATE = 'estimate'

    @property
    def graphql_key(self) -> str:
        return _FIELD_TO_GRAPHQL[self]

    @property
    def resolve_strategy(self) -> _ResolveStrategy:
        return _FIELD_TO_STRATEGY[self]

    @classmethod
    def updatable_fields(cls) -> list[str]:
        return [f.value for f in cls]


_FIELD_TO_GRAPHQL: dict[LinearTicketSchema, str] = {
    LinearTicketSchema.STATUS: 'stateId',
    LinearTicketSchema.PRIORITY: 'priority',
    LinearTicketSchema.OWNER: 'assigneeId',
    LinearTicketSchema.LABELS: 'labelIds',
    LinearTicketSchema.ESTIMATE: 'estimate',
}

_FIELD_TO_STRATEGY: dict[LinearTicketSchema, _ResolveStrategy] = {
    LinearTicketSchema.STATUS: _ResolveStrategy.LOOKUP_STATE,
    LinearTicketSchema.PRIORITY: _ResolveStrategy.PRIORITY,
    LinearTicketSchema.OWNER: _ResolveStrategy.LOOKUP_MEMBER,
    LinearTicketSchema.LABELS: _ResolveStrategy.LOOKUP_LABELS,
    LinearTicketSchema.ESTIMATE: _ResolveStrategy.PASSTHROUGH,
}


_GRAPHQL_ENDPOINT = 'https://api.linear.app/graphql'

_ISSUES_QUERY = """
query Issues($teamId: String!, $after: String, $filter: IssueFilter) {
  team(id: $teamId) {
    issues(first: 50, after: $after, filter: $filter) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id identifier title description
        state { id name }
        priority
        assignee { id name }
        labels { nodes { id name } }
        project { id name }
        estimate
        createdAt updatedAt
      }
    }
  }
}
"""

_ISSUE_UPDATE_MUTATION = """
mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier updatedAt }
  }
}
"""

_WORKFLOW_STATES_QUERY = """
query WorkflowStates($teamId: String!) {
  team(id: $teamId) {
    states { nodes { id name } }
  }
}
"""

_TEAM_LABELS_QUERY = """
query TeamLabels($teamId: String!) {
  team(id: $teamId) {
    labels { nodes { id name } }
  }
}
"""

_TEAM_MEMBERS_QUERY = """
query TeamMembers($teamId: String!) {
  team(id: $teamId) {
    members { nodes { id name } }
  }
}
"""


class LinearAPIError(Exception):
    """Raised on Linear GraphQL API errors."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LinearAuthError(LinearAPIError):
    """Raised on 401 Unauthorized."""

    pass


class LinearRateLimitError(LinearAPIError):
    """Raised on 429 Too Many Requests."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class LinearProvider(ExternalProvider):
    """Linear external provider — syncs via GraphQL, delegates storage to a cache provider."""

    @classmethod
    def setup(
        cls,
        home: Path,
        cache: TicketProvider,
    ) -> LinearProvider:
        """Interactive setup for Linear provider during oppie init.

        Prompt for API key, test connectivity, select team/project scope,
        save config, and optionally run initial sync.
        Returns a configured LinearProvider ready for use.
        """
        # Deferred imports: setup() is only called during `oppie init`,
        # avoids pulling click/discovery into all provider usage
        import click

        from oppie.config import save_provider_credentials
        from oppie.providers.linear.discovery import (
            list_projects,
            list_teams,
            test_api_key,
        )

        # Prompt for API key
        while True:
            api_key = click.prompt('Linear API key', hide_input=True)
            click.echo('Testing API key...')
            if test_api_key(api_key):
                click.echo('API key valid.')
                break
            click.echo('Error: Invalid API key (HTTP 401). Try again.')

        # List teams
        teams = list_teams(api_key)
        if not teams:
            raise click.ClickException('No teams found in workspace.')

        click.echo('\nSelect team:')
        for i, team in enumerate(teams, 1):
            click.echo(f'  {i}. {team["name"]} ({team["key"]})')
        choice = click.prompt('Team', type=click.IntRange(1, len(teams)))
        selected_team = teams[choice - 1]

        # Optionally select project
        projects = list_projects(api_key, selected_team['id'])
        project_id = None
        if projects:
            click.echo('\nSelect project (optional):')
            click.echo('  0. All projects')
            for i, proj in enumerate(projects, 1):
                click.echo(f'  {i}. {proj["name"]}')
            proj_choice = click.prompt(
                'Project',
                type=click.IntRange(0, len(projects)),
                default=0,
            )
            if proj_choice > 0:
                project_id = projects[proj_choice - 1]['id']

        # Deferred import: avoids circular dependency at module level
        from oppie.providers.linear.config import LinearProviderConfig

        config = LinearProviderConfig(
            type='linear',  # type: ignore[arg-type]
            team_id=selected_team['id'],
            project_id=project_id,
            api_key=api_key,
        )

        # Save credentials
        config_dir = home / 'config'
        save_provider_credentials(config_dir, {'api_key': api_key})

        return cls(home=home, cache=cache, config=config)

    def __init__(
        self,
        home: Path,
        cache: TicketProvider,
        config: LinearProviderConfig,
    ) -> None:
        if httpx is None:
            raise ImportError(
                'Linear provider requires the linear extra. '
                'Install with: pip install oppie[linear]'
            )
        self._home = home
        self._cache = cache
        self._config = config
        api_key = resolve_api_key(config)
        self._client = httpx.Client(
            base_url=_GRAPHQL_ENDPOINT,
            headers={'Authorization': api_key},
            timeout=30.0,
        )
        self._checkpoint_path = home / 'state' / 'linear' / 'sync-checkpoint.json'
        self._outbox_path = home / 'state' / 'linear' / 'outbox.jsonl'
        self._outbox_lock_path = home / 'state' / 'linear' / 'outbox.lock'
        # Lookup caches (populated during sync)
        self._state_map: dict[str, str] = {}  # state name -> id
        self._label_map: dict[str, str] = {}  # label name -> id
        self._member_map: dict[str, str] = {}  # member name -> id

    @property
    def home(self) -> Path:
        return self._home

    @property
    def version(self) -> str:
        return 'v1'

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_sync=True,
            supports_incremental_sync=True,
            supports_write=True,
            supports_create=False,
            supports_projects=True,
            supports_estimates=True,
            supports_cycles=True,
            supports_custom_fields=False,
            supported_field_updates=LinearTicketSchema.updatable_fields(),
        )

    def read_ticket(self, ticket_id: str) -> Ticket | None:
        return self._cache.read_ticket(ticket_id)

    def update_ticket(self, ticket_id: str, updates: dict) -> Ticket:
        result = self._cache.update_ticket(ticket_id, updates)
        # Queue mutation for outbox flush
        ticket = self._cache.read_ticket(ticket_id)
        if ticket and ticket.metadata.source == TicketSource.LINEAR:
            for field_name, value in updates.items():
                op = Operation(
                    ticket_id=ticket_id,
                    field=field_name,
                    before_value=getattr(ticket, field_name),
                    after_value=value,
                    rationale='Queued for Linear sync',
                )
                self._append_outbox(op)
        return result

    def list_tickets(self) -> list[Ticket]:
        return self._cache.list_tickets()

    def _build_sync_filter(
        self,
        checkpoint: str | None,
    ) -> dict | None:
        """Build a GraphQL IssueFilter from config scope + checkpoint."""
        parts: dict[str, Any] = {}

        if checkpoint:
            parts['updatedAt'] = {'gte': checkpoint}
        if self._config.project_id:
            parts['project'] = {'id': {'eq': self._config.project_id}}
        if self._config.sync_statuses:
            parts['state'] = {'name': {'in': self._config.sync_statuses}}
        if self._config.sync_labels:
            parts['labels'] = {'name': {'in': self._config.sync_labels}}

        return parts or None

    def sync(self, checkpoint: str | None = None) -> SyncResult:
        """Fetch issues from Linear, upsert into cache, persist checkpoint."""
        if checkpoint is None:
            checkpoint = self._load_checkpoint()

        self._refresh_lookup_caches()

        gql_filter = self._build_sync_filter(checkpoint)

        tickets_upserted = 0
        errors: list[str] = []
        latest_updated_at: str | None = checkpoint
        cursor: str | None = None
        page_num = 0

        logger.debug(
            'Starting sync for team %s (checkpoint=%s)',
            self._config.team_id,
            checkpoint,
        )

        while True:
            page_num += 1
            variables: dict[str, Any] = {'teamId': self._config.team_id}
            if cursor:
                variables['after'] = cursor
            if gql_filter:
                variables['filter'] = gql_filter

            logger.debug('Fetching page %d (cursor=%s)', page_num, cursor)

            try:
                data = self._graphql(_ISSUES_QUERY, variables)
            except LinearAPIError as e:
                logger.debug('API error on page %d: %s', page_num, e)
                errors.append(str(e))
                break

            team = data.get('team')
            if not team:
                errors.append('Team not found')
                break

            issues = team['issues']
            page_count = len(issues['nodes'])
            logger.debug('Page %d returned %d issues', page_num, page_count)

            for node in issues['nodes']:
                try:
                    ticket = self._map_issue_to_ticket(node)
                    self._cache.upsert_ticket(ticket)
                    tickets_upserted += 1
                    if (
                        latest_updated_at is None
                        or node['updatedAt'] > latest_updated_at
                    ):
                        latest_updated_at = node['updatedAt']
                except Exception as e:
                    logger.debug(
                        'Failed to map issue %s: %s', node.get('identifier', '?'), e
                    )
                    errors.append(f'Failed to sync {node.get("identifier", "?")}: {e}')

            page_info = issues['pageInfo']
            if page_info['hasNextPage']:
                cursor = page_info['endCursor']
            else:
                break

        logger.debug(
            'Sync complete: %d upserted, %d errors, %d pages',
            tickets_upserted,
            len(errors),
            page_num,
        )

        if latest_updated_at:
            self._save_checkpoint(latest_updated_at)

        return SyncResult(
            tickets_upserted=tickets_upserted,
            checkpoint=latest_updated_at,
            errors=errors,
        )

    def apply(self, operations: list[Operation]) -> list[OperationResult]:
        """Send mutations to Linear. Called during outbox flush."""
        logger.debug('Applying %d operations', len(operations))
        if not self._state_map:
            self._refresh_lookup_caches()

        results: list[OperationResult] = []
        for op in operations:
            try:
                ticket = self._cache.read_ticket(op.ticket_id)
                if ticket is None or ticket.metadata.external_id is None:
                    results.append(
                        OperationResult(
                            operation=op,
                            status=OperationStatus.FAILED,
                            error=f'Ticket {op.ticket_id} not found or missing external_id',
                        )
                    )
                    continue

                mutation_input = self._build_mutation_input(op)
                variables = {
                    'id': ticket.metadata.external_id,
                    'input': mutation_input,
                }
                data = self._graphql(_ISSUE_UPDATE_MUTATION, variables)
                success = data.get('issueUpdate', {}).get('success', False)

                if success:
                    result = OperationResult(
                        operation=op,
                        status=OperationStatus.OK,
                    )
                else:
                    result = OperationResult(
                        operation=op,
                        status=OperationStatus.FAILED,
                        error='Linear mutation returned success=false',
                    )
                results.append(result)
                logger.debug(
                    'Operation %s.%s: %s', op.ticket_id, op.field, result.status.value
                )
            except LinearAPIError as e:
                result = OperationResult(
                    operation=op,
                    status=OperationStatus.FAILED,
                    error=str(e),
                )
                results.append(result)
                logger.debug(
                    'Operation %s.%s: %s', op.ticket_id, op.field, result.status.value
                )
        return results

    def flush_outbox(self) -> list[OperationResult]:
        """Read outbox, apply all queued operations, clear successful entries."""
        operations = self._read_outbox()
        if not operations:
            return []
        logger.debug('Flushing outbox: %d operations', len(operations))
        results = self.apply(operations)
        # Remove successful operations from outbox
        failed_ops = [r.operation for r in results if r.status != OperationStatus.OK]
        self._write_outbox(failed_ops)
        logger.debug('Outbox flush complete: %d failed', len(failed_ops))
        return results

    def _graphql(self, query: str, variables: dict | None = None) -> dict:
        """Execute a GraphQL request. Raise on HTTP or GraphQL errors."""
        payload: dict[str, Any] = {'query': query}
        if variables:
            payload['variables'] = variables

        logger.debug('GraphQL request (%d bytes)', len(json.dumps(payload)))
        resp = self._client.post('', json=payload)
        logger.debug('GraphQL response: %d status', resp.status_code)

        if resp.status_code == 401:
            raise LinearAuthError('Authentication failed. Check your Linear API key.')
        if resp.status_code == 429:
            retry_after = resp.headers.get('retry-after')
            raise LinearRateLimitError(
                'Rate limited by Linear API.',
                retry_after=float(retry_after) if retry_after else None,
            )
        resp.raise_for_status()

        body = resp.json()
        if 'errors' in body:
            msgs = [e.get('message', str(e)) for e in body['errors']]
            raise LinearAPIError(f'GraphQL errors: {"; ".join(msgs)}')

        return dict(body.get('data', {}))

    def _map_issue_to_ticket(self, node: dict) -> Ticket:
        """Map a Linear GraphQL issue node to an oppie Ticket."""
        assignee = node.get('assignee')
        project = node.get('project')
        labels_nodes = (node.get('labels') or {}).get('nodes', [])
        state = node.get('state') or {}
        priority_int = node.get('priority', 0)

        return Ticket(
            id=node['identifier'],
            title=node.get('title', ''),
            status=state.get('name', 'unknown'),
            priority=LinearPriority.to_label(priority_int),
            owner=assignee.get('name') if assignee else None,
            labels=[lbl['name'] for lbl in labels_nodes],
            created_at=node['createdAt'],
            updated_at=node['updatedAt'],
            project=project.get('name') if project else None,
            description=node.get('description') or '',
            metadata=TicketMetadata(
                source=TicketSource.LINEAR,
                external_id=node['id'],
                synced_at=datetime.now(UTC).isoformat(),
            ),
            estimate=node.get('estimate'),
        )

    def _build_mutation_input(self, op: Operation) -> dict:
        """Map an oppie Operation to a Linear IssueUpdateInput dict."""
        try:
            schema = LinearTicketSchema(op.field)
        except ValueError:
            raise LinearAPIError(
                f'Unsupported field for mutation: {op.field!r}'
            ) from None

        key = schema.graphql_key
        strategy = schema.resolve_strategy

        if strategy == _ResolveStrategy.PASSTHROUGH:
            return {key: op.after_value}

        if strategy == _ResolveStrategy.PRIORITY:
            try:
                linear_priority = LinearPriority.from_label(op.after_value)
            except ValueError as err:
                raise LinearAPIError(
                    f'Unknown priority {op.after_value!r}. '
                    f'Known: {[m.label for m in LinearPriority]}'
                ) from err
            return {key: int(linear_priority)}

        if strategy == _ResolveStrategy.LOOKUP_STATE:
            resolved = self._state_map.get(op.after_value)
            if not resolved:
                raise LinearAPIError(
                    f'Unknown state {op.after_value!r}. '
                    f'Known: {list(self._state_map.keys())}'
                )
            return {key: resolved}

        if strategy == _ResolveStrategy.LOOKUP_MEMBER:
            if op.after_value is None:
                return {key: None}
            resolved = self._member_map.get(op.after_value)
            if not resolved:
                raise LinearAPIError(
                    f'Unknown member {op.after_value!r}. '
                    f'Known: {list(self._member_map.keys())}'
                )
            return {key: resolved}

        if strategy == _ResolveStrategy.LOOKUP_LABELS:
            label_ids = []
            for name in op.after_value or []:
                lid = self._label_map.get(name)
                if not lid:
                    raise LinearAPIError(
                        f'Unknown label {name!r}. Known: {list(self._label_map.keys())}'
                    )
                label_ids.append(lid)
            return {key: label_ids}

        raise LinearAPIError(
            f'No resolve strategy for field: {op.field!r}'
        )  # pragma: no cover

    def _refresh_lookup_caches(self) -> None:
        """Fetch workflow states, labels, and members from Linear for ID resolution."""
        team_id = self._config.team_id
        lookups: list[tuple[str, str, dict[str, str]]] = [
            (_WORKFLOW_STATES_QUERY, 'states', self._state_map),
            (_TEAM_LABELS_QUERY, 'labels', self._label_map),
            (_TEAM_MEMBERS_QUERY, 'members', self._member_map),
        ]
        for query, key, cache in lookups:
            try:
                data = self._graphql(query, {'teamId': team_id})
                nodes = data.get('team', {}).get(key, {}).get('nodes', [])
                cache.clear()
                cache.update({n['name']: n['id'] for n in nodes})
            except LinearAPIError:
                pass
        logger.debug(
            'Refreshed lookup caches: %d states, %d labels, %d members',
            len(self._state_map),
            len(self._label_map),
            len(self._member_map),
        )

    def _load_checkpoint(self) -> str | None:
        if not self._checkpoint_path.exists():
            return None
        data = json.loads(self._checkpoint_path.read_text())
        checkpoint: str | None = data.get('checkpoint')
        logger.debug('Loaded checkpoint: %s', checkpoint)
        return checkpoint

    def _save_checkpoint(self, checkpoint: str) -> None:
        self._checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._checkpoint_path.parent,
            suffix='.tmp',
        )
        try:
            with open(fd, 'w') as f:
                json.dump({'checkpoint': checkpoint}, f)
            Path(tmp).replace(self._checkpoint_path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        logger.debug('Saved checkpoint: %s', checkpoint)

    def _append_outbox(self, op: Operation) -> None:
        self._outbox_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._outbox_lock_path, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with open(self._outbox_path, 'a') as f:
                    f.write(json.dumps(op.to_dict(), separators=(',', ':')) + '\n')
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
        logger.debug('Appended operation to outbox: %s.%s', op.ticket_id, op.field)

    def _read_outbox(self) -> list[Operation]:
        if not self._outbox_path.exists():
            return []
        with open(self._outbox_lock_path, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_SH)
            try:
                ops = []
                for line in self._outbox_path.read_text().splitlines():
                    if line.strip():
                        ops.append(Operation.from_dict(json.loads(line)))
                logger.debug('Read %d operations from outbox', len(ops))
                return ops
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _write_outbox(self, operations: list[Operation]) -> None:
        """Rewrite outbox with only the given operations (atomic + locked)."""
        with open(self._outbox_lock_path, 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if not operations:
                    self._outbox_path.unlink(missing_ok=True)
                    return
                fd, tmp = tempfile.mkstemp(
                    dir=self._outbox_path.parent,
                    suffix='.tmp',
                )
                try:
                    with open(fd, 'w') as f:
                        for op in operations:
                            f.write(
                                json.dumps(op.to_dict(), separators=(',', ':')) + '\n'
                            )
                    Path(tmp).replace(self._outbox_path)
                except BaseException:
                    Path(tmp).unlink(missing_ok=True)
                    raise
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> LinearProvider:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
