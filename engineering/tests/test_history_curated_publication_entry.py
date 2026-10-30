"""Whole-request binding and explicit publication-only dispatch."""
import pytest
from test_engineering_history_local import module
from test_history_curated_publication import catalog
from test_history_curated_preview import preview_inputs
from test_history_managed_link import setup,exporter,j,fixtures

m=module('curated_publication_entry');c=module('contract');pub=module('curated_publication')


def packet(preview):
    return {'contract':'engineering-curated-publication-request.v1','operation':'publish','approved':True,
            'client_key':'selected','expected_head':None,'preview':preview,'reviewed_preview_sha256':c.digest(c.encoded(preview))}


def apply(root,value):
    raw=c.encoded(value);return m.apply(root,raw,c.digest(raw))


def test_publish_withdraw_replay_and_no_authority(catalog):
    root,preview,repo=catalog;p=packet(preview);first=apply(root,p)
    assert first['human_authenticated'] is False and first['authority_granted'] is False
    assert apply(root,p)['replayed'] is True
    withdrawal={'contract':p['contract'],'operation':'withdraw','approved':True,'client_key':'withdraw',
                'expected_head':first['generation_sha256'],'entry_ids':[preview['entries'][0]['entry_id']]}
    second=apply(root,withdrawal)
    assert pub.search(root,repo,'')['entries']==[]
    assert apply(root,p)['generation_sha256']==first['generation_sha256']
    assert pub.head(root)==second['generation_sha256']


@pytest.mark.parametrize('change',[{'approved':False},{'approved':1},{'catalog':'/private/history'},
                                  {'operation':'initialize'},{'operation':'search'},{'extra':True}])
def test_unsupported_packet_never_mutates(catalog,change):
    root,preview,_=catalog;p=packet(preview);p.update(change)
    with pytest.raises(ValueError):apply(root,p)
    assert pub.head(root) is None and list((root/'generations').iterdir())==[]


def test_exact_bytes_and_preview_hash_required(catalog):
    root,preview,_=catalog;p=packet(preview);raw=c.encoded(p)
    with pytest.raises(ValueError,match='bytes differ'):m.apply(root,raw+b' ',c.digest(raw))
    p['reviewed_preview_sha256']='0'*64
    with pytest.raises(ValueError,match='reviewed preview'):apply(root,p)
    with pytest.raises(ValueError,match='bounded'):m.apply(root,b'x'*(m.LIMIT+1),'0'*64)
    assert pub.head(root) is None


def test_production_entry_refuses_operator_without_catalog_access():
    import subprocess
    import sys
    result=subprocess.run([sys.executable,'-I','-B',str(m.__file__),'--reviewed-request-sha256','0'*64],
                          input=b'{}',capture_output=True,timeout=10)
    assert result.returncode==1
    assert result.stdout==b''
    assert b'Curated publication refused' in result.stderr
