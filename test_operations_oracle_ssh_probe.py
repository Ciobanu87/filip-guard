import base64
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from operations_oracle_ssh_probe import pinned_known_host,run_probe,REMOTE_COMMAND


class OracleSSHPreflightTests(unittest.TestCase):
    def setUp(self):
        self.blob=b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20'+b'x'*32
        self.public=base64.b64encode(self.blob).decode()
        self.fp='SHA256:'+base64.b64encode(sha256(self.blob).digest()).decode().rstrip('=')
        self.env={'FG_OCI_SSH_PROBE_AUTHORIZED':'1','FG_OCI_HOST':'8.8.8.8',
                  'FG_OCI_HOST_ED25519_SHA256':self.fp,
                  'FG_OCI_SSH_PRIVATE_KEY':'-----BEGIN OPENSSH PRIVATE KEY-----\n'+'x'*180+'\n-----END OPENSSH PRIVATE KEY-----'}
        self.scan='8.8.8.8 ssh-ed25519 '+self.public+'\n'
    def test_matching_host_key_is_pinned_without_trusting_scan_hostname(self):
        self.assertEqual(pinned_known_host('8.8.8.8',self.fp,self.scan),'8.8.8.8 ssh-ed25519 '+self.public+'\n')
    def test_mismatch_blocks_before_authentication(self):
        calls=[]
        def runner(args,**kwargs):
            calls.append(args)
            return SimpleNamespace(returncode=0,stdout=self.scan,stderr='')
        self.env['FG_OCI_HOST_ED25519_SHA256']='SHA256:'+'a'*43
        with self.assertRaises(ValueError):run_probe(self.env,runner)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'ssh-keyscan')
    def test_read_only_authentication_uses_private_files_and_strict_pin(self):
        calls=[];paths=[]
        def runner(args,**kwargs):
            calls.append(args);self.assertNotIn('FG_OCI_SSH_PRIVATE_KEY',kwargs['env'])
            if args[0]=='ssh-keyscan':return SimpleNamespace(returncode=0,stdout=self.scan)
            key=Path(args[args.index('-i')+1]);paths.append(key)
            self.assertEqual(key.stat().st_mode&0o777,0o600)
            self.assertIn('StrictHostKeyChecking=yes',args);self.assertIn('IdentityAgent=none',args)
            self.assertEqual(args[-1],REMOTE_COMMAND)
            return SimpleNamespace(returncode=0,stdout=json.dumps({k:True for k in (
                'arm64','sudo_read_check_available','password_authentication_disabled',
                'public_key_authentication_enabled','root_login_disabled')}))
        report=run_probe(self.env,runner)
        self.assertTrue(report['host_identity_verified']);self.assertFalse(report['server_modified'])
        self.assertFalse(report['always_free_billing_verified']);self.assertEqual(len(calls),2)
        self.assertTrue(all(not p.exists() for p in paths))
        self.assertNotIn(self.env['FG_OCI_SSH_PRIVATE_KEY'],json.dumps(report))
    def test_private_ips_and_invalid_key_shapes_are_rejected(self):
        for host in ('127.0.0.1','10.0.0.1','169.254.169.254'):
            with self.assertRaises(ValueError):pinned_known_host(host,self.fp,self.scan)
        for scan in ('',self.scan.replace('ssh-ed25519','ssh-rsa'),self.scan.replace(self.public,'!!!')):
            with self.assertRaises(ValueError):pinned_known_host('8.8.8.8',self.fp,scan)
    def test_authorization_and_authentication_failure_do_not_modify_server(self):
        with self.assertRaises(ValueError):run_probe({**self.env,'FG_OCI_SSH_PROBE_AUTHORIZED':'0'})
        def runner(args,**kwargs):return SimpleNamespace(returncode=0 if args[0]=='ssh-keyscan' else 255,stdout=self.scan)
        with self.assertRaises(ConnectionError):run_probe(self.env,runner)
