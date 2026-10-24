"""Passive, explicit operational-to-engineering link plans. No control authority.

Packets are allowlisted source claims, not authenticated evidence. The root
exporter is separate; private history intake remains imported, never observed.
"""
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from jsonschema import Draft202012Validator,FormatChecker

SCHEMA=Path(__file__).resolve().parents[2]/'contracts/engineering-managed-export-v1.schema.json'


def local(name):
    spec=importlib.util.spec_from_file_location('managed_link_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def public_reference(value):
    if not isinstance(value,dict) or set(value)!={'namespace','id'}:return False
    if value['namespace']=='git_commit':return bool(re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',value['id']))
    if value['namespace']!='pull_request' or any(c.isspace() for c in value['id']):return False
    p=urlsplit(value['id'])
    return bool(p.scheme=='https' and p.hostname and not p.username and not p.password and not p.query and not p.fragment
                and p.netloc==p.hostname and re.fullmatch('/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*',p.path))


def validate(packet):
    c=local('contract');packet=c.decode(c.encoded(packet))
    Draft202012Validator(json.loads(SCHEMA.read_text()),format_checker=FormatChecker()).validate(packet)
    previous=packet['after'];ids=set()
    for fact in packet['facts']:
        if fact['sequence']<=previous or fact['event_id'] in ids:raise ValueError('ordered unique source events required')
        previous=fact['sequence'];ids.add(fact['event_id'])
        if any(not public_reference(ref) for ref in fact['public_references']):raise ValueError('public source reference required')
        if (fact['event_type']=='decision.recorded')!=(fact['decision_subject'] is not None):raise ValueError('decision subject differs')
    if packet['next_after']!=previous or (packet['has_more'] and not packet['facts']):raise ValueError('invalid export cursor')
    return packet


def plan(work_request,packet):
    c=local('contract');work=c.validate(work_request);packet=validate(packet);source=packet['work'];body=work['body']
    if work['operation'] not in ('work.create','work.revise'):raise ValueError('explicit engineering work revision required')
    if (body['work_item_id']!=source['work_item_id'] or body['repository_id']!=source['repository_id'] or
            body['baseline']!=source['baseline'] or body['allowed_paths']!=source['requested_paths']):
        raise ValueError('exact work identity repository baseline and scope binding required')
    head=c.digest(c.encoded(body))
    binding={'journal_id':packet['journal_id'],'work_item_id':source['work_item_id'],
             'operational_revision':source['revision'],'operational_work_sha256':source['record_sha256'],
             'engineering_revision':body['revision'],'engineering_work_sha256':head}
    requests=[]
    for fact in packet['facts']:
        # Stable across export boundaries/capture times; same source event ID with
        # changed bytes conflicts at intake instead of silently creating a new row.
        key='oplink_'+c.digest(c.encoded({'binding':binding,'event_id':fact['event_id']}))
        references=[{'namespace':'operational_event','id':fact['event_id'],'sha256':fact['record_sha256']},
                    {'namespace':'external','id':'workflow:'+packet['journal_id']+':'+source['work_item_id']+':r'+str(source['revision']),
                     'sha256':source['record_sha256']}]
        references.extend({'namespace':ref['namespace'],'id':ref['id'],'sha256':None} for ref in fact['public_references'])
        request={'contract':'engineering-history.v1','operation':'checkpoint.append','client_event_key':key,'expected_head':head,
                 'source':{'kind':'imported','namespace':'managed_workflow_export','id':fact['event_id']},'occurred_at':None,
                 'body':{'work_item_id':body['work_item_id'],'work_revision_sha256':head,'checkpoint_type':'progress',
                         'summary':'Imported operational source claim; original provenance is quoted, not authenticated by this intake.\n'+c.encoded({'binding':binding,'source_fact':fact}).decode().strip(),
                         'decisions':[],'next_action':None,'references':references}}
        requests.append(c.validate(request))
    return {'contract':'engineering-managed-link-plan.v1','binding':binding,'source_packet_sha256':c.digest(c.encoded(packet)),
            'requests':requests,'next_after':packet['next_after'],'has_more':packet['has_more'],
            'authority_granted':False,'publication_authorized':False,'release_status':'not_inferred'}
