"""New operator protections only; no provider traffic or customer writes."""
import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
from operations_alerting import Incidents,opaque,emit,ping,endpoint
from operations_observer import collect,read_db,backup_freshness
from operations_journal import ingest
from operations_healthchecks import recover_worker
from operations_events import record


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.root.chmod(0o700)
        self.journal=Incidents(self.root)

    def test_incident_survives_reopen_and_successful_ordinary_heartbeat(self):
        source=opaque('uncertain');self.journal.fail('autofix',source,1)
        calls=[];emit(Incidents(self.root),'host','incident',send=lambda url,failed:calls.append((url,failed)) or True)
        self.assertEqual(calls,[('incident',True),('host',False)])
        self.assertEqual(len(self.journal.active()),1)

    def test_verified_confirmation_and_new_failure_reopens(self):
        source=opaque('source');self.journal.fail('backup',source,1)
        self.journal.confirm(source,opaque('independent-readback'),2)
        self.journal.fail('backup',source,1);self.assertEqual(self.journal.active(),[])
        self.journal.fail('backup',source,3);self.assertEqual(len(self.journal.active()),1)

    def test_confirmation_requires_later_recovery_evidence(self):
        source=opaque('source');self.journal.fail('rollback',source,10)
        for evidence,now in (('',11),(opaque('proof'),9)):
            with self.assertRaises(ValueError):self.journal.confirm(source,evidence,now)
        self.assertEqual(len(self.journal.active()),1)

    def test_incident_delivery_failure_withholds_host_heartbeat(self):
        calls=[];result=emit(self.journal,'host','incident',send=lambda u,f:calls.append(u) or False)
        self.assertEqual(calls,['incident']);self.assertFalse(result['heartbeat_confirmed'])

    def test_endpoint_rejects_secrets_in_redirects_queries_and_other_hosts(self):
        valid='https://hc-ping.com/00000000-0000-0000-0000-000000000001'
        self.assertEqual(endpoint(valid),valid)
        for url in (valid+'?token=secret',valid+'/fail',valid.replace('hc-ping.com','example.com'),valid.replace('https:','http:'),valid.replace('.com/','.com:443/')):
            with self.assertRaises(ValueError):endpoint(url)

    def test_safe_ingestion_retry_is_bounded_and_payload_empty(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'OK'
        from unittest.mock import Mock
        opener=Mock();opener.open.side_effect=[OSError('private-error'),Response()]
        self.assertTrue(ping('https://hc-ping.com/00000000-0000-0000-0000-000000000001',True,opener=opener,sleep=lambda _:None))
        self.assertEqual(opener.open.call_count,2)
        for call in opener.open.call_args_list:
            request=call.args[0];self.assertEqual(request.data,b'');self.assertTrue(request.full_url.endswith('/fail'))

    def test_permanent_http_error_has_no_retry_or_secret_log(self):
        from unittest.mock import Mock
        opener=Mock();opener.open.side_effect=urllib.error.HTTPError('secret-url',403,'secret-message',{},None)
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertFalse(ping('https://hc-ping.com/00000000-0000-0000-0000-000000000001',opener=opener))
        self.assertEqual(opener.open.call_count,1);self.assertEqual(output.getvalue(),'')

    def test_all_transient_retries_stop_after_two(self):
        from unittest.mock import Mock
        opener=Mock();opener.open.side_effect=OSError('unavailable')
        self.assertFalse(ping('https://hc-ping.com/00000000-0000-0000-0000-000000000001',opener=opener,sleep=lambda _:None));self.assertEqual(opener.open.call_count,2)

    def test_unknown_wordpress_results_are_detected_without_database_writes(self):
        state=self.root/'state';path=state/'sites'/'owner'/'site'/'repairs.sqlite';path.parent.mkdir(parents=True)
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE repair_plans (plan_id TEXT,state TEXT,expires_at REAL)')
            db.executemany('INSERT INTO repair_plans VALUES (?,?,?)',[('one','outcome_unknown',10),('two','rollback_unverified',10),('three','applying',10),('four','preparing_backup',10)])
        before=path.read_bytes();collect(state,self.journal,now=1000)
        self.assertEqual(path.read_bytes(),before);self.assertEqual(len(self.journal.active()),4)
        self.assertEqual({x[1] for x in self.journal.active()},{'autofix','rollback'})

    def test_missing_database_is_not_initialized(self):
        path=self.root/'missing.sqlite'
        with self.assertRaises(ValueError):read_db(path,'SELECT 1')
        self.assertFalse(path.exists())

    def test_ai_timeout_needs_later_actual_success_not_expired_cooldown(self):
        state=self.root/'state';state.mkdir();path=state/'advisor.sqlite'
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE advisor_requests(state TEXT,started REAL,expires REAL)')
            db.execute("INSERT INTO advisor_requests VALUES ('failed',10,11)")
        collect(state,self.journal,now=1000,expect_ai=True);self.assertEqual(len(self.journal.active()),1)
        collect(state,self.journal,now=2000,expect_ai=True);self.assertEqual(len(self.journal.active()),1)
        with sqlite3.connect(path) as db:db.execute("INSERT INTO advisor_requests VALUES ('complete',2001,3000)")
        collect(state,self.journal,now=2002,expect_ai=True);self.assertEqual(self.journal.active(),[])

    def test_worker_recovery_never_starts_inactive_or_unapproved_service(self):
        from unittest.mock import Mock
        source=opaque('worker');self.journal.fail('worker',source,10);runner=Mock()
        for state,gate in (('inactive',True),('active',False)):
            self.assertEqual(recover_worker(self.journal,now=20,properties={'ActiveState':state},gate=lambda:gate,runner=runner),'held')
        runner.assert_not_called()

    def test_worker_restart_reserved_and_limited_without_false_recovery(self):
        from unittest.mock import Mock
        source=opaque('worker');self.journal.fail('worker',source,10);runner=Mock()
        for now in (20,21):self.assertEqual(recover_worker(self.journal,now=now,properties={'ActiveState':'active'},gate=lambda:True,runner=runner),'requested-not-yet-verified')
        self.assertEqual(recover_worker(self.journal,now=22,properties={'ActiveState':'active'},gate=lambda:True,runner=runner),'limit-reached')
        self.assertEqual(runner.call_count,2);self.assertEqual(len(self.journal.active()),1)
        self.assertEqual(runner.call_args.args[0],['systemctl','try-restart','filip-guard-worker.service'])

    def test_no_restart_of_ui_or_wordpress_mutation(self):
        with self.assertRaises(ValueError):self.journal.reserve_restart('filip-guard-ui.service',10)

    def test_worker_stall_cleared_only_by_advanced_heartbeat(self):
        state=self.root/'state';state.mkdir();path=state/'monitor.sqlite'
        with sqlite3.connect(path) as db:db.execute('CREATE TABLE monitor_runtime(name TEXT,value REAL)');db.execute("INSERT INTO monitor_runtime VALUES ('heartbeat',10)")
        collect(state,self.journal,now=1000,expect_worker=True);self.assertEqual(len(self.journal.active()),1)
        with sqlite3.connect(path) as db:db.execute('UPDATE monitor_runtime SET value=1001')
        collect(state,self.journal,now=1002,expect_worker=True);self.assertEqual(self.journal.active(),[])

    def test_stale_backup_latches_and_receipt_presence_does_not_clear(self):
        root=self.root/'recovery';root.mkdir();backup_freshness(root,self.journal,now=1000)
        self.assertEqual(len(self.journal.active()),1)
        (root/'valid.json').write_text(json.dumps(dict(scope='application_sqlite_state',deployment_id='fixture',key_id='fixture',object_id='fixture',ciphertext_sha256='a'*64)))
        backup_freshness(root,self.journal,now=__import__('time').time());self.assertEqual(len(self.journal.active()),1)

    def test_event_source_does_not_emit_customer_reference(self):
        output=io.StringIO()
        with patch.dict(os.environ,{'FG_OPERATOR_EVENTS':'1'}),contextlib.redirect_stdout(output):record('backup','failed','private_customer_secret')
        self.assertNotIn('private_customer_secret',output.getvalue());event=json.loads(output.getvalue());self.assertEqual(event['state'],'failed')

    def test_journal_recovery_cannot_clear_uncertain_wordpress_or_other_incidents(self):
        def event(kind,state,at):return {'__CURSOR':'cursor'+str(at),'__REALTIME_TIMESTAMP':str(at*1000000),'MESSAGE':json.dumps({'fg_operator_event':1,'kind':kind,'state':state,'reference':'a'*64})}
        ingest(self.journal,[event('autofix','failed',1),event('ai','failed',2),event('ai','verified',3),event('autofix','verified',4)])
        self.assertEqual([x[1] for x in self.journal.active()],['autofix'])

    def test_full_journal_window_does_not_skip_unknown_events(self):
        with self.assertRaises(ValueError):ingest(self.journal,[{}]*1000)
        with self.journal.db() as db:self.assertEqual(db.execute('SELECT * FROM metadata').fetchall(),[])

    def test_backup_interlock_prevents_restart_during_quiesced_export(self):
        import fcntl
        from operations_healthchecks import restart_interlock
        path=self.root/'backup.lock';path.write_text('');path.chmod(0o600)
        with open(path,'r') as handle:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
            from types import SimpleNamespace
            info=path.stat();trusted=SimpleNamespace(st_mode=info.st_mode,st_uid=0,st_nlink=1)
            with patch('operations_healthchecks.os.fstat',return_value=trusted),self.assertRaises(BlockingIOError):
                with restart_interlock(path):self.fail('Restart must not overlap backup')

    def test_private_health_endpoint_does_not_read_customer_pages(self):
        from operations_observer import ui_health
        from unittest.mock import Mock
        connection=Mock();response=Mock();response.status=200;response.read.return_value=b'ok'
        connection.getresponse.return_value=response;factory=Mock(return_value=connection)
        ui_health(self.journal,now=10,connection_factory=factory)
        factory.assert_called_once_with('127.0.0.1',8501,timeout=2)
        self.assertEqual(connection.request.call_args.args,('GET','/_stcore/health'))
        self.assertEqual(self.journal.active(),[])

    def test_installer_refuses_nonroot_before_host_changes(self):
        from deployment.oracle_operator_prepare import run
        with patch('deployment.oracle_operator_prepare.os.geteuid',return_value=123),patch('deployment.oracle_operator_prepare.states') as states:
            with self.assertRaises(ValueError):run({})
            states.assert_not_called()

    def test_installer_never_overwrites_different_existing_file(self):
        from deployment.oracle_operator_prepare import write_once_or_same
        path=self.root/'prepared.py';path.write_bytes(b'old');path.chmod(0o600)
        with self.assertRaises(ValueError):write_once_or_same(path,b'new',0o600)
        self.assertEqual(path.read_bytes(),b'old')

    def test_malformed_event_is_not_forwarded_or_marked_healthy(self):
        with self.assertRaises(ValueError):ingest(self.journal,[{'MESSAGE':'{"fg_operator_event":1,"secret":"do-not-export"}'}])


if __name__=='__main__':unittest.main()
