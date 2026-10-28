"""Passive exact review-document packet and durable private intake receiver.

A trusted producer must establish protected custody before build(). Packet hashes
alone authenticate no source, human decision or execution authorization.
"""
import os
from pathlib import Path
import re


def local(name):
    import importlib.util
    spec=importlib.util.spec_from_file_location('review_link_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


MAX_PACKET=512*1024


def build(custody):
    package=custody['package']
    return validate({'contract':'engineering-review-document-export.v1','work_request':custody['work_request'],
        **{key:package[key] for key in ('document_request','manifest','markdown','binding')},
        'visibility':'operator_private','source_provenance':'imported','authority_granted':False})


def validate(packet):
    c=local('contract');packet=c.decode(c.encoded(packet),max_bytes=MAX_PACKET)
    if (set(packet)!={'contract','work_request','document_request','manifest','markdown','binding','visibility','source_provenance','authority_granted'} or
            packet['contract']!='engineering-review-document-export.v1' or packet['visibility']!='operator_private' or
            packet['source_provenance']!='imported' or packet['authority_granted'] is not False):
        raise ValueError('private passive review-document packet required')
    work=c.validate(packet['work_request']);request=c.validate(packet['document_request'])
    if work['operation'] not in ('work.create','work.revise') or request['operation']!='document.render' or request['body']['document_type']!='review':
        raise ValueError('explicit engineering revision and review document required')
    binding=packet['binding']
    fields={'contract','review_id','task_id','work_item_id','work_revision_sha256','document_request_sha256',
            'document_manifest_sha256','markdown_sha256','binding_renderer_sha256','authority_granted','approval_protocol'}
    if (type(binding) is not dict or set(binding)!=fields or binding['contract']!='engineering-managed-review-binding.v1' or
            binding['authority_granted'] is not False or binding['approval_protocol']!='existing_v1_unchanged'):
        raise ValueError('passive capture companion required')
    for key in ('review_id','work_revision_sha256','document_request_sha256','document_manifest_sha256','markdown_sha256','binding_renderer_sha256'):
        if type(binding[key]) is not str or not re.fullmatch('[0-9a-f]{64}',binding[key]):raise ValueError('exact companion digest required')
    if type(binding['task_id']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}',binding['task_id']):raise ValueError('bounded operational task identity required')
    if request['source']!={'kind':'imported','namespace':'managed-review','id':binding['review_id']}:
        raise ValueError('imported capture attribution required')
    raw,manifest=local('documents').render(request,work['body'])
    if (type(packet['markdown']) is not str or packet['markdown'].encode()!=raw or c.encoded(packet['manifest'])!=c.encoded(manifest) or
            binding['work_item_id']!=work['body']['work_item_id'] or
            binding['work_revision_sha256']!=c.digest(c.encoded(work['body'])) or
            binding['document_request_sha256']!=c.digest(c.encoded(request)) or
            binding['document_manifest_sha256']!=c.digest(c.encoded(manifest)) or binding['markdown_sha256']!=c.digest(raw)):
        raise ValueError('exact document, revision and companion association required')
    return packet


def inspect(packet):
    packet=validate(packet);c=local('contract');body=packet['document_request']['body']
    return {'packet_sha256':c.digest(c.encoded(packet)),'work_item_id':body['work_item_id'],
            'repository_id':packet['work_request']['body']['repository_id'],'document_id':body['document_id'],
            'document_version':body['document_version'],'markdown_sha256':packet['binding']['markdown_sha256'],
            'authority_granted':False,'history_records_written':False}


def prepare(root,packet,reviewed_packet_sha256):
    packet=validate(packet);review=inspect(packet);d=local('link_delivery');root=Path(root)
    if review['packet_sha256']!=reviewed_packet_sha256:raise ValueError('exact reviewed document packet required')
    if (os.getuid()==0 or os.geteuid()!=os.getuid() or not root.is_absolute() or
            root.parent.resolve(strict=True)!=root.parent):raise ValueError('canonical unprivileged private state required')
    root.mkdir(mode=0o700);d.guard(root)
    d.write(root/'packet.json',{'packet':packet,'packet_sha256':reviewed_packet_sha256})
    return dict(review,prepared=True,delivery_started=False)


def deliver(root,call,*,writer_uid,peer_uid):
    d=local('link_delivery');sync=local('managed_sync');c=local('contract');root=d.guard(root)
    if (type(peer_uid) is not int or peer_uid!=os.getuid() or type(writer_uid) is not int or
            writer_uid<1 or writer_uid in (996,997)):raise ValueError('explicit caller and service identities required')
    with sync.locked(root):
        saved=d.read(root/'packet.json')
        if set(saved)!={'packet','packet_sha256'}:raise ValueError('frozen document packet differs')
        packet=validate(saved['packet']);sha=c.digest(c.encoded(packet))
        if sha!=saved['packet_sha256']:raise ValueError('frozen packet digest differs')
        sync.target(call,packet['work_request'])  # No implicit work creation/revision.
        request=packet['document_request'];receipt_path=root/'receipt.json'
        if receipt_path.exists() or receipt_path.is_symlink():receipt=d.read(receipt_path)
        else:
            answer=call({'method':'submit','request':request})
            if type(answer) is not dict or set(answer)!={'inserted','receipt'} or type(answer['inserted']) is not bool:
                raise ValueError('document intake response differs')
            receipt=answer['receipt']
            d.check_receipt(receipt,request,writer_uid,peer_uid,document_manifest=packet['manifest']);d.write(receipt_path,receipt)
        d.check_receipt(receipt,request,writer_uid,peer_uid,document_manifest=packet['manifest'])
        back=call({'method':'document','document_id':request['body']['document_id'],'version':request['body']['document_version']})
        if (type(back) is not dict or set(back)!={'markdown','manifest','authority_granted'} or back['authority_granted'] is not False or
                back['markdown']!=packet['markdown'] or c.encoded(back['manifest'])!=c.encoded(packet['manifest'])):
            raise ValueError('exact stored document readback required; receipt retained')
        complete={'contract':'engineering-review-document-intake.v1','packet_sha256':sha,'receipt_id':receipt['receipt_id'],
                  'document_id':request['body']['document_id'],'document_version':request['body']['document_version'],
                  'markdown_sha256':packet['binding']['markdown_sha256'],'authority_granted':False,
                  'task_success_established':False,'release_status':'not_inferred'}
        path=root/'complete.json'
        if path.exists() or path.is_symlink():
            if d.read(path)!=complete:raise ValueError('document completion differs')
        else:d.write(path,complete)
        return complete
