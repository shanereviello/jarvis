"""Optional isolated curated-reader Unix endpoint; no production entry or ACL change.

Reuse the bounded existing kernel-peer transport with only the curated dispatcher.
"""
import importlib.util
import os
from pathlib import Path


def local(name):
    spec=importlib.util.spec_from_file_location('curated_unix_'+name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


transport=local('unix')


class Server(transport.Server):
    def __init__(self,path,catalog_root,policy,*,on_bound=None):
        transport.uid(os.getuid())
        if os.geteuid()!=os.getuid():raise ValueError('unprivileged curated reader required')
        self.path=transport.endpoint(path)
        self.access=local('curated_read_access').Access(catalog_root,policy)
        self.listener=None;self.identity=None;self.on_bound=on_bound


def call(path,service_uid,message):
    return transport.call(path,service_uid,message)
