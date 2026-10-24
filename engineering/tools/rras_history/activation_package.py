"""Generate a pinned, stdlib root first-activation tool; no runtime mutation."""
import hashlib
import importlib.util
from pathlib import Path


def emit_helper(destination):
    root=Path(__file__).parent
    spec=importlib.util.spec_from_file_location('activation_installer_builder',root/'install_package.py')
    builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
    # Reuse exactly the audited inactive verifier/primitives, excluding its CLI.
    destination=Path(destination)
    temporary=destination.with_name(destination.name+'.inactive-source')
    builder.emit_helper(temporary)
    try:base=temporary.read_text().split("\nif __name__=='__main__':",1)[0]
    finally:temporary.unlink()
    probe=(root/'activation_probe.py').read_text()
    activation=(root/'first_activation.py').read_text()
    with destination.open('x') as stream:stream.write(base+'\nACTIVATION_PROBE='+repr(probe)+'\n'+activation)
    return hashlib.sha256(destination.read_bytes()).hexdigest()
