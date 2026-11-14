"""Validate future Linear-linked Hermes session identities before collection.

This module selects metadata only. It does not access sessions, start work,
assign a repository, or authorize capture by itself. The cutoff must be fixed
by the operator-controlled rollout, not generated again on each poll.
"""
from datetime import datetime, timezone
import re
import uuid


def identifier(value):
    if type(value) is not str:
        raise ValueError('canonical UUID required')
    try:
        parsed = uuid.UUID(value)
    except ValueError as exc:
        raise ValueError('canonical UUID required') from exc
    if str(parsed) != value:
        raise ValueError('canonical UUID required')
    return value


def timestamp(value):
    if type(value) is not str or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z', value):
        raise ValueError('UTC timestamp required')
    try:
        return datetime.fromisoformat(value[:-1] + '+00:00').astimezone(timezone.utc)
    except ValueError as exc:
        raise ValueError('UTC timestamp required') from exc


def select(row, *, organization_id, cutoff):
    """Return an exact eligible session identity, or None for an older session.

    The caller must obtain rows from an authenticated, trusted registry and
    enforce the separately approved destination and bounded polling policy.
    """
    identifier(organization_id)
    start = timestamp(cutoff)
    if type(row) is not dict or set(row) != {
            'organization_id', 'agent_session_id', 'issue_id', 'hermes_session_id', 'created_at'}:
        raise ValueError('exact Linear session metadata required')
    org = identifier(row['organization_id'])
    session = identifier(row['agent_session_id'])
    issue = identifier(row['issue_id'])
    created = timestamp(row['created_at'])
    if org != organization_id:
        raise ValueError('session organization differs')
    if row['hermes_session_id'] != 'linear:' + org + ':' + session:
        raise ValueError('native session identity differs')
    if created <= start:
        return None
    return dict(organization_id=org, agent_session_id=session, issue_id=issue,
                hermes_session_id=row['hermes_session_id'], created_at=row['created_at'])


def select_page(page, *, organization_id, cutoff, after_time, after_id):
    """Check a bounded, strictly ordered page before any source is opened."""
    previous = (timestamp(after_time), identifier(after_id))
    if (type(page) is not dict or set(page) != {'contract', 'sessions'} or
            page['contract'] != 'hermes-future-session-page.v1' or
            type(page['sessions']) is not list or len(page['sessions']) > 4):
        raise ValueError('bounded future session page required')
    result = []
    for row in page['sessions']:
        checked = select(row, organization_id=organization_id, cutoff=cutoff)
        if checked is None:
            raise ValueError('future session page contains an older session')
        current = (timestamp(checked['created_at']), checked['agent_session_id'])
        if current <= previous:
            raise ValueError('future session cursor repeated or regressed')
        previous = current
        result.append(checked)
    return result
