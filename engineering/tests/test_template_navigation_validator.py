import importlib.util
from pathlib import Path
import subprocess
import pytest

spec=importlib.util.spec_from_file_location('navigation_validator',Path(__file__).resolve().parents[1]/'tools/rras_native/validate_template_navigation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

@pytest.fixture
def repo(tmp_path):
    def git(*args):return subprocess.check_output(['git','-C',str(tmp_path),*args])
    git('init','-q')
    for name,(old,new,target) in m.REPLACEMENTS.items():
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('---\nid: fixture\n---\n'+old+'\n')
        p=tmp_path/target;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('Template\n')
    git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','baseline')
    baseline=git('rev-parse','HEAD').decode().strip()
    for name,(old,new,target) in m.REPLACEMENTS.items():
        p=tmp_path/name;p.write_text(p.read_text().replace(old,new))
    return tmp_path,baseline

def test_exact_replacements_pass(repo):
    result=m.validate(*repo);assert result['exact_replacements']==2 and not result['runtime_tested']

@pytest.mark.parametrize('damage',['extra_text','outside_file','partial','missing_target','symlink_target','wrong_baseline','committed_change'])
def test_incomplete_or_expanded_work_refused(repo,damage):
    root,baseline=repo;name=next(iter(m.REPLACEMENTS));p=root/name
    if damage=='extra_text':p.write_text(p.read_text()+'unapproved text\n')
    if damage=='outside_file':(root/'outside.txt').write_text('refuse')
    if damage=='partial':
        old,new,_=m.REPLACEMENTS[name];p.write_text(p.read_text().replace(new,old))
    if damage=='missing_target':(root/m.REPLACEMENTS[name][2]).unlink()
    if damage=='symlink_target':
        target=root/m.REPLACEMENTS[name][2];target.unlink();target.symlink_to(p)
    if damage=='wrong_baseline':baseline='0'*40
    if damage=='committed_change':
        subprocess.run(['git','-C',str(root),'add','.'],check=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','unexpected commit'],check=True)
    with pytest.raises(ValueError):m.validate(root,baseline)
