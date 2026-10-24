"""Read-only allowlisted export from one exact operational work revision.

No blobs, prompts, free-text summaries, approval payloads or private actor/config fields
are exported. No journal writes, history delivery, network or control action.
"""
import importlib.util
import os
from pathlib import Path
import sqlite3
import stat


def local(name):
    spec=importlib.util.spec_from_file_location('engineering_export_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def link():
    path=Path(__file__).parent.parent/'rras_history/managed_link.py'
    spec=importlib.util.spec_from_file_location('engineering_link_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def read_snapshot(root):
    j=local('workflow_journal');root=j.private_root(root);path=root/'workflow.sqlite3';info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_nlink!=1 or
            stat.S_IMODE(info.st_mode)!=0o600):raise ValueError('private journal database required')
    for suffix in ('-journal','-wal','-shm'):
        side=Path(str(path)+suffix)
        if side.exists() or side.is_symlink():
            item=side.lstat()
            if side.is_symlink() or not stat.S_ISREG(item.st_mode) or item.st_uid!=os.getuid() or item.st_nlink!=1 or item.st_mode&0o077:
                raise ValueError('unsafe journal sidecar')
    db=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=5,isolation_level=None)
    try:
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        if db.execute('SELECT version FROM meta').fetchall()!=[(1,)]:raise ValueError('unsupported journal schema')
        saved=db.execute('SELECT digest,body,ingest_kind FROM records ORDER BY rowid LIMIT ?', (j.MAX_RECORDS+1,)).fetchall()
        if len(saved)>j.MAX_RECORDS:raise ValueError('bounded journal required')
        rows=[]
        for digest,raw,ingestion in saved:
            record=j.decode(raw)
            if j.digest(raw)!=digest or j.encoded(record)!=raw:raise ValueError('source record digest differs')
            rows.append((record,{'digest':digest,'ingest_kind':ingestion}))
        local('workflow_records').validate_history(record for record,_ in rows)
        return rows
    finally:db.close()


def export(root,journal_id,work_sha,*,after=0,limit=100):
    j=local('workflow_journal');j.exact_digest(work_sha);j.bounds(after,limit)
    return from_snapshot(read_snapshot(root),journal_id,work_sha,after=after,limit=limit)


def from_snapshot(rows,journal_id,work_sha,*,after=0,limit=100):
    """Build a page from the frozen, validated rows returned by read_snapshot."""
    j=local('workflow_journal');j.exact_digest(work_sha);j.bounds(after,limit)
    works=[record for record,meta in rows if record['kind']=='work_item' and meta['digest']==work_sha]
    if len(works)!=1:raise ValueError('exact operational work revision required')
    work=works[0]
    events=sorted([(record,meta) for record,meta in rows if record['kind']=='event' and record['work_item_sha256']==work_sha and record['sequence']>after],key=lambda pair:pair[0]['sequence'])
    selected=events[:limit];facts=[];adapter=link()
    for event,meta in selected:
        fact=j.event_view(event,meta,'jarvis')
        fact.pop('artifacts') # private and public artifact payloads remain separate
        fact['artifacts']=[{key:ref[key] for key in ('artifact_id','sha256','purpose')} for ref in event['artifacts']]
        fact['public_references']=[ref for ref in event['references'] if adapter.public_reference(ref)][:30]
        fact['omitted_reference_count']=len(event['references'])-len(fact['public_references'])
        facts.append(fact)
    packet={'contract':'engineering-managed-export.v1','journal_id':journal_id,
            'work':{key:work[key] for key in ('work_item_id','repository_id','revision','mode','baseline','requested_paths')},
            'after':after,'next_after':selected[-1][0]['sequence'] if selected else after,'has_more':len(events)>len(selected),'facts':facts}
    packet['work']['record_sha256']=work_sha
    return adapter.validate(packet)


def main(argv=None):
    import argparse
    import json
    from jsonschema import ValidationError
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--store',required=True);parser.add_argument('--journal-id',required=True)
    parser.add_argument('--work-sha256',required=True);parser.add_argument('--after',type=int,default=0)
    parser.add_argument('--limit',type=int,default=100);parser.add_argument('--output',required=True)
    args=parser.parse_args(argv)
    try:
        output=Path(args.output)
        local('workflow_journal').private_root(output.parent)
        packet=export(args.store,args.journal_id,args.work_sha256,after=args.after,limit=args.limit)
        raw=local('workflow_journal').encoded(packet)
        fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        fd=os.open(output.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
        print(json.dumps({'exported':True,'packet_sha256':local('workflow_journal').digest(raw),'events':len(packet['facts']),
                          'next_after':packet['next_after'],'has_more':packet['has_more'],'source_mutations':False,'authority_granted':False}))
    except (ValueError,KeyError,TypeError,OSError,sqlite3.Error,ValidationError):
        parser.exit(1,'Engineering export refused; preserve source and existing output. No action or import invoked.\n')


if __name__=='__main__':main()
