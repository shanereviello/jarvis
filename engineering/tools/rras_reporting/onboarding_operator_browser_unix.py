"""Narrow peer-authenticated bridge between browser and operator services.

The operator side re-verifies signed operator headers; UID permission alone is
not human approval. The browser side receives no general history-write access.
"""
import importlib.util
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('operator_browser_unix_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def pack(headers):
    if type(headers) is not list or len(headers)>128:raise ValueError('bounded request headers required')
    result=[];size=0
    for item in headers:
        if type(item) not in (tuple,list) or len(item)!=2 or not all(type(x) is bytes for x in item):raise ValueError('exact request headers required')
        name,value=(x.decode('ascii') for x in item);size+=len(name)+len(value)
        if size>32768:raise ValueError('bounded request headers required')
        result.append([name,value])
    return result


def unpack(headers):
    if type(headers) is not list or len(headers)>128:raise ValueError('bounded request headers required')
    value=[]
    for item in headers:
        if type(item) is not list or len(item)!=2 or not all(type(x) is str for x in item):raise ValueError('exact request headers required')
        value.append(tuple(x.encode('ascii') for x in item))
    pack(value)
    return value


class Broker:
    def __init__(self,browser_uid,browser):
        local('onboarding_broker_unix').unix().uid(browser_uid)
        if not callable(getattr(browser,'begin',None)) or not callable(getattr(browser,'confirm',None)):
            raise ValueError('protected operator browser coordinator required')
        self.grants={browser_uid:{}};self.browser=browser

    def dispatch(self,peer,message):
        if peer not in self.grants or type(message) is not dict:raise ValueError('browser peer refused')
        operation=message.get('operation')
        if operation=='attestation.begin' and set(message)=={'operation','headers','review_id','comment_id'}:
            return self.browser.begin(unpack(message['headers']),message['review_id'],message['comment_id'])
        if operation=='attestation.confirm' and set(message)=={'operation','headers','challenge','statement'}:
            return self.browser.confirm(unpack(message['headers']),message['challenge'],message['statement'])
        raise ValueError('bounded attestation operation required')


class Client:
    def __init__(self,path,service_uid):
        self.unix=local('onboarding_broker_unix').unix();self.unix.uid(service_uid)
        self.unix.DEADLINE_SECONDS=60
        self.path=self.unix.endpoint(path);self.service_uid=service_uid
    def begin(self,headers,review_id,comment_id):
        return self.unix.call(self.path,self.service_uid,dict(operation='attestation.begin',headers=pack(headers),review_id=review_id,comment_id=comment_id))
    def confirm(self,headers,challenge,statement):
        return self.unix.call(self.path,self.service_uid,dict(operation='attestation.confirm',headers=pack(headers),challenge=challenge,statement=statement))
