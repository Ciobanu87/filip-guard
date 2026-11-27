import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import groq_usage_reconciliation as recovery


def fixture():
    output=io.StringIO();fields=['request_id','created_at','status_code','model','api_key_id','project_id','input_tokens','input_non_cached_tokens','input_cached_tokens','input_audio_seconds','output_tokens']
    writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
    base=datetime(2026,11,24,7,tzinfo=timezone.utc).timestamp()
    for index in range(15):
        input_tokens=462 if index==0 else 200 if index<14 else 0
        out=186 if index==0 else 50 if index<14 else 0
        writer.writerow(dict(request_id='req_fixture'+str(index),created_at=int((base+index*61)*1000),status_code=200 if index<14 else 429,
            model=recovery.MODEL,api_key_id='fixture-key-id',project_id='fixture-project-id',input_tokens=input_tokens,
            input_non_cached_tokens=input_tokens,input_cached_tokens=0,input_audio_seconds=0,output_tokens=out))
    return output.getvalue().encode()


class ProviderHistoryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.raw=fixture();self.patch=patch.object(recovery,'SOURCE_SHA',hashlib.sha256(self.raw).hexdigest());self.patch.start()
        self.db=sqlite3.connect(':memory:')
    def tearDown(self):self.db.close();self.patch.stop()
    def imported(self):return recovery.import_history(self.db,self.raw,now=recovery.EXPORTED_AT+60)

    def test_exact_provider_rows_tokens_and_429_are_retained(self):
        report=self.imported()
        self.assertEqual((report['provider_requests_imported'],report['http_200'],report['http_429'],report['total_tokens']),(15,14,1,3898))
        self.assertEqual(self.db.execute('SELECT count(*) FROM advisor_requests').fetchone()[0],0)
        self.assertTrue(report['historical_local_reservations_unknown'])
        self.assertFalse(report['quality_cache_reconstructed'])

    def test_import_is_idempotent_and_existing_budgets_never_decrease(self):
        self.imported();day=int(recovery.EXPORTED_AT//86400)
        self.db.execute('UPDATE advisor_budget SET calls=37 WHERE day=?',(day-3,))
        self.db.execute('UPDATE advisor_budget SET calls=7 WHERE day=?',(day,));self.db.commit()
        self.imported()
        self.assertEqual(self.db.execute('SELECT calls FROM advisor_budget WHERE day=?',(day-3,)).fetchone()[0],37)
        self.assertEqual(self.db.execute('SELECT calls FROM advisor_budget WHERE day=?',(day,)).fetchone()[0],7)
        self.assertEqual(self.db.execute('SELECT count(*) FROM recovered_provider_requests').fetchone()[0],15)

    def test_existing_request_rows_survive_recovery(self):
        self.imported()
        self.db.execute("INSERT INTO advisor_requests VALUES ('original','original',1,2,3,'failed','retained')");self.db.commit()
        self.imported()
        self.assertEqual(self.db.execute("SELECT result FROM advisor_requests WHERE scope='original'").fetchone(),('retained',))

    def test_altered_source_cannot_create_a_ledger(self):
        with self.assertRaises(ValueError):recovery.import_history(self.db,self.raw+b'\n',now=recovery.EXPORTED_AT)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0],0)

    def test_conflicting_import_is_not_overwritten(self):
        self.imported()
        self.db.execute('UPDATE recovered_provider_requests SET output_tokens=999 WHERE request_id=?',('req_fixture0',));self.db.commit()
        with self.assertRaises(ValueError):self.imported()
        self.assertEqual(self.db.execute('SELECT output_tokens FROM recovered_provider_requests WHERE request_id=?',('req_fixture0',)).fetchone()[0],999)

    def test_one_probe_durable_marker_prevents_repeat_after_success_or_failure(self):
        for fail in (False,True):
            with self.subTest(fail=fail),tempfile.TemporaryDirectory() as directory:
                self.imported();root=Path(directory);key=root/'synthetic-key';key.write_text('gsk_'+'a'*30);key.chmod(0o400)
                calls=[]
                def exchange(provider,messages,schema):
                    calls.append(1);provider.attempted_exchanges+=1;provider.last_usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}
                    if fail:raise ValueError('synthetic-failure')
                    return {'status':'ok'}
                first=recovery.single_probe(self.db,root,key,now=recovery.EXPORTED_AT+120,exchange=exchange)
                second=recovery.single_probe(self.db,root,key,now=recovery.EXPORTED_AT+121,exchange=exchange)
                self.assertEqual(len(calls),1);self.assertEqual(first['new_provider_attempts'],1)
                self.assertEqual(second['new_provider_attempts'],0);self.assertTrue(second['reused_receipt'])
                # Reset only this in-memory synthetic test DB between subtests.
                self.db.close();self.db=sqlite3.connect(':memory:')

    def test_pending_crash_marker_blocks_every_retry(self):
        self.imported()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'groq-oracle-key-validation-v1.attempt.json').write_text('{}')
            result=recovery.single_probe(self.db,root,root/'absent-key',now=recovery.EXPORTED_AT+10)
            self.assertEqual(result['new_provider_attempts'],0)
            self.assertEqual(result['status'],'previous-attempt-held-no-retry')

    def test_exhausted_budget_or_stale_export_makes_no_attempt(self):
        self.imported();day=int(recovery.EXPORTED_AT//86400)
        self.db.execute('UPDATE advisor_budget SET calls=20 WHERE day=?',(day,));self.db.commit()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);key=root/'synthetic-key';key.write_text('gsk_'+'a'*30);key.chmod(0o400)
            for now in (recovery.EXPORTED_AT+10,recovery.EXPORTED_AT+7*3600):
                with self.assertRaises(ValueError):recovery.single_probe(self.db,root,key,now=now)
            self.assertFalse((root/'groq-oracle-key-validation-v1.attempt.json').exists())


