import json
import tempfile
from pathlib import Path
from unittest.mock import Mock,patch
import unittest
from advisor_diagnostics import AdvisorFailure
from advisor_groq import GroqFreeProvider,cloud_exchange
from contextual_advisor import ContextualAdvisor,SCHEMA,FOCUS,MISSING,validate_selection
from advisor_context import evidence_bundle
from advisor_selection_contract import build_schema,normalize
from test_contextual_advisor import ROWS,CONTEXT,SCOPE,selection
from test_advisor_groq import KEY,response,raw_response,indexed_selection

class RealFailureRegressionTests(unittest.TestCase):
    def test_received_api_json_can_fail_semantic_validation_with_exact_safe_reason(self):
        bundle,facts,base=evidence_bundle(ROWS,CONTEXT)
        payload=selection(bundle);payload['recommendations'][0]['seo_draft']='Award-winning furniture with guaranteed delivery'
        with self.assertRaises(AdvisorFailure) as caught:validate_selection(payload,bundle,facts,base,'synthetic')
        self.assertEqual(caught.exception.diagnostic,{'stage':'selection','code':'draft_unsupported'})
        # The new contract transmits no free-form draft/focus/guessed identifiers.
        normalized=normalize(indexed_selection(bundle),base,facts,FOCUS)
        self.assertEqual(validate_selection(normalized,bundle,facts,base,'synthetic')[0]['seo_draft'],CONTEXT[ROWS[0]['page']][0])
    def test_indexed_schema_binds_findings_evidence_and_priority_before_generation(self):
        bundle,facts,base=evidence_bundle(ROWS,CONTEXT);schema=build_schema(base,facts,MISSING)
        root=schema['properties']['recommendations']
        self.assertEqual(root['required'],['f0']);self.assertFalse(root['additionalProperties'])
        fields=root['properties']['f0']['properties']
        self.assertEqual(set(fields),{'evidence_id','priority','missing_information','include_draft'})
        self.assertEqual(fields['priority']['enum'],['Medium','High'])
        self.assertEqual(fields['evidence_id']['enum'],list(facts))
    def test_no_guard_is_removed_for_malicious_indexed_output(self):
        bundle,facts,base=evidence_bundle(ROWS,CONTEXT)
        for change in [{'evidence_id':'p99e0'},{'command':'danger'},{'include_draft':'true'}]:
            payload=indexed_selection(bundle);payload['recommendations']['f0'].update(change)
            with self.assertRaises(AdvisorFailure):normalize(payload,base,facts,FOCUS)
        payload=indexed_selection(bundle);payload['recommendations']['f0']['priority']='Low'
        with self.assertRaises(AdvisorFailure):validate_selection(normalize(payload,base,facts,FOCUS),bundle,facts,base,'synthetic')
    def test_complete_http_body_does_not_wait_for_peer_eof_or_idle_timeout(self):
        socket=Mock();socket.recv.side_effect=[raw_response(),TimeoutError('peer remains open')]
        with patch('advisor_groq.create_verified_connection',return_value=socket):self.assertEqual(cloud_exchange(b'{}',KEY,2)['model'],'qwen/qwen3.8-27b')
        self.assertEqual(socket.recv.call_count,1);socket.close.assert_called_once()
    def test_http_quota_status_and_retry_after_are_exposed_without_error_body(self):
        body=b'{"error":{"message":"'+KEY.encode()+b'"}}'
        raw=b'HTTP/1.1 429 Limited\r\nContent-Type: application/json\r\nRetry-After: 120\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        socket=Mock();socket.recv.side_effect=[raw]
        with patch('advisor_groq.create_verified_connection',return_value=socket),self.assertRaises(AdvisorFailure) as caught:cloud_exchange(b'{}',KEY,2)
        self.assertEqual(caught.exception.diagnostic,{'stage':'http','code':'http_error','http_status':429,'retry_after_seconds':120.0,'quota_kind':'unknown'})
        self.assertNotIn(KEY,str(caught.exception))
    def test_connection_and_read_timeouts_are_distinguishable(self):
        with patch('advisor_groq.create_verified_connection',side_effect=TimeoutError(KEY)),self.assertRaises(AdvisorFailure) as caught:cloud_exchange(b'{}',KEY,2)
        self.assertEqual(caught.exception.diagnostic,{'stage':'connect','code':'timeout'})
        socket=Mock();socket.recv.side_effect=TimeoutError(KEY)
        with patch('advisor_groq.create_verified_connection',return_value=socket),self.assertRaises(AdvisorFailure) as caught:cloud_exchange(b'{}',KEY,2)
        self.assertEqual(caught.exception.diagnostic,{'stage':'read','code':'timeout'})
    def test_backend_and_cached_failures_preserve_safe_diagnostic(self):
        with tempfile.TemporaryDirectory() as root:
            provider=GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True)
            engine=ContextualAdvisor(Path(root)/'ledger.sqlite',provider,clock=lambda:100)
            with patch('advisor_groq.cloud_exchange',side_effect=AdvisorFailure('http_error','http',http_status=401)):
                result=engine.analyze(ROWS,CONTEXT,scope=SCOPE)
            self.assertEqual(result['diagnostic']['http_status'],401)
            self.assertNotIn(KEY,json.dumps(result))

    def test_provider_error_codes_are_allowlisted_while_messages_and_unknown_codes_are_discarded(self):
        for code,expected in [('json_validate_failed',True),(KEY,False)]:
            body={'error':{'code':code,'type':'invalid_request_error','message':KEY,'failed_generation':KEY}}
            socket=Mock();socket.recv.side_effect=[raw_response(400,body)]
            with patch('advisor_groq.create_verified_connection',return_value=socket),self.assertRaises(AdvisorFailure) as caught:
                cloud_exchange(b'{}',KEY,2)
            diagnostic=caught.exception.diagnostic
            self.assertEqual(diagnostic.get('provider_type'),'invalid_request_error')
            self.assertEqual('provider_code' in diagnostic,expected)
            self.assertNotIn(KEY,json.dumps(diagnostic))
