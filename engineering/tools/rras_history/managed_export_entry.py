"""Capability-free root reader: one frozen source snapshot, private output only."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'vendor'))


def native():
    path=ROOT/'engineering/tools/rras_native/engineering_export.py'
    spec=importlib.util.spec_from_file_location('protected_engineering_export',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def check_boundary():
    if os.getuid()!=0 or os.geteuid()!=0 or os.getgroups():raise ValueError('root-only private source reader required')
    fields=dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines() if ':' in line)
    if fields['NoNewPrivs'].strip()!='1' or any(int(fields[key].strip(),16) for key in ('CapEff','CapPrm','CapInh','CapBnd','CapAmb')):
        raise ValueError('source reader privilege boundary differs')
    if [name for _,name in socket.if_nameindex()]!=['lo']:raise ValueError('source reader network boundary differs')
    if set(os.environ)-{'PATH','HOME','LANG','LC_CTYPE'}:raise ValueError('unexpected source reader environment')


def write(path,raw):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())


def produce(source,output,plan):
    exporter=native();rows=exporter.read_snapshot(source)
    packets=[];after=0;first=None
    for index in range(101):
        packet=exporter.from_snapshot(rows,plan['journal_id'],plan['source_work_sha256'],after=after)
        work=packet['work']
        if (work['work_item_id']!=plan['work_item_id'] or work['repository_id']!=plan['repository_id'] or
                work['baseline']!=plan['baseline'] or work['requested_paths']!=plan['allowed_paths']):
            raise ValueError('reviewed source work baseline or scope differs')
        if first is None:first=work
        elif work!=first:raise ValueError('source revision changed within frozen snapshot')
        raw=exporter.local('workflow_journal').encoded(packet)
        name=f'packet-{index:03d}.json';write(output/name,raw)
        packets.append({'file':name,'sha256':hashlib.sha256(raw).hexdigest(),'events':len(packet['facts'])})
        after=packet['next_after']
        if not packet['has_more']:break
    else:raise ValueError('export page bound exceeded')
    result={'contract':'engineering-production-export-result.v1','work':first,'journal_id':plan['journal_id'],
            'packets':packets,'next_after':after,'source_open_mode':'ro','source_rows_written':False,
            'history_records_written':False,'api_calls':0}
    raw=exporter.local('workflow_journal').encoded(result);write(output/'export-result.json',raw)
    fd=os.open(output,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    return {'exported':True,'pages':len(packets),'events':sum(p['events'] for p in packets),'next_after':after,
            'source_rows_written':False,'history_records_written':False,'api_calls':0}


if __name__=='__main__':
    try:
        check_boundary();output=Path(sys.argv[1]);plan=json.loads((output/'plan.json').read_bytes())
        print(json.dumps(produce(Path('/var/lib/rras-workflow/journal'),output,plan)))
    except Exception:
        import traceback
        traceback.print_exc();raise SystemExit(1)
