import importlib.util
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location('docs_validator',ROOT/'tools/rras_native/validate_mk1_docs.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

@pytest.fixture
def docs(tmp_path):
    def git(*args):return subprocess.run(['git','-C',str(tmp_path),*args],capture_output=True,check=True).stdout
    git('init','-q');(tmp_path/'code.py').write_text('baseline\n');git('add','.');git('-c','user.name=Test','-c','user.email=t@localhost','commit','-qm','baseline')
    baseline=git('rev-parse','HEAD').decode().strip()
    for i,name in enumerate(m.REQUIRED):
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text(f'---\nid: rras.fixture.doc{i}\ntitle: Fixture\nkind: document\nsystem: rras.mk1\nstatus: draft\nlast_verified: null\nsource_refs: []\n---\n\n# Fixture\n')
    return tmp_path,baseline

def test_complete_foundation_passes_without_runtime_claim(docs):
    root,baseline=docs
    result=m.validate(root,baseline)
    assert result['documents']==23 and result['runtime_tested'] is False

@pytest.mark.parametrize('change',['source','missing','duplicate','link','secret','verified','symlink','metadata','baseline'])
def test_failed_acceptance(docs,change):
    root,baseline=docs;p=root/'docs/README.md'
    if change=='source':(root/'code.py').write_text('source changed\n')
    if change=='missing':p.unlink()
    if change=='duplicate':p.write_text(p.read_text().replace('rras.fixture.doc0','rras.fixture.doc1'))
    if change=='link':p.write_text(p.read_text()+'[broken](missing.md)\n')
    if change=='secret':p.write_text(p.read_text()+'PLACEHOLDER_SECRET\n')
    if change=='verified':p.write_text(p.read_text().replace('status: draft','status: verified'))
    if change=='symlink':p.unlink();p.symlink_to(root/'code.py')
    if change=='metadata':p.write_text('# Missing metadata\n')
    if change=='baseline':baseline='0'*40
    with pytest.raises(ValueError):m.validate(root,baseline)

def test_relative_link_and_fenced_example(docs):
    root,baseline=docs;p=root/'docs/README.md'
    p.write_text(p.read_text()+'[source](../code.py)\n```md\n[example](not-real.md)\n```\n')
    assert m.validate(root,baseline)['relative_links_checked']==1
