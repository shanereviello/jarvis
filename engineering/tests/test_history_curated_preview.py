"""Explicit curation excludes private source text and preserves claim limits."""
import copy
import pytest
from test_engineering_history_local import module
from test_history_managed_link import setup,exporter,j,fixtures

m=module('curated_preview');c=module('contract')


@pytest.fixture
def preview_inputs(setup):
    *_,history=setup;rows=history.history()['records'];sha=c.digest(c.encoded(rows[0]['submission']))
    selection={'source_request_sha256':sha,'summary':'Prepared managed history recording',
        'rationale':'Keep engineering changes discoverable','limitations':'Proposal only; no task success or deployment established'}
    return rows,[selection]


def test_only_explicit_curation_in_preview(preview_inputs):
    rows,selections=preview_inputs;preview=m.build(rows,selections);raw=c.encoded(preview)
    work=rows[0]['submission']['body']
    for key in ('title','objective','rationale'):assert work[key].encode() not in raw
    entry=preview['entries'][0];assert entry['summary']==selections[0]['summary']
    assert entry['source_provenance']=='agent_reported' and entry['source_authenticated'] is False
    assert preview['visibility']=='operator_private' and preview['publication_authorized'] is False
    assert entry['source_occurred_at'] is None and entry['release_status']=='not_inferred'


@pytest.mark.parametrize('field',['request_sha256','work_item_id','recorded_at','receipt_id'])
def test_changed_receipt_refused(preview_inputs,field):
    rows,selections=copy.deepcopy(preview_inputs);rows[0]['receipt'][field]='invalid'
    with pytest.raises(ValueError):m.build(rows,selections)


@pytest.mark.parametrize('change',['missing_source','duplicate','extra','empty','too_long','control'])
def test_bad_or_implicit_selection_refused(preview_inputs,change):
    rows,selections=copy.deepcopy(preview_inputs)
    if change=='missing_source':selections[0]['source_request_sha256']='f'*64
    elif change=='duplicate':selections*=2
    elif change=='extra':selections[0]['private_document_path']='/private'
    elif change=='empty':selections[0]['summary']=' '
    elif change=='too_long':selections[0]['summary']='x'*4097
    else:selections[0]['summary']='bad\x00text'
    with pytest.raises(ValueError):m.build(rows,selections)


def test_search_is_pinned_bounded_and_repository_scoped(preview_inputs):
    preview=m.build(*preview_inputs);sha=c.digest(c.encoded(preview));repo=preview['entries'][0]['repository_id']
    found=m.search(preview,sha,repo,'MANAGED discoverable')
    assert len(found['entries'])==1 and found['publication_authorized'] is False
    assert m.search(preview,sha,'other_repo','')['entries']==[]
    assert m.search(preview,sha,repo,'nonexistent')['entries']==[]
    with pytest.raises(ValueError):m.search(preview,'f'*64,repo,'')
    with pytest.raises(ValueError):m.search(preview,sha,repo,'',limit=51)
    with pytest.raises(ValueError):m.search(preview,sha,repo,'x'*257)


def test_deterministic_preview_and_search_no_input_mutation(preview_inputs):
    before=copy.deepcopy(preview_inputs);a=m.build(*preview_inputs);b=m.build(*preview_inputs)
    assert a==b and preview_inputs==before
    m.search(a,c.digest(c.encoded(a)),a['entries'][0]['repository_id'],'')
    assert a==b


@pytest.mark.parametrize('field,value',[('private_notes','sentinel'),('curation_provenance','observed'),('source_authenticated',True),('release_status','deployed'),('source_recorded_at','unknown')])
def test_search_refuses_extra_private_fields_and_promoted_authority(preview_inputs,field,value):
    preview=m.build(*preview_inputs);preview['entries'][0][field]=value
    with pytest.raises(ValueError):m.search(preview,c.digest(c.encoded(preview)),preview['entries'][0]['repository_id'],'')


def test_imported_event_claim_and_pagination_do_not_promote_provenance(setup):
    _,_,packet,work,history=setup
    request=module('managed_link').plan(work,packet)['requests'][0];history.submit(request,peer_uid=1000)
    rows=history.history()['records'];selections=[]
    for row in rows:
        selections.append({'source_request_sha256':c.digest(c.encoded(row['submission'])),
            'summary':'Selected recording claim','rationale':'Keep an explicit reference','limitations':'Not independent observed evidence'})
    preview=m.build(rows,selections);sha=c.digest(c.encoded(preview));repo=work['body']['repository_id']
    first=m.search(preview,sha,repo,'recording',limit=1);second=m.search(preview,sha,repo,'recording',offset=first['next_offset'],limit=1)
    assert first['has_more'] and not second['has_more']
    assert second['entries'][0]['source_provenance']=='imported' and second['entries'][0]['source_authenticated'] is False
    assert request['body']['summary'].encode() not in c.encoded(preview)
    withdrawn=m.build(rows,selections[:1]);assert len(m.search(withdrawn,c.digest(c.encoded(withdrawn)),repo,'')['entries'])==1