if __name__=='__main__':unittest.main()

class CurrentOwnerAuthorizationTests(unittest.TestCase):
    def test_current_one_call_scope_is_distinct_from_historical_host_only_approval(self):
        from operations_oracle_groq_recovery import validate_probe_authorization
        data=json.loads(Path('deployment/oracle-groq-controlled-validation-request.json').read_text())
        validate_probe_authorization(data)
        for name,value in [('metadata_publication_authorized',False),('maximum_new_provider_attempts',2),('automatic_retries',1),('paid_services_authorized',True),('application_master_key_operations',True),('systemd_service_activation',True)]:
            altered=dict(data);altered[name]=value
            with self.assertRaises(ValueError):validate_probe_authorization(altered)

class MinimizedObservationRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.raw=fixture();self.patch=patch.object(recovery,'SOURCE_SHA',hashlib.sha256(self.raw).hexdigest());self.patch.start()
        self.observation=recovery.verified_daily_observation(self.raw);self.db=sqlite3.connect(':memory:')
    def tearDown(self):self.db.close();self.patch.stop()
    def imported(self):return recovery.import_verified_observation(self.db,self.observation,now=recovery.EXPORTED_AT+60)
    def test_original_verification_emits_no_private_identifiers_or_request_times(self):
        text=json.dumps(self.observation)
        for private in ('fixture-key-id','fixture-project-id','req_fixture','created_at'):
            self.assertNotIn(private,text)
        self.assertEqual(self.observation['total_tokens'],3898)
    def test_minimized_import_does_not_fabricate_cached_requests(self):
        report=self.imported()
        self.assertTrue(report['reconciliation_verified'])
        self.assertEqual(self.db.execute('SELECT requests,http_200,http_429,input_tokens,output_tokens FROM recovered_provider_daily').fetchall(),[(15,14,1,3062,836)])
        self.assertEqual(self.db.execute('SELECT count(*) FROM advisor_requests').fetchone()[0],0)
        self.assertFalse(report['original_sqlite_recovered'])
    def test_existing_counters_and_request_history_are_preserved(self):
        self.imported();today=int(recovery.EXPORTED_AT//86400)
        self.db.execute('UPDATE advisor_budget SET calls=9 WHERE day=?',(today,))
        self.db.execute('UPDATE advisor_budget SET calls=37 WHERE day=?',(today-3,))
        self.db.execute("INSERT INTO advisor_requests VALUES ('prior','prior',1,2,3,'failed','preserved')");self.db.commit()
        self.imported()
        self.assertEqual(self.db.execute('SELECT calls FROM advisor_budget WHERE day=?',(today,)).fetchone()[0],9)
        self.assertEqual(self.db.execute('SELECT calls FROM advisor_budget WHERE day=?',(today-3,)).fetchone()[0],37)
        self.assertEqual(self.db.execute("SELECT result FROM advisor_requests WHERE scope='prior'").fetchone()[0],'preserved')
        self.assertEqual(self.db.execute('SELECT count(*) FROM recovered_provider_daily').fetchone()[0],1)
    def test_modified_or_stale_observation_creates_no_current_day_allowance(self):
        altered=dict(self.observation);altered['requests']=14
        for item,now in ((altered,recovery.EXPORTED_AT+60),(self.observation,recovery.EXPORTED_AT+7*3600)):
            with self.assertRaises(ValueError):recovery.import_verified_observation(self.db,item,now=now)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sqlite_master').fetchone()[0],0)
