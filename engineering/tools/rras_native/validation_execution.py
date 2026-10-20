"""One-use independent validation of a protected, read-only review candidate.

No model/provider credentials, mutable worker Git, automatic retry or acceptance.
Only a separately installed protected copy may expose these root-only commands.
"""
import importlib.util
import os
from pathlib import Path
import pwd
import selectors
import subprocess
import time

OUTPUT_LIMIT = 2 * 1024 * 1024
TARGET = '/run/rras-validation/repo'
STARTED = 'independent-validation-started.json'
RESULT = 'independent-validation-result.json'
OUTPUT = 'independent-validation-output.bin'


def local(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def bounded_run(argv, timeout):
    """Bound the root systemd client output/time; never signal a worker PID.

    Killing our own client on a bound does not assert the service stopped. The
    fixed unit, RuntimeMaxSec and subsequent independent slot check govern that.
    """
    client = subprocess.Popen(argv, env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'},
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = bytearray(); reason = None; code = None
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(client.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0: reason = 'client_timeout'; break
                ready = selector.select(min(remaining, 0.25))
                for key, _ in ready:
                    block = os.read(key.fileobj.fileno(), 65536)
                    if not block: selector.unregister(key.fileobj); continue
                    room = OUTPUT_LIMIT - len(output)
                    output.extend(block[:room])
                    if len(block) > room: reason = 'output_limit'; break
                if reason: break
            if reason is None:
                try: code = client.wait(timeout=max(0.001, deadline - time.monotonic()))
                except subprocess.TimeoutExpired: reason = 'client_timeout'
    finally:
        if client.poll() is None: client.kill()
        client.wait(); client.stdout.close()
    return {'service_exit':code, 'capture_complete':reason is None, 'interruption':reason, 'output':bytes(output)}


def exclusive(path, raw):
    # activity.absent is deliberately idempotent and cannot be an execution fence.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    local('activity').fsync_directory(Path(path).parent)


def account():
    user = pwd.getpwnam('jarvis-codex-engineering')
    if user.pw_uid != 996 or user.pw_gid != 996 or set(os.getgrouplist(user.pw_name,996)) != {996}:
        raise ValueError('dedicated validation identity changed')


def job_fence(members,review):
    host=local('workflow_journal').decode(members['host-result.json'])
    job=local('approved_launch').trusted(host['job'])
    raw=local('publication_custody').root_bytes(Path(job)/'request.json',1024*1024)
    if local('workflow_journal').decode(raw)!=review['request']:
        raise ValueError('original root job request changed')
    return Path(job)/STARTED


def execute(finish_custody, package, stage):
    v = local('validation_workspace'); v.administrator()
    local('approved_launch').trusted(Path(__file__)); account()
    receipt = v.verify(finish_custody, package, stage)
    plan = receipt['plan']; a = local('activity'); root = Path(finish_custody)
    finish, review, members = local('workflow_finish').load(root)
    argv = local('post_validation').service_argv(plan, TARGET, str(Path(stage) / 'repo'))
    launch = local('approved_launch'); launch.slot()
    if any((root/name).exists() or (root/name).is_symlink() for name in (STARTED,RESULT,OUTPUT)):
        raise ValueError('validation attempt already fenced or has residual evidence')
    fence = {'schema_version':1, 'authorization_id':finish['authorization_id'],
        'plan_sha256':a.digest(a.encoded(plan)), 'stage_sha256':a.digest(a.encoded(receipt)),
        'argv_sha256':a.digest(a.encoded(argv)), 'automatic_retry':False}
    # The original root job is unique to the coding launch. A duplicate finish
    # capture or different stage cannot create another execution authorization.
    exclusive(job_fence(members,review), a.encoded(fence))
    a.absent(root / STARTED, a.encoded(fence))
    try:
        observed = bounded_run(argv, plan['timeout_seconds'] + 30)
    except (OSError, subprocess.SubprocessError):
        observed = {'service_exit':None, 'capture_complete':False, 'interruption':'client_error', 'output':b''}
    a.absent(root / OUTPUT, observed['output'])
    stopped = True
    try: launch.slot()
    except (ValueError, OSError, subprocess.SubprocessError): stopped = False
    after = None
    # Always reverify protected input, never open a worker-writable Git checkout.
    try:
        if v.verify(finish_custody, package, stage) == receipt: after = receipt['review_tree']
    except (ValueError, OSError, KeyError, subprocess.SubprocessError): pass
    facts = {'plan_sha256':fence['plan_sha256'],
        'service_exit':observed['service_exit'] if observed['capture_complete'] else None,
        'host_stop_verified':stopped, 'tree_before':receipt['review_tree'],
        'tree_after':after, 'expected_tree':receipt['review_tree']}
    classification = local('post_validation').observed_result(plan, facts)
    result = dict(schema_version=1, fence=fence, plan=plan, observation=facts,
        classification=classification, capture_complete=observed['capture_complete'],
        interruption=observed['interruption'], output_sha256=a.digest(observed['output']),
        output_bytes=len(observed['output']), authorization_id=finish['authorization_id'])
    a.absent(root / RESULT, a.encoded(result))
    return public(result)


def public(result):
    return {'recorded_result':True, 'outcome':result['classification']['outcome'],
        'host_stop_verified':result['observation']['host_stop_verified'],
        'automatic_retry':False, 'publication_authorized':False, 'task_success_established':False}


def load(finish_custody, package, stage):
    v = local('validation_workspace'); v.administrator()
    local('approved_launch').trusted(Path(__file__))
    receipt = v.verify(finish_custody, package, stage)
    a = local('activity'); root = Path(finish_custody); read = local('publication_custody').root_bytes
    decode = local('workflow_journal').decode
    result = decode(read(root / RESULT, 1024*1024)); fence = decode(read(root / STARTED, 1024*1024))
    output = read(root / OUTPUT, OUTPUT_LIMIT)
    finish, review, members = local('workflow_finish').load(root)
    plan = receipt['plan']; argv = local('post_validation').service_argv(plan,TARGET,str(Path(stage)/'repo'))
    global_fence=decode(read(job_fence(members,review),1024*1024))
    expected = {'schema_version':1,'authorization_id':finish['authorization_id'],
        'plan_sha256':a.digest(a.encoded(plan)), 'stage_sha256':a.digest(a.encoded(receipt)),
        'argv_sha256':a.digest(a.encoded(argv)), 'automatic_retry':False}
    facts = result['observation']
    if (result['schema_version'] != 1 or result['fence'] != fence or fence != expected or global_fence != fence or
            result['authorization_id'] != finish['authorization_id'] or result['plan'] != plan or
            result['output_sha256'] != a.digest(output) or result['output_bytes'] != len(output) or
            type(result['capture_complete']) is not bool or
            result['interruption'] not in (None,'client_timeout','output_limit','client_error') or
            result['capture_complete'] != (result['interruption'] is None) or
            (not result['capture_complete'] and facts['service_exit'] is not None) or
            facts['tree_before'] != receipt['review_tree'] or facts['expected_tree'] != receipt['review_tree'] or
            facts['tree_after'] not in (None,receipt['review_tree']) or
            result['classification'] != local('post_validation').observed_result(plan,facts)):
        raise ValueError('independent validation custody changed')
    return finish, review, result


def record(finish_custody, package, stage):
    finish, review, result = load(finish_custody,package,stage)
    local('workflow_finish').record(finish_custody)
    events = local('managed_events'); store = events.journal(review); a = local('activity')
    auth = finish['authorization_id']; work = review['admission']['work_item']
    # Raw stdout remains in root-only custody and is never an artifact payload.
    payload = a.encoded({k:v for k,v in result.items() if k != 'plan'})
    digest = a.digest(payload); actor = {'type':'service','id':'independent-validator'}
    event = {'event_id':events.stable('evt_',auth,'independent-validation'),
        'work_item_id':work['work_item_id'], 'work_item_sha256':review['admission']['work_item_sha256'],
        'attempt_id':events.stable('att_',auth), 'actor':actor,
        'provenance':{'kind':'observed','source':{'namespace':'external','id':'host-validation:'+digest},
                      'source_sha256':digest,'recorded_by':actor},
        'event_type':'validation.finished', 'outcome':result['classification']['outcome'],
        'summary':'Host independent validation attempt against an immutable review candidate; task acceptance and release remain separate.',
        'artifacts':[{'artifact_id':events.stable('art_',auth,'independent-validation'),'sha256':digest,
                      'media_type':'application/json','visibility':'operator_only','purpose':'validation'}],
        'references':[{'namespace':'authorization','id':auth},
                      {'namespace':'git_commit','id':result['plan']['identity']['commit']}],
        'corrects_event_id':None,'decision_subject':None}
    store.append([],{digest:payload},transition=(event,None))
    return dict(public(result), journal_recorded=True, provenance='observed')


def release(finish_custody, package, stage):
    """Publish only a bounded protected proof after durable successful recording."""
    finish, review, result = load(finish_custody,package,stage)
    if result['classification']['outcome'] != 'succeeded':
        raise ValueError('successful independent validation required')
    record(finish_custody,package,stage)
    a=local('activity');read=local('publication_custody').root_bytes
    hf=local('publication_handoff');handoff=local('workflow_journal').decode(read(Path(package)/'handoff.json',1024*1024))
    identity=result['plan']['identity']
    proof={'schema_version':1,'handoff_sha256':a.digest(a.encoded(handoff)),
        'commit':identity['commit'],'baseline':identity['baseline'],'export_id':identity['export_id'],
        'outcome':'succeeded','scope':'independent_mechanical_validation',
        'plan_sha256':result['observation']['plan_sha256'],'result_sha256':a.digest(a.encoded(result)),
        'task_success_established':False,'merge_authorized':False,'deploy_authorized':False}
    hf.validate_proof(handoff,proof)
    destination=Path(package)/'independent-validation.json'
    a.absent(destination,a.encoded(proof));destination.chmod(0o444)
    return {'released_validation_proof':True,'commit':identity['commit'],'merge_authorized':False,'deploy_authorized':False}
