import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from operator_secrets import MountedKeyring,private_file,configured_master_keys
import test_customer_sites as fixtures

class KeyCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.old=secrets.token_bytes(32);self.new=secrets.token_bytes(32)
        for name,key in [('old',self.old),('new',self.new)]:
            p=self.root/(name+'.key');p.write_bytes(key);p.chmod(0o600)
    def test_mounted_versions_survive_reconstruction(self):
        ring=MountedKeyring(self.root,'new');self.assertEqual(ring('old'),self.old)
        self.assertEqual(configured_master_keys({'FG_GUARD_KEY_DIRECTORY':str(self.root),'FG_GUARD_KEY_ID':'new'})('new'),self.new)
        for key in ['../old','missing']:
            with self.assertRaises(ValueError):ring(key)
    def test_missing_short_public_or_symlinked_keys_fail_closed(self):
        for mode,data in [(0o644,self.old),(0o600,b'short')]:
            p=self.root/'bad.key';p.write_bytes(data);p.chmod(mode)
            with self.assertRaises(ValueError):MountedKeyring(self.root,'bad')
        p=self.root/'link.key';p.symlink_to(self.root/'old.key')
        with self.assertRaises(ValueError):MountedKeyring(self.root,'link')
        fifo=self.root/'pipe';os.mkfifo(fifo,0o600)
        with self.assertRaises(ValueError):private_file(fifo,32)
    def test_rotation_preserves_old_archive_recovery_and_owner_isolation(self):
        f=fixtures.CustomerSitesTests();f.setUp();self.addCleanup(f.doCleanups)
        old=f.master
        plan,approval=f.approved();result=f.service.apply(f.a,f.site_a,plan,approval,now=103)
        ring={'test-key':old,'new':self.new};f.service.master_keys=ring.__getitem__;f.service.key_id='new'
        with self.assertRaises(PermissionError):f.service.rotate_credentials(f.b,f.site_a,now=104)
        calls=f.calls
        self.assertEqual(f.service.rotate_credentials(f.a,f.site_a,now=104)['status'],'rotated')
        self.assertEqual(f.calls,calls)
        self.assertEqual(f.service._credentials(f.a,f.site_a,now=104)[0],'admin')
        self.assertEqual(f.service.get_backup(f.a,f.site_a,result['backup_id'],now=104)['content'],'Private original 0')
        self.assertEqual(f.service.rotate_credentials(f.a,f.site_a,now=104)['status'],'unchanged')
        ring.pop('test-key')
        with self.assertRaises(PermissionError):f.service.get_backup(f.a,f.site_a,result['backup_id'],now=104)
    def test_legacy_single_key_configuration_is_still_readable(self):
        provider=configured_master_keys({'FG_GUARD_MASTER_KEY_FILE':str(self.root/'old.key'),'FG_GUARD_KEY_ID':'old'})
        self.assertEqual(provider('old'),self.old)
        with self.assertRaises(PermissionError):provider('new')
