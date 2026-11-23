"""Real, disposable WordPress REST tests. Requires local PHP/WP-CLI and a SQL DB.

Never point this runner at an existing WordPress installation. It copies a clean
WordPress source tree, creates its own database and generated test credentials,
starts loopback HTTP/TLS servers, and destroys resources on exit. No public site.
"""
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backup import BackupManager
from wordpress_autofix_engine import AutoFixEngine
from wordpress_rest_gateway import WordPressRESTGateway, WordPressRESTAuthenticationError
from wordpress_revision_guard import RevisionMismatchError


def php_quote(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


class RealWordPress:
    def __init__(self):
        self.stack = ExitStack()
        try:
            self._setup()
        except BaseException:
            self.stack.close()
            raise

    def _setup(self):
        self.temp = self.stack.enter_context(tempfile.TemporaryDirectory(prefix='fg-real-wp-'))
        self.root = Path(self.temp)
        self.php = os.environ.get('FG_WP_PHP_BINARY', 'php')
        self.php_args = [self.php]
        if os.environ.get('FG_WP_PHP_INI'):
            self.php_args += ['-c', os.environ['FG_WP_PHP_INI']]
        self.cli = os.environ['FG_WP_CLI']
        self.wp = self.root / 'wordpress'
        shutil.copytree(os.environ['FG_WP_SOURCE'], self.wp)
        if (self.wp / 'wp-config.php').exists():
            raise RuntimeError('Only a clean WordPress source tree is allowed')
        self.database = 'fg_test_' + secrets.token_hex(6)
        self.db_port = int(os.environ.get('FG_WP_DB_PORT', '3306'))
        if os.environ.get('FG_WP_DB_SERVER'):
            self.start_database()
        self.create_database()
        self.configure_wordpress()
        self.wpcli('core', 'install', '--url=https://fgwp.test', '--title=FILIP GUARD isolated fixture',
                   '--admin_user=fg-admin', '--admin_email=fixture@example.invalid',
                   '--admin_password=' + secrets.token_urlsafe(32), '--skip-email')
        self.wpcli('option', 'update', 'permalink_structure', '/%postname%/')
        plugin = self.wp / 'wp-content/plugins/filip-guard-companion'
        plugin.mkdir()
        shutil.copyfile(ROOT / 'wordpress_companion/filip-guard-companion.php', plugin / 'filip-guard-companion.php')
        self.wpcli('plugin', 'activate', 'filip-guard-companion')
        self.editor_id = int(self.wpcli('user', 'create', 'fg-editor', 'editor@example.invalid',
                                      '--role=editor', '--user_pass=' + secrets.token_urlsafe(24), '--porcelain'))
        self.subscriber_id = int(self.wpcli('user', 'create', 'fg-subscriber', 'subscriber@example.invalid',
                                          '--role=subscriber', '--user_pass=' + secrets.token_urlsafe(24), '--porcelain'))
        self.editor_password = self.wpcli('user', 'application-password', 'create', 'fg-editor', 'FG integration', '--porcelain')
        self.subscriber_password = self.wpcli('user', 'application-password', 'create', 'fg-subscriber', 'FG integration', '--porcelain')
        self.start_servers()
        self.inject_fault = None
        self.request_count = 0

    def command(self, args, *, input=None):
        result = subprocess.run(args, input=input, text=True, capture_output=True, timeout=60)
        if result.returncode:
            # Deliberately omit command/arguments: they may contain test secrets.
            raise RuntimeError('Local fixture command failed; diagnostic: ' + result.stderr[-400:].replace(
                getattr(self, 'editor_password', 'unused-marker'), '[redacted]'))
        return result.stdout.strip()

    def wpcli(self, *args):
        return self.command(self.php_args + [self.cli, '--path=' + str(self.wp), '--skip-themes', '--no-color'] + list(args))

    def start_database(self):
        port_socket = socket.socket()
        port_socket.bind(('127.0.0.1', 0))
        self.db_port = port_socket.getsockname()[1]
        port_socket.close()
        log = self.stack.enter_context(open(self.root / 'database.log', 'w'))
        process = subprocess.Popen([os.environ['FG_WP_DB_SERVER'], '--no-defaults',
            '--basedir=' + os.environ['FG_WP_DB_BASEDIR'], '--datadir=' + os.environ['FG_WP_DB_DATADIR'],
            '--socket=', '--bind-address=127.0.0.1', '--port=' + str(self.db_port),
            '--pid-file=' + str(self.root / 'database.pid'), '--skip-log-bin'], stdout=log, stderr=log)
        self.stack.callback(self.stop_process, process)
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError('Isolated SQL server failed to start')
            try:
                with socket.create_connection(('127.0.0.1', self.db_port), timeout=.2):
                    return
            except OSError:
                time.sleep(.1)
        raise RuntimeError('Isolated SQL server startup timeout')

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def create_database(self):
        script = self.root / 'database.php'
        script.write_text('''<?php
$p=json_decode(stream_get_contents(STDIN),true);
$d=new mysqli('127.0.0.1',$p['user'],$p['password'],'',$p['port']);
if(!$d->query('CREATE DATABASE `'.$p['database'].'` CHARACTER SET utf8mb4')){exit(2);}
''')
        self.db_user = os.environ.get('FG_WP_DB_USER', 'root')
        self.db_password = os.environ.get('FG_WP_DB_PASSWORD', '')
        self.command(self.php_args + [str(script)], input=json.dumps(dict(user=self.db_user,
            password=self.db_password, port=self.db_port, database=self.database)))
        self.stack.callback(self.drop_database)

    def drop_database(self):
        script = self.root / 'drop-database.php'
        script.write_text("<?php $p=json_decode(stream_get_contents(STDIN),true); $d=new mysqli('127.0.0.1',$p['user'],$p['password'],'',$p['port']); $d->query('DROP DATABASE `'.$p['database'].'`');")
        self.command(self.php_args + [str(script)], input=json.dumps(dict(user=self.db_user,
            password=self.db_password, port=self.db_port, database=self.database)))

    def configure_wordpress(self):
        constants = dict(DB_NAME=self.database, DB_USER=self.db_user, DB_PASSWORD=self.db_password,
            DB_HOST='127.0.0.1:' + str(self.db_port), DB_CHARSET='utf8mb4', DB_COLLATE='',
            WP_HOME='https://fgwp.test', WP_SITEURL='https://fgwp.test', WP_ENVIRONMENT_TYPE='staging')
        for key in ('AUTH_KEY','SECURE_AUTH_KEY','LOGGED_IN_KEY','NONCE_KEY','AUTH_SALT','SECURE_AUTH_SALT','LOGGED_IN_SALT','NONCE_SALT'):
            constants[key] = secrets.token_urlsafe(48)
        text = '<?php\n' + ''.join('define(' + php_quote(k) + ',' + php_quote(v) + ');\n' for k,v in constants.items())
        text += "define('FILIP_GUARD_TEST_REPAIRS',true);\ndefine('WP_HTTP_BLOCK_EXTERNAL',true);\ndefine('DISABLE_WP_CRON',true);\ndefine('WP_DEBUG',false);\n$table_prefix='wp_';\ndefine('ABSPATH',__DIR__.'/');\nrequire_once ABSPATH.'wp-settings.php';\n"
        path = self.wp / 'wp-config.php'
        path.write_text(text)
        path.chmod(0o600)

    def start_servers(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'fgwp.test')])
        now = datetime.now(timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(hours=2)).add_extension(x509.SubjectAlternativeName([x509.DNSName('fgwp.test')]),False)
            .add_extension(x509.BasicConstraints(ca=True,path_length=0),True).sign(key,hashes.SHA256()))
        certfile,keyfile=self.root/'fixture.crt',self.root/'fixture.key'
        certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        keyfile.chmod(0o600)
        raw_socket=socket.socket();raw_socket.bind(('127.0.0.1',0));self.http_port=raw_socket.getsockname()[1];raw_socket.close()
        router=self.root/'router.php'
        router.write_text("<?php $_SERVER['HTTPS']='on'; $_SERVER['SERVER_PORT']='443'; require "+php_quote(self.wp/'index.php')+";\n")
        log=self.stack.enter_context(open(self.root/'php-server.log','w'))
        process=subprocess.Popen(self.php_args+['-S','127.0.0.1:'+str(self.http_port),'-t',str(self.wp),str(router)],stdout=log,stderr=log)
        self.stack.callback(self.stop_process,process)
        fixture=self
        class Proxy(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def do_GET(self): self.forward()
            def do_POST(self): self.forward()
            def log_message(self,*args): pass
            def forward(self):
                fixture.request_count += 1
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                upstream=http.client.HTTPConnection('127.0.0.1',fixture.http_port,timeout=15)
                try:
                    upstream.request(self.command,self.path,body=body,
                        headers={**dict(self.headers),'Host':'fgwp.test','Connection':'close'})
                    response=upstream.getresponse(); data=response.read()
                    self.send_response(response.status)
                    for k,v in response.getheaders():
                        if k.lower() not in ('content-length','connection','transfer-encoding','server','date'):
                            self.send_header(k,v)
                    self.send_header('Content-Length',str(len(data)))
                    self.send_header('Connection','close'); self.end_headers(); self.wfile.write(data)
                finally:
                    upstream.close()
        server=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(certfile,keyfile)
        server.socket=context.wrap_socket(server.socket,server_side=True)
        self.tls_port=server.server_address[1]
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.stack.callback(server.server_close);self.stack.callback(server.shutdown)
        self.client_context=ssl.create_default_context(cafile=str(certfile))
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',self.http_port),timeout=.2):break
            except OSError:time.sleep(.05)

    def connector(self, hostname, timeout=15):
        if hostname != 'fgwp.test': raise ValueError('Unexpected local fixture hostname')
        raw=socket.create_connection(('127.0.0.1',self.tls_port),timeout=timeout)
        return self.client_context.wrap_socket(raw,server_hostname=hostname)

    def gateway(self, subscriber=False, wrong=False):
        if subscriber: provider=lambda:('fg-subscriber',self.subscriber_password)
        elif wrong: provider=lambda:('fg-editor','fictitious-invalid-password')
        else: provider=lambda:('fg-editor',self.editor_password)
        return WordPressRESTGateway('https://fgwp.test',provider)

    def post(self):
        return int(self.wpcli('post','create','--post_type=post','--post_status=publish',
            '--post_title=Fixture post','--post_author='+str(self.editor_id),'--post_content=<p>Original</p>','--porcelain'))

    def close(self): self.stack.close()


class RealWordPressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=RealWordPress()
        cls.addClassCleanup(cls.fixture.close)
        cls.network=patch('wordpress_secure_https.create_verified_connection',side_effect=cls.fixture.connector)
        cls.network.start();cls.addClassCleanup(cls.network.stop)

    def setUp(self):
        self.post_id=self.fixture.post()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.gateway=self.fixture.gateway()
        self.engine=AutoFixEngine(Path(self.temp.name)/'engine.sqlite',BackupManager(Path(self.temp.name)/'backup.sqlite'),self.gateway)
        self.session=dict(user_id=self.fixture.editor_id,session_id=secrets.token_urlsafe(32))

    def snapshot(self):
        return self.gateway.read_authorized('https://fgwp.test','post',self.post_id,self.fixture.editor_id)

    def approved(self):
        plan=self.engine.propose(site_url='https://fgwp.test',resource_type='post',resource_id=self.post_id,
            proposed_content='<p>Updated</p>',**self.session)['plan_id']
        return plan,self.engine.approve(plan,confirmed=True,**self.session)

    def test_real_auth_and_permissions(self):
        self.assertEqual(self.snapshot().content,'<p>Original</p>')
        with self.assertRaises(WordPressRESTAuthenticationError):
            self.fixture.gateway(wrong=True).read_authorized('https://fgwp.test','post',self.post_id,self.fixture.editor_id)
        with self.assertRaises(PermissionError):
            self.fixture.gateway(subscriber=True).read_authorized('https://fgwp.test','post',self.post_id,self.fixture.subscriber_id)

    def test_real_approved_engine_write_backup_and_verification(self):
        plan,token=self.approved();result=self.engine.apply(plan,token,**self.session)
        self.assertEqual(result['status'],'applied')
        self.assertEqual(self.snapshot().content,'<p>Updated</p>')
        self.assertEqual(self.engine.backups.get_backup(result['backup_id'])['content'],'<p>Original</p>')
        self.assertEqual(self.engine.apply(plan,token,**self.session),result)

    def test_real_conditional_restore_and_idempotency(self):
        original=self.snapshot()
        updated=self.gateway.compare_and_swap(original,'<p>Updated</p>',self.fixture.editor_id,operation_id=secrets.token_hex(16))
        operation=secrets.token_hex(16)
        restored=self.gateway.compare_and_swap(updated,original.content,self.fixture.editor_id,operation_id=operation)
        self.assertEqual(restored.content,original.content)
        self.assertEqual(self.gateway.compare_and_swap(updated,original.content,self.fixture.editor_id,operation_id=operation),restored)

    def test_real_concurrent_edit_is_preserved(self):
        original=self.snapshot()
        self.fixture.wpcli('post','update',str(self.post_id),'--post_title=Concurrent title')
        with self.assertRaises(RevisionMismatchError):
            self.gateway.compare_and_swap(original,'<p>Updated</p>',self.fixture.editor_id,operation_id=secrets.token_hex(16))
        self.assertEqual(self.snapshot().content,original.content)


def main():
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(RealWordPressTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__': raise SystemExit(main())
