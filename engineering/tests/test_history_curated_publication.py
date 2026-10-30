"""Private local publication selection, withdrawal, replay and atomic visibility."""
import copy
import pytest
from test_engineering_history_local import module
from test_history_curated_preview import preview_inputs
from test_history_managed_link import setup,exporter,j,fixtures

m=module('curated_publication');c=module('contract');preview_module=module('curated_preview')


@pytest.fixture
def catalog(preview_inputs,tmp_path):
    preview=preview_module.build(*preview_inputs);repo=preview['entries'][0]['repository_id']
    parent=tmp_path/'private';parent.mkdir(mode=0o700);root=parent/'catalog';m.initialize(root,[repo])
    return root,preview,repo


def publish(root,preview,head=None,key='first'):
    return m.publish(root,preview,c.digest(c.encoded(preview)),head,key,approve_publication=True)


def test_explicit_approval_and_exact_digest_before_write(catalog):
    root,preview,_=catalog
    with pytest.raises(ValueError,match='approval'):m.publish(root,preview,'f'*64,None,'first')
    with pytest.raises(ValueError,match='reviewed preview'):m.publish(root,preview,'f'*64,None,'first',approve_publication=True)
    assert m.head(root) is None and not list((root/'generations').iterdir())


def test_first_publication_replay_and_read(catalog):
    root,preview,repo=catalog;receipt=publish(root,preview)
    assert receipt['human_authenticated'] is False and receipt['authority_granted'] is False
    answer=m.search(root,repo,'managed')
    assert answer['entries']==preview['entries'] and answer['generation_sha256']==receipt['generation_sha256']
    again=publish(root,preview)
    assert again['replayed'] and again['recorded_at']==receipt['recorded_at']
    assert len(list((root/'generations').iterdir()))==1


def test_wrong_repository_refused_before_loading_generation(catalog,monkeypatch):
    root,preview,_=catalog;publish(root,preview)
    monkeypatch.setattr(m,'chain',lambda *_:pytest.fail('unauthorized search must not load catalog'))
    with pytest.raises(ValueError,match='access refused'):m.search(root,'other_repo','secret')


def test_publication_outside_pinned_policy_refused(catalog,preview_inputs):
    root,_,_=catalog;rows,selections=copy.deepcopy(preview_inputs)
    rows[0]['submission']['body']['repository_id']='other_repo'
    sha=c.digest(c.encoded(rows[0]['submission']));rows[0]['receipt']['request_sha256']=sha;selections[0]['source_request_sha256']=sha
    other=preview_module.build(rows,selections)
    with pytest.raises(ValueError,match='outside repository'):publish(root,other)


def test_withdrawal_invalidates_old_cursor_and_does_not_republish_on_replay(catalog):
    root,preview,repo=catalog;first=publish(root,preview);old=first['generation_sha256'];entry=preview['entries'][0]['entry_id']
    withdrawn=m.withdraw(root,[entry],old,'withdraw',approve_withdrawal=True)
    assert m.search(root,repo,'')['entries']==[]
    with pytest.raises(ValueError,match='stale catalog'):m.search(root,repo,'',generation_sha256=old)
    again=publish(root,preview)
    assert again['generation_sha256']==old and m.head(root)==withdrawn['generation_sha256']
    assert m.search(root,repo,'')['entries']==[]
    replay=m.withdraw(root,[entry],old,'withdraw',approve_withdrawal=True)
    assert replay['replayed'] and replay['recorded_at']==withdrawn['recorded_at']


def test_stale_head_and_reused_key_conflict_before_new_generation(catalog):
    root,preview,_=catalog;first=publish(root,preview)
    with pytest.raises(ValueError,match='stale publication'):publish(root,preview,None,'second')
    with pytest.raises(ValueError,match='key conflict'):publish(root,preview,first['generation_sha256'],'first')
    assert len(list((root/'generations').iterdir()))==1


def test_unknown_withdrawal_or_missing_approval_refused(catalog):
    root,preview,_=catalog;first=publish(root,preview)
    with pytest.raises(ValueError,match='approval'):m.withdraw(root,[preview['entries'][0]['entry_id']],first['generation_sha256'],'withdraw')
    with pytest.raises(ValueError,match='source unavailable'):m.withdraw(root,['cur_'+'f'*64],first['generation_sha256'],'withdraw',approve_withdrawal=True)


def test_atomic_pointer_failure_leaves_previous_generation_visible(catalog,monkeypatch):
    root,preview,repo=catalog;first=publish(root,preview);old=first['generation_sha256']
    def stopped(*_):raise OSError('synthetic pointer publication failure')
    monkeypatch.setattr(m.os,'replace',stopped)
    with pytest.raises(OSError):m.withdraw(root,[preview['entries'][0]['entry_id']],old,'withdraw',approve_withdrawal=True)
    assert m.head(root)==old and m.search(root,repo,'')['entries']==preview['entries']
    assert list(root.glob('.current-*.pending')) and len(list((root/'generations').iterdir()))==2
    with pytest.raises(FileExistsError):m.withdraw(root,[preview['entries'][0]['entry_id']],old,'withdraw',approve_withdrawal=True)
    assert m.head(root)==old


def test_read_refuses_changed_generation(catalog):
    root,preview,repo=catalog;first=publish(root,preview)
    path=root/'generations'/(first['generation_sha256']+'.json');path.write_text('{}')
    with pytest.raises(ValueError,match='generation digest'):m.search(root,repo,'')


def test_page_offset_requires_generation(catalog):
    root,preview,repo=catalog;publish(root,preview)
    with pytest.raises(ValueError,match='generation-bound'):m.search(root,repo,'',offset=1)


def test_local_owner_does_not_create_production_paths(catalog):
    root,preview,_=catalog;publish(root,preview)
    for path in root.rglob('*'):
        assert path.stat().st_mode&0o777==(0o700 if path.is_dir() else 0o600)


def test_reopen_returns_original_receipt_without_new_generation(catalog):
    root,preview,_=catalog;first=publish(root,preview)
    reopened=module('curated_publication')
    again=reopened.publish(root,preview,c.digest(c.encoded(preview)),None,'first',approve_publication=True)
    assert again['replayed'] and again['generation_sha256']==first['generation_sha256']
    assert again['recorded_at']==first['recorded_at'] and len(list((root/'generations').iterdir()))==1


def test_concurrent_publication_lock_refused_before_intent(catalog):
    root,preview,_=catalog
    with module('managed_sync').locked(root):
        with pytest.raises(ValueError,match='another sync'):publish(root,preview)
    assert not list(root.glob('intent-*.json')) and m.head(root) is None
