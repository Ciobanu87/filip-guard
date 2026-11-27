import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import owner_master_custody as custody

SECRET='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopq'  # synthetic test fixture only
CORE=Path(__file__).parent/'deployment/owner_custody_core.js'
NODE=r"""
require(process.argv[1]);let raw='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>raw+=c);
process.stdin.on('end',async()=>{try{const data=JSON.parse(raw);const bytes=Uint8Array.from(Buffer.from(data.bundle,'base64'));
const result=await FGOwnerCustody.recover(bytes,data.secret);process.stdout.write(JSON.stringify(result));}
catch(error){process.stdout.write(JSON.stringify({status:'recovery-rejected'}));process.exitCode=2;}});
"""


class IndependentOwnerCustodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=bytes(range(32));cls.bundle,cls.proof=custody.create_bundle(cls.master,SECRET,deployment_id='a'*32)
    def node(self,bundle,secret=SECRET):
        result=subprocess.run(['node','-e',NODE,str(CORE)],input=json.dumps({'bundle':base64.b64encode(bundle).decode(),'secret':secret}),capture_output=True,text=True,timeout=30)
        return result.returncode,json.loads(result.stdout)
    def test_existing_python_backup_format_recovers_independently_in_node_webcrypto(self):
        code,result=self.node(self.bundle)
        self.assertEqual(code,0)
        self.assertEqual(result['recovery_proof'],self.proof)
        self.assertTrue(result['offline_application_backup_recovery_verified'])
    def test_wrong_secret_yields_no_key_or_proof(self):
        code,result=self.node(self.bundle,SECRET[::-1])
        self.assertEqual(code,2);self.assertEqual(result,{'status':'recovery-rejected'})
    def test_modified_master_envelope_is_rejected(self):
        data=json.loads(self.bundle);raw=bytearray(base64.b64decode(data['envelope']['ciphertext']));raw[0]^=1
        data['envelope']['ciphertext']=base64.b64encode(raw).decode()
        code,result=self.node(custody.canonical(data))
        self.assertEqual(code,2);self.assertNotIn('recovery_proof',result)
    def test_modified_application_backup_is_rejected(self):
        data=json.loads(self.bundle);raw=bytearray(base64.b64decode(data['application_state_check']['ciphertext']));raw[-1]^=1
        data['application_state_check']['ciphertext']=base64.b64encode(raw).decode()
        self.assertEqual(self.node(custody.canonical(data))[0],2)
    def test_different_deployment_binding_is_rejected(self):
        data=json.loads(self.bundle);data['envelope']['deployment_id']='b'*32
        self.assertEqual(self.node(custody.canonical(data))[0],2)
    def test_export_contains_no_plaintext_master_or_recovery_secret(self):
        self.assertNotIn(SECRET.encode(),self.bundle)
        self.assertNotIn(base64.b64encode(self.master),self.bundle)
        self.assertLess(len(self.bundle),3800)
        envelope=json.loads(self.bundle)['envelope']
        self.assertEqual(len(base64.b64decode(envelope['ciphertext'])),48)
    def test_weak_secret_rejected_before_random_envelope_material(self):
        for value in ('short','a'*43):
            with patch.object(custody.os,'urandom') as random:
                with self.assertRaises(ValueError):custody.create_bundle(self.master,value,deployment_id='a'*32)
                random.assert_not_called()
    def test_exclusive_private_file_never_overwrites_existing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'key'
            custody.exclusive(path,b'original',0o400,os.getuid(),os.getgid())
            with self.assertRaises(FileExistsError):custody.exclusive(path,b'replacement',0o400,os.getuid(),os.getgid())
            self.assertEqual(path.read_bytes(),b'original');self.assertEqual(path.stat().st_mode&0o777,0o400)
    def test_packaged_html_has_exact_script_hashes_and_network_disabled(self):
        document=(CORE.parent/'owner-custody.html').read_text()
        self.assertIn("connect-src 'none'",document)
        scripts=re.findall(r'<script>(.*?)</script>',document,re.S)
        self.assertEqual(len(scripts),2)
        for source in scripts:
            digest=base64.b64encode(hashlib.sha256(source.encode()).digest()).decode()
            self.assertIn("'sha256-"+digest+"'",document)
            self.assertNotIn('localStorage',source);self.assertNotIn('fetch(',source)
    def test_offline_cli_recovers_private_master_without_original_host_or_database(self):
        from recover_owner_master import recover_private_file
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);parent.chmod(0o700);path=parent/'retained-version.key'
            result=recover_private_file(self.bundle,SECRET,path)
            self.assertEqual(path.read_bytes(),self.master);self.assertEqual(path.stat().st_mode&0o777,0o400)
            self.assertEqual(result['deployment_id'],'a'*32);self.assertFalse(result['services_started'])
            with self.assertRaises(FileExistsError):recover_private_file(self.bundle,SECRET,path)
            self.assertEqual(path.read_bytes(),self.master)
    def test_wrong_secret_does_not_create_private_recovery_file(self):
        from recover_owner_master import recover_private_file
        with tempfile.TemporaryDirectory() as directory:
            parent=Path(directory);parent.chmod(0o700);path=parent/'no-key'
            with self.assertRaises(Exception):recover_private_file(self.bundle,SECRET[::-1],path)
            self.assertFalse(path.exists())
    def test_importing_public_helper_does_not_generate_any_master(self):
        with patch.object(custody,'prepare') as prepare:
            self.assertTrue(callable(custody.export_sealed));prepare.assert_not_called()


if __name__=='__main__':unittest.main()
