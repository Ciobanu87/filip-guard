"""Real isolated S3/TLS and SMTP/TLS processes; no cloud or inbox claim.

Only ephemeral credentials, loopback sockets, private generated certificates and
synthetic accounts. A MinIO binary is supplied by CI from pinned official source.
Production transports/configuration are unchanged; fixture DNS and CA trust are
injected only into this runner. No plaintext TLS bypass or external mail exists.
"""
import argparse
import datetime
import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from cryptography import x509
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from external_backup_store import S3BackupConfig,configured_s3_store,ObjectStoreError
from operations_backup import probe_external_backup,export_recovery_manifest
from application_state_backup import export_application_state, recover_application_state, REVIEW_MARKER
from customer_auth import CustomerAuth
from monitoring_email import SMTPConfig,SMTPNotificationSender,VerifiedEmailBinding,MonitoringEmailDispatcher,DeliveryNotStarted
import test_guard_application as application_fixture
import test_monitoring_service as monitoring_fixture


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));return sock.getsockname()[1]


def certificate(root):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'FILIP GUARD disposable infrastructure')])
    now=datetime.datetime.now(datetime.timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=1))
          .not_valid_after(now+datetime.timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
          .add_extension(x509.SubjectAlternativeName([x509.DNSName('object.test'),x509.DNSName('smtp.test')]),critical=False)
          .sign(key,hashes.SHA256()))
    (root/'public.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (root/'private.key').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    (root/'private.key').chmod(0o600)
    return root/'public.crt',root/'private.key'


class Infrastructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fg-real-infrastructure-');cls.root=Path(cls.temp.name)
        cls.root.chmod(0o700);cls.cert,cls.key=certificate(cls.root)
        cls.smtp_port=free_port();cls.s3_port=free_port()
        cls.user='fg-'+secrets.token_hex(8);cls.password=secrets.token_urlsafe(32)
        cls.resolver=socket.getaddrinfo;cls.default_context=staticmethod(ssl.create_default_context)
        def resolve(host,port,*args,**kwargs):
            if host in ('object.test','smtp.test'):
                return cls.resolver('127.0.0.1',cls.s3_port if host=='object.test' else cls.smtp_port,*args,**kwargs)
            return cls.resolver(host,port,*args,**kwargs)
        cls.dns=patch('socket.getaddrinfo',side_effect=resolve);cls.dns.start()
        cls.env=patch.dict(os.environ,{'AWS_CA_BUNDLE':str(cls.cert),'NO_PROXY':'object.test,smtp.test,127.0.0.1,localhost','no_proxy':'object.test,smtp.test,127.0.0.1,localhost'})
        cls.env.start();cls.process=None
        from aiosmtpd.controller import Controller
        from aiosmtpd.smtp import AuthResult
        cls.messages=[];cls.drop_ack=False
        class Sink:
            async def handle_DATA(self,server,session,envelope):
                if any(not address.endswith('@example.test') for address in envelope.rcpt_tos):return '550 Fixture-only recipient'
                cls.messages.append(envelope.original_content)
                if cls.drop_ack:server.transport.close()
                return '250 Accepted by local test sink'
        def auth(server,session,envelope,mechanism,data):
            return AuthResult(success=data.login==cls.user.encode() and data.password==cls.password.encode(),handled=False)
        tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cls.cert,cls.key)
        cls.smtp=Controller(Sink(),hostname='127.0.0.1',port=cls.smtp_port,tls_context=tls,
                            require_starttls=True,auth_required=True,authenticator=auth)
        cls.smtp.start()
        if not SMTP_ONLY:cls.start_minio()

    @classmethod
    def start_minio(cls):
        binary=os.environ.get('FG_MINIO_BINARY')
        if not binary:raise RuntimeError('Pinned MinIO test binary is required; no external provider fallback')
        env={**os.environ,'MINIO_ROOT_USER':cls.user,'MINIO_ROOT_PASSWORD':cls.password,'MINIO_BROWSER':'off'}
        cls.process=subprocess.Popen([binary,'server',str(cls.root/'s3-data'),'--address','127.0.0.1:'+str(cls.s3_port),
                                      '--certs-dir',str(cls.root)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        until=time.monotonic()+40
        while time.monotonic()<until:
            if cls.process.poll() is not None:raise RuntimeError('Isolated MinIO failed to start')
            try:
                connection=http.client.HTTPSConnection('object.test',443,timeout=1,context=cls.default_context(cafile=str(cls.cert)))
                try:
                    connection.request('GET','/minio/health/ready');response=connection.getresponse();response.read(1024)
                    if response.status==200:return
                finally:connection.close()
            except OSError:time.sleep(.1)
        raise RuntimeError('Isolated S3 startup deadline exceeded')

    @classmethod
    def stop_minio(cls):
        if cls.process is not None:
            cls.process.terminate();cls.process.wait(timeout=15);cls.process=None

    @classmethod
    def tearDownClass(cls):
        cls.stop_minio();cls.smtp.stop();cls.env.stop();cls.dns.stop();cls.temp.cleanup()

    def store(self):
        return configured_s3_store(S3BackupConfig('https://object.test','fg-test-'+secrets.token_hex(8)),lambda:(self.user,self.password))

    def new_store(self):
        store=self.store();store.client.create_bucket(Bucket=store.bucket);return store

    def sender(self):
        sender=SMTPNotificationSender(SMTPConfig('smtp.test','alerts@example.test',587,'starttls'),
                                      lambda:(self.user,self.password),authorized=True)
        return sender

    def trusted_tls(self):
        context=self.default_context(cafile=str(self.cert))
        self.assertTrue(context.check_hostname);self.assertEqual(context.verify_mode,ssl.CERT_REQUIRED)
        return patch('monitoring_email.ssl.create_default_context',return_value=context)

    @unittest.skipIf('--smtp-only' in sys.argv,'S3 tests require CI-built official MinIO binary')
    def test_01_real_s3_verified_encrypted_backup_and_independent_recovery(self):
        store=self.new_store();result=probe_external_backup(store)
        self.assertTrue(result['independent_recovery'])
        self.assertNotIn(b'FILIP GUARD synthetic recovery probe',store.get(result['object_id']))

    @unittest.skipIf('--smtp-only' in sys.argv,'S3 tests require CI-built official MinIO binary')
    def test_02_object_survives_actual_server_restart_and_fresh_sdk_client(self):
        store=self.new_store();store.put('restart-proof',b'encrypted-fixture-bytes')
        self.stop_minio();self.start_minio()
        fresh=configured_s3_store(S3BackupConfig('https://object.test',store.bucket),lambda:(self.user,self.password))
        self.assertEqual(fresh.get('restart-proof'),b'encrypted-fixture-bytes')

    @unittest.skipIf('--smtp-only' in sys.argv,'S3 tests require CI-built official MinIO binary')
    def test_03_customer_recovery_in_new_process_without_original_session_or_database(self):
        f=application_fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        store=self.new_store();f.sites.object_store=store
        plan=f.proposal();result=f.application.approve_and_apply(f.a,f.site_a,plan['plan_id'],confirmed=True)
        principal,_=f.sites._owned(f.a,f.site_a)
        manifest=f.root/'receipt.json';export_recovery_manifest(f.sites.root,principal.customer_id,f.site_a,result['backup_id'],manifest)
        key=f.root/'master.key';key.write_bytes(f.master);key.chmod(0o600)
        credentials=f.root/'s3.json';credentials.write_text(json.dumps({'access_key_id':self.user,'secret_access_key':self.password}));credentials.chmod(0o600)
        destination=f.root/'independently-restored.sqlite'
        env={**os.environ,'FG_GUARD_S3_ENDPOINT':'https://object.test','FG_GUARD_S3_BUCKET':store.bucket,
             'FG_GUARD_S3_CREDENTIALS_FILE':str(credentials),'FG_GUARD_MASTER_KEY_FILE':str(key),'FG_GUARD_KEY_ID':'test-key',
             'FG_FIXTURE_S3_PORT':str(self.s3_port)}
        # This child alone maps its fixture DNS; TLS still verifies object.test.
        code="import socket,os,runpy; original=socket.getaddrinfo; socket.getaddrinfo=lambda host,port,*a,**k: original('127.0.0.1',int(os.environ['FG_FIXTURE_S3_PORT']),*a,**k) if host=='object.test' else original(host,port,*a,**k); runpy.run_path('operations_backup.py',run_name='__main__')"
        f.auth.logout(f.a)
        child=subprocess.run([sys.executable,'-c',code,'recover','--authorized-external-access','--manifest',str(manifest),'--destination',str(destination)],
                             cwd=ROOT,env=env,capture_output=True,text=True,timeout=40)
        self.assertEqual(child.returncode,0,'Independent recovery process failed (secrets withheld)')
        self.assertTrue(json.loads(child.stdout)['verified']);self.assertEqual(destination.stat().st_mode&0o777,0o600)

    @unittest.skipIf('--smtp-only' in sys.argv,'S3 tests require CI-built official MinIO binary')
    def test_04_storage_outage_blocks_repair_before_any_wordpress_write(self):
        f=application_fixture.UnifiedFlowTests();f.setUp();self.addCleanup(f.doCleanups)
        f.sites.object_store=self.new_store();plan=f.proposal()
        before=f.backends[f.origins[0]].read_authorized(f.origins[0],'post',1,7)
        self.stop_minio()
        try:
            with self.assertRaises(Exception):f.application.approve_and_apply(f.a,f.site_a,plan['plan_id'],confirmed=True)
            after=f.backends[f.origins[0]].read_authorized(f.origins[0],'post',1,7)
            self.assertEqual(before.content,after.content);self.assertEqual(before.revision,after.revision)
        finally:self.start_minio()

    def email_fixture(self):
        f=monitoring_fixture.MonitoringServiceTests();f.setUp();self.addCleanup(f.doCleanups)
        f.enable();f.monitor.run_once(now=100)
        sender=self.sender()
        return f,MonitoringEmailDispatcher(f.monitor,sender=sender,recipient_resolver=lambda cid:VerifiedEmailBinding(cid,'owner@example.test'))

    def test_05_starttls_delivery_to_local_sink_and_restart_deduplication(self):
        f,dispatcher=self.email_fixture();before=len(self.messages)
        with self.trusted_tls():self.assertEqual(dispatcher.dispatch_once(now=3600)['status'],'sent')
        self.assertEqual(len(self.messages),before+1)
        self.assertIn(b'No repairs were authorized',self.messages[-1])
        restarted=MonitoringEmailDispatcher(f.monitor,sender=self.sender(),recipient_resolver=dispatcher.recipients)
        with self.trusted_tls():self.assertEqual(restarted.dispatch_once(now=7200)['status'],'idle')
        self.assertEqual(len(self.messages),before+1)

    def test_06_untrusted_certificate_prevents_login_and_mail(self):
        sender=self.sender();before=len(self.messages)
        notice={'notification_id':'a'*32,'customer_id':'b'*32,'payload':{'origin':'https://example.test','events':[]}}
        with self.assertRaises(DeliveryNotStarted):sender.send(notice,VerifiedEmailBinding('b'*32,'owner@example.test'))
        self.assertEqual(len(self.messages),before)

    def test_07_lost_smtp_ack_is_quarantined_without_resending(self):
        f,dispatcher=self.email_fixture();before=len(self.messages);type(self).drop_ack=True
        try:
            with self.trusted_tls():self.assertEqual(dispatcher.dispatch_once(now=3600)['status'],'unknown')
        finally:type(self).drop_ack=False
        self.assertEqual(len(self.messages),before+1)
        restarted=MonitoringEmailDispatcher(f.monitor,sender=self.sender(),recipient_resolver=dispatcher.recipients)
        with self.trusted_tls():self.assertEqual(restarted.dispatch_once(now=7200)['status'],'idle')
        self.assertEqual(len(self.messages),before+1)

    @unittest.skipIf('--smtp-only' in sys.argv,'S3 tests require CI-built official MinIO binary')
    def test_08_application_state_recovery_over_real_s3_with_stopped_source(self):
        # Private synthetic state, all SQLite connections closed; not a cloud-host drill.
        with tempfile.TemporaryDirectory(prefix='fg-state-real-s3-') as directory:
            root=Path(directory); source=root/'source'; source.mkdir(mode=0o700)
            auth=CustomerAuth(source/'accounts.sqlite')
            auth.register('recovery-proof','Synthetic-recovery-password')
            key=secrets.token_bytes(32); keys=lambda version:key
            store=self.new_store()
            receipt=export_application_state(source,store,keys,deployment_id='d'*32,key_id='fixture-v1',quiesced=True)
            # Fresh SDK client + new destination; old DB/session is not consulted.
            fresh=configured_s3_store(S3BackupConfig('https://object.test',store.bucket),lambda:(self.user,self.password))
            destination=root/'restored'
            result=recover_application_state(fresh,keys,receipt,destination)
            self.assertTrue(result['verified']); self.assertTrue(result['resume_blocked'])
            self.assertEqual((source/'accounts.sqlite').read_bytes(),(destination/'accounts.sqlite').read_bytes())
            with self.assertRaises(ValueError): CustomerAuth(destination/'accounts.sqlite')
            # Explicit simulated operator review of this disposable offline fixture only.
            (destination/REVIEW_MARKER).unlink()
            recovered=CustomerAuth(destination/'accounts.sqlite')
            self.assertEqual(recovered.resolve(recovered.login('recovery-proof','Synthetic-recovery-password')).username,'recovery-proof')
SMTP_ONLY='--smtp-only' in sys.argv
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Infrastructure)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
