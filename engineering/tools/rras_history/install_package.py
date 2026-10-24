"""Generate a reviewable stdlib-only installer; never install while packaging."""
import hashlib
from pathlib import Path


def emit_helper(destination):
    root=Path(__file__).parent
    common=(root/'history_acceptance_package.py').read_text().split('\ndef safe_name(',1)[0]
    verifier=(root/'production_package.py').read_text().split("\nif __name__=='__main__':",1)[0]
    # Capture only already-reviewed stdlib primitives. Root never loads Python
    # modules from the candidate, imports vendor code, or uses its sys.path.
    binding='''
from types import SimpleNamespace
_install_common=SimpleNamespace(encoded=encoded,decode=decode,regular=regular,LIMIT=LIMIT)
'''
    override='''
def common():return _install_common
'''
    installer=(root/'inactive_install.py').read_text()
    destination=Path(destination)
    with destination.open('x') as stream:stream.write(common+binding+'\n'+verifier+override+'\n'+installer)
    return hashlib.sha256(destination.read_bytes()).hexdigest()
