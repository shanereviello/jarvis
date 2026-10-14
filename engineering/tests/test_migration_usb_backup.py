import importlib.util,io,os,tarfile,tempfile,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('backup',Path(__file__).resolve().parents[1]/'tools/migration/usb_backup.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class BackupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_content_and_symlink_restoration(self):
  source=self.root/'source';source.mkdir();(source/'repo').mkdir();(source/'repo/file').write_text('fixture');(source/'repo/link').symlink_to('file')
  manifest,_=m.inventory(source,['repo']);archive=self.root/'backup.tar'
  with tarfile.open(archive,'w') as t:t.add(source/'repo',arcname='repo')
  m.validate_archive(archive);restore=self.root/'restore';restore.mkdir()
  with tarfile.open(archive) as t:t.extractall(restore)
  m.compare_restored(manifest,restore)
  (restore/'repo/file').write_text('tampered')
  with self.assertRaises(ValueError):m.compare_restored(manifest,restore)
 def test_traversal_and_absolute_hardlink_refused(self):
  for name,link in [('../escape',None),('file','/etc/passwd')]:
   archive=self.root/'bad.tar'
   with tarfile.open(archive,'w') as t:
    item=tarfile.TarInfo(name)
    if link:item.type=tarfile.LNKTYPE;item.linkname=link
    t.addfile(item)
   with self.assertRaises(ValueError):m.validate_archive(archive)
 def test_symlink_descendant_refused(self):
  archive=self.root/'bad.tar'
  with tarfile.open(archive,'w') as t:
   link=tarfile.TarInfo('dir');link.type=tarfile.SYMTYPE;link.linkname='/tmp';t.addfile(link);t.addfile(tarfile.TarInfo('dir/file'))
  with self.assertRaises(ValueError):m.validate_archive(archive)

 def test_real_gpg_roundtrip_with_harmless_fixture(self):
  import subprocess,hashlib
  home=self.root/'gnupg';home.mkdir(mode=0o700);plain=self.root/'plain';plain.write_bytes(b'NONSECRET-BACKUP-FIXTURE')
  encrypted=self.root/'encrypted';restored=self.root/'restored'
  base=['gpg','--homedir',str(home),'--batch','--pinentry-mode','loopback','--no-symkey-cache','--passphrase-fd','0']
  password=b'NONSECRET-TEST-PASSPHRASE\n'
  subprocess.run([*base,'--symmetric','--cipher-algo','AES256','--output',str(encrypted),str(plain)],input=password,check=True,capture_output=True)
  subprocess.run([*base,'--decrypt','--output',str(restored),str(encrypted)],input=password,check=True,capture_output=True)
  self.assertEqual(m.digest(plain),m.digest(restored));self.assertNotIn(plain.read_bytes(),encrypted.read_bytes())
