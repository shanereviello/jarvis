"""One generation containing independently validated curated publication previews."""
import importlib.util
from pathlib import Path
import re


def local(name):
    spec=importlib.util.spec_from_file_location('curated_composite_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def build(parts):
    c=local('contract')
    if type(parts) is not list or not 1<=len(parts)<=16:raise ValueError('bounded curated components required')
    entries=[];seen=set()
    for part in parts:
        if type(part) is not dict or part.get('contract') not in ('engineering-curated-preview.v1','engineering-curated-reporting-preview.v1'):
            raise ValueError('supported nonrecursive curated component required')
        module=local('curated_reporting' if part['contract']=='engineering-curated-reporting-preview.v1' else 'curated_preview')
        # Validation covers all entries even if the selected repository is absent.
        module.search(part,c.digest(c.encoded(part)),'validation','',limit=1)
        for entry in part['entries']:
            if entry['entry_id'] in seen:raise ValueError('duplicate curated component entry')
            seen.add(entry['entry_id']);entries.append(entry)
    if len(entries)>100:raise ValueError('combined curated generation exceeds entry bound')
    result=dict(contract='engineering-curated-composite-preview.v1',audience='jarvis_candidate',visibility='operator_private',
        publication_authorized=False,authority_granted=False,source_freshness='not_polled',parts=parts,entries=entries)
    if len(c.encoded(result))>2*1024*1024:raise ValueError('combined curated generation exceeds size bound')
    return result


def search(preview,reviewed_sha256,repository_id,query,*,offset=0,limit=20):
    c=local('contract')
    if c.digest(c.encoded(preview))!=reviewed_sha256 or build(preview.get('parts'))!=preview:
        raise ValueError('exact validated composite preview required')
    if (type(repository_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',repository_id) or
        type(query) is not str or len(query.encode())>256 or type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50):
        raise ValueError('bounded exact curated query required')
    entries=[]
    for part in preview['parts']:
        module=local('curated_reporting' if part['contract']=='engineering-curated-reporting-preview.v1' else 'curated_preview')
        for part_offset in (0,50):
            result=module.search(part,c.digest(c.encoded(part)),repository_id,query,offset=part_offset,limit=50)
            entries.extend(result['entries'])
            if not result['has_more']:break
    page=entries[offset:offset+limit]
    return dict(entries=page,next_offset=offset+len(page),has_more=offset+len(page)<len(entries),
        preview_sha256=reviewed_sha256,publication_authorized=False,authority_granted=False,source_freshness='not_polled')


def without(preview,ids):
    parts=local('contract').decode(local('contract').encoded(preview))['parts']
    for part in parts:
        part['entries']=[entry for entry in part['entries'] if entry['entry_id'] not in ids]
        if part['contract']=='engineering-curated-reporting-preview.v1':part['coverage']['returned_count']=len(part['entries'])
    return build(parts)
