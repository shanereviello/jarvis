"""Policy tests use supplied test UIDs; not cross-UID host acceptance."""
import copy
import os
import pytest
from test_engineering_history_local import module, request, note, document, WORK

m = module('access'); storage = module('store')


def policy():
    return {'contract': 'engineering-history-access.v1', 'principals': [
        {'uid': 2001, 'private_read': ['example'], 'write': ['example']},
        {'uid': 2002, 'private_read': ['other'], 'write': ['other']},
        {'uid': 2003, 'private_read': ['example'], 'write': []},
        {'uid': 2004, 'private_read': ['example'], 'write': ['example']}]}


@pytest.fixture
def access(tmp_path):
    root = tmp_path / 'store'; root.mkdir(mode=0o700)
    return m.Access(storage.Store(root, create=True), policy())


def submit(access, r=None, uid=2001):
    return access.dispatch(uid, {'method': 'submit', 'request': r or request()})


def history(access, uid=2001, repo='example', offset=0, limit=100):
    return access.dispatch(uid, dict(method='history', repository_id=repo, offset=offset, limit=limit))


@pytest.mark.parametrize('uid', [0, 996, 997, 2005, True, '2001', None, 2**64])
def test_unauthenticated_or_worker_denied(access, uid):
    with pytest.raises(ValueError): submit(access, uid=uid)
    assert access.store.history()['records'] == []


def test_service_receipt_and_replay_after_restart(access):
    first = submit(access)
    receipt = first['receipt']
    assert receipt['contract'] == 'engineering-history-receipt.v2'
    assert receipt['peer_uid'] == 2001 and receipt['writer_uid'] == os.getuid()
    assert receipt['transport'] == 'authenticated_local_service'
    assert receipt['provenance'] == 'agent_reported' and receipt['authority_granted'] is False
    reopened = m.Access(storage.Store(access.store.root), policy())
    assert submit(reopened) == {'inserted': False, 'receipt': receipt}


def test_peer_and_local_dedupe_namespaces_are_distinct(access):
    head = submit(access)['receipt']['work_revision_sha256']
    n = note(head)
    a = submit(access, n)['receipt']
    b = submit(access, n, uid=2004)['receipt']
    local = access.store.submit(n)['receipt']
    assert len({a['receipt_id'], b['receipt_id'], local['receipt_id']}) == 3
    assert access.store.submit(n)['receipt'] == local
    assert submit(access, n)['receipt'] == a


def test_repository_filter_before_pagination_and_no_cross_repo_reads(access):
    submit(access)
    r = request(); r['body']['work_item_id'] = 'wrk_' + '3'*32; r['body']['repository_id'] = 'other'
    submit(access, r, uid=2002)
    head = history(access)['records'][0]['receipt']['work_revision_sha256']
    submit(access, note(head))
    page = history(access, limit=1)
    assert page['has_more'] and page['next_offset'] == 1
    page = history(access, offset=1, limit=1)
    assert len(page['records']) == 1 and not page['has_more']
    assert len(history(access, 2002, 'other')['records']) == 1
    with pytest.raises(ValueError): history(access, 2002)
    with pytest.raises(ValueError): submit(access, note(head), uid=2002)
    with pytest.raises(ValueError): submit(access, uid=2003)


def test_cannot_move_work_into_an_authorized_repository(access):
    head = submit(access)['receipt']['work_revision_sha256']
    r = request('work.revise', 'move', head); r['body'].update(revision=2, repository_id='other')
    with pytest.raises(ValueError): submit(access, r, uid=2002)
    assert len(access.store.history()['records']) == 1


def test_private_document_read_and_indistinguishable_missing(access):
    head = submit(access)['receipt']['work_revision_sha256']; r = document(head)
    receipt = submit(access, r)['receipt']
    msg = dict(method='document', document_id=r['body']['document_id'], version=None)
    result = access.dispatch(2003, msg)
    assert result['manifest'] == receipt['document_manifest']
    assert result['markdown'].encode() == access.store.document(r['body']['document_id'])[0]
    with pytest.raises(ValueError, match='^document unavailable$'): access.dispatch(2002, msg)
    msg['document_id'] = 'doc_' + '9'*32
    with pytest.raises(ValueError, match='^document unavailable$'): access.dispatch(2002, msg)


@pytest.mark.parametrize('method', ['execute', 'merge', 'deploy', 'publish', 'outbox', 'status', 'shell'])
def test_no_action_or_export_routes(access, method):
    with pytest.raises(ValueError): access.dispatch(2001, {'method': method})


def test_actor_claim_cannot_override_peer_or_grant(access):
    r = request(); r['source']['kind'] = 'human_reported'
    receipt = submit(access, r)['receipt']
    assert receipt['peer_uid'] == 2001 and receipt['provenance'] == 'human_reported'
    assert receipt['authority_granted'] is False
    with pytest.raises(ValueError): access.dispatch(2002, {'method':'submit', 'request':r, 'peer_uid':2001})
    r['source']['kind'] = 'observed'
    with pytest.raises(Exception): submit(access, r)


@pytest.mark.parametrize('change', ['root', 'worker', 'duplicate', 'wildcard', 'write_without_read', 'extra'])
def test_policy_refuses_unsafe_grants(access, change):
    p = policy(); e = p['principals'][0]
    if change == 'root': e['uid'] = 0
    if change == 'worker': e['uid'] = 996
    if change == 'duplicate': p['principals'].append(copy.deepcopy(e))
    if change == 'wildcard': e['private_read'] = ['*']
    if change == 'write_without_read': e['private_read'] = []
    if change == 'extra': e['human_authority'] = True
    with pytest.raises(ValueError): m.Access(access.store, p)


def test_policy_is_copied_and_revocation_blocks_duplicate(access):
    p = policy(); gateway = m.Access(access.store, p); submit(gateway)
    p['principals'][0]['write'] = []
    assert not submit(gateway)['inserted']
    revoked = policy(); revoked['principals'][0]['write'] = []
    with pytest.raises(ValueError): submit(m.Access(access.store, revoked))


@pytest.mark.parametrize('offset,limit', [(-1,1),(True,1),(0,False),(0,101)])
def test_bad_pagination(access, offset, limit):
    with pytest.raises(ValueError): history(access, offset=offset, limit=limit)


def test_repository_labels_match_envelope_contract(access):
    p = policy(); p['principals'][0].update(private_read=['Repo-name.v2'], write=['Repo-name.v2'])
    gateway = m.Access(access.store, p)
    r = request(); r['body']['repository_id'] = 'Repo-name.v2'
    submit(gateway, r)
    assert len(history(gateway, repo='Repo-name.v2')['records']) == 1


def test_conflicting_key_preserves_original_peer_receipt(access):
    first = submit(access)
    changed = request(); changed['body']['objective'] = 'Changed intent'
    with pytest.raises(ValueError, match='idempotency'): submit(access, changed)
    assert submit(access) == {'inserted': False, 'receipt': first['receipt']}
    assert len(access.store.pending()['pending']) == 1
