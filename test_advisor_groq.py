import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from advisor_groq import GroqFreeProvider,cloud_exchange,HOST,MODEL
from advisor_provider import ProviderUnavailable
from contextual_advisor import configured_advisor,ContextualAdvisor
from test_contextual_advisor import ROWS,CONTEXT,SCOPE,selection

KEY='gsk_'+'synthetic'*6

def response(payload=None):
    return {'model':MODEL,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(payload or {'recommendations':[]})}}],
            'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}

def raw_response(status=200,body=None):
    body=json.dumps(body or response()).encode()
    return f'HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n'.encode()+body

class GroqProviderTests(unittest.TestCase):
    def provider(self):return GroqFreeProvider(lambda:KEY,free_plan_confirmed=True,data_consent=True)
    def test_strict_schema_no_tools_no_reasoning_and_bounded_output(self):
        with patch('advisor_groq.cloud_exchange',return_value=response()) as exchange:
            self.assertEqual(self.provider().generate([],{}),{'recommendations':[]})
        body=json.loads(exchange.call_args.args[0]);self.assertEqual(body['model'],MODEL)
        self.assertTrue(body['response_format']['json_schema']['strict']);self.assertFalse(body['stream'])
        self.assertEqual(body['reasoning_effort'],'none');self.assertEqual(body['max_completion_tokens'],1200)
        self.assertNotIn('tools',body);self.assertNotIn(KEY,str(body))
    def test_free_confirmation_and_data_consent_required_before_any_request(self):
        for free,consent in [(False,False),(False,True),(True,False)]:
            with self.assertRaises(ValueError):GroqFreeProvider(lambda:KEY,free_plan_confirmed=free,data_consent=consent)
        with self.assertRaises(ValueError):GroqFreeProvider(lambda:KEY,model='paid-or-unreviewed',free_plan_confirmed=True,data_consent=True)
    def test_rejects_truncation_refusal_wrong_model_tools_usage_and_bad_json(self):
        malformed=[{**response(),'model':'other'}, {**response(),'choices':[]},
            {**response(),'usage':{'prompt_tokens':100,'completion_tokens':2000,'total_tokens':2100}}]
        for field,value in [('finish_reason','length'),('message',{'role':'assistant','tool_calls':[{}],'content':'{}'}),
                            ('message',{'role':'assistant','refusal':'blocked','content':'{}'}),('message',{'role':'assistant','content':'{"a":1,"a":2}'})]:
            r=response();r['choices'][0][field]=value;malformed.append(r)
        for result in malformed:
            with patch('advisor_groq.cloud_exchange',return_value=result),self.assertRaises(ProviderUnavailable):self.provider().generate([],{})
    def test_fixed_public_tls_host_credential_destination_and_socket_close(self):
        socket=Mock();socket.recv.side_effect=[raw_response(),b'']
        with patch('advisor_groq.create_verified_connection',return_value=socket) as connect:
            self.assertEqual(cloud_exchange(b'{}',KEY,2)['model'],MODEL)
        connect.assert_called_once_with('api.groq.com',timeout=2)
        request=socket.sendall.call_args.args[0]
        self.assertIn(b'Host: api.groq.com',request);self.assertIn(('Bearer '+KEY).encode(),request)
        socket.close.assert_called_once()
    def test_redirect_auth_failure_quota_and_errors_never_retry_or_leak_key(self):
        for status in [206,302,401,403,429,500]:
            socket=Mock();socket.recv.side_effect=[raw_response(status),b'']
            with patch('advisor_groq.create_verified_connection',return_value=socket) as connect,self.assertRaises(ProviderUnavailable) as caught:
                cloud_exchange(b'{}',KEY,2)
            self.assertNotIn(KEY,str(caught.exception));connect.assert_called_once();socket.close.assert_called_once()
    def test_unsafe_key_input_rejected_before_tls(self):
        with patch('advisor_groq.create_verified_connection') as connect:
            for key in ['bad','gsk_'+('a'*20)+'\r\nHost: evil']:
                with self.assertRaises(ValueError):cloud_exchange(b'{}',key,2)
            connect.assert_not_called()
    def test_cloud_uses_same_context_validator_fallback_and_persistent_quota(self):
        with tempfile.TemporaryDirectory() as root:
            engine=ContextualAdvisor(Path(root)/'ledger.sqlite',self.provider(),daily_calls=1)
            def inference(body,*args):
                bundle=json.loads(json.loads(body)['messages'][1]['content'])
                self.assertNotIn('token=private',str(bundle));return response(selection(bundle))
            with patch('advisor_groq.cloud_exchange',side_effect=inference) as exchange:
                self.assertEqual(engine.analyze(ROWS,CONTEXT,scope=SCOPE)['status'],'model-assisted')
                self.assertEqual(engine.analyze(ROWS,CONTEXT,scope=SCOPE)['status'],'model-assisted')
                self.assertEqual(engine.analyze(ROWS,CONTEXT,scope='c'*32+':'+'d'*32)['status'],'rate-limit')
                exchange.assert_called_once()
    def test_configuration_loads_only_explicit_private_key_without_enabling_by_default(self):
        with tempfile.TemporaryDirectory() as root:
            keyfile=Path(root)/'key';keyfile.write_text(KEY);keyfile.chmod(0o600)
            env={'FG_AI_AUTHORIZED':'1','FG_AI_PROVIDER':'groq-free','FG_GROQ_API_KEY_FILE':str(keyfile),
                 'FG_AI_FREE_PLAN_CONFIRMED':'1','FG_AI_CLOUD_DATA_CONSENT':'1','FG_AI_LEDGER_DB':str(Path(root)/'ledger.sqlite')}
            with patch.dict(os.environ,env,clear=True),patch('advisor_groq.cloud_exchange') as network:
                engine=configured_advisor();self.assertEqual(engine.provider.name,'groq-free');network.assert_not_called()
    def test_oversized_cloud_context_is_blocked_before_key_access_or_network(self):
        keys=Mock(return_value=KEY)
        provider=GroqFreeProvider(keys,free_plan_confirmed=True,data_consent=True)
        with patch('advisor_groq.cloud_exchange') as network,self.assertRaises(ProviderUnavailable):
            provider.generate([{'role':'user','content':'x'*6001}],{})
        keys.assert_not_called();network.assert_not_called()
    def test_cloud_minute_limit_survives_reconstruction_and_is_shared_across_scopes(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'ledger.sqlite';provider=self.provider()
            def inference(body,*args):return response(selection(json.loads(json.loads(body)['messages'][1]['content'])))
            with patch('advisor_groq.cloud_exchange',side_effect=inference) as network:
                self.assertEqual(ContextualAdvisor(path,provider,clock=lambda:100).analyze(ROWS,CONTEXT,scope=SCOPE)['status'],'model-assisted')
                self.assertEqual(ContextualAdvisor(path,provider,clock=lambda:101).analyze(ROWS,CONTEXT,scope='c'*32+':'+'d'*32)['status'],'rate-limit')
                self.assertEqual(ContextualAdvisor(path,provider,clock=lambda:161).analyze(ROWS,CONTEXT,scope='c'*32+':'+'d'*32)['status'],'model-assisted')
                self.assertEqual(network.call_count,2)
