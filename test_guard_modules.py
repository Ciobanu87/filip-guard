import json
import unittest
from unittest.mock import Mock,patch
from guard_module_contract import configure,Check,CONTRACT_VERSION
from guard_network import GuardNetwork
import commerce_guard
import api_app_guard
import infrastructure_guard


class Context:
    origin='https://example.com'
    json=staticmethod(GuardNetwork.json)
    def __init__(self,response=(200,'application/json',b'{"status":"ok"}')):self.response=response;self.calls=[]
    def site(self,path):self.calls.append(path);return self.response
    def dns(self):return ['93.184.216.34']
    def certificate_expiry(self):return 100+86400*60


class GuardContractTests(unittest.TestCase):
    def test_three_modules_are_explicit_read_only_and_future_agent_is_not_registered(self):
        for name in ('agent','ai_agent','dynamic','commands'):
            with self.assertRaises(ValueError):configure('https://example.com',{name:{}})
        check=Check('api','status','https://example.com/health','fail','HTTP mismatch','Review service')
        self.assertFalse(check.finding()['autofix']);self.assertEqual(check.as_dict()['contract_version'],CONTRACT_VERSION)
        self.assertEqual(check.finding()['key'],check.finding()['key'])

    def test_external_private_mutating_credential_and_encoded_paths_rejected(self):
        bad=['https://elsewhere.example','//127.0.0.1/x','/checkout','/cart','/wp-admin/options.php','/logout',
             '/%252e%252e/private','/health?token=abc','/x#fragment','/x\\y','/gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ','/api%252flogout']
        for path in bad:
            with self.subTest(path=path),self.assertRaises(ValueError):configure('https://example.com',{'api':{'paths':[path]}})
        with self.assertRaises(ValueError):configure('https://127.0.0.1',{'api':{'paths':['/health']}})

    def test_module_count_and_configuration_are_bounded(self):
        with self.assertRaises(ValueError):configure('https://example.com',{'api':{'paths':['/a','/b','/c','/d']}})
        with self.assertRaises(ValueError):configure('https://example.com',{'api':{'paths':['/health'],'headers':{'Authorization':'secret'}}})
        with self.assertRaises(ValueError):configure('https://example.com',{'api':{'paths':['/health'],'required_keys':['token']}})
        with self.assertRaises(ValueError):configure('https://example.com',{'infrastructure':{'registered_domain':'other.com'}})
        with self.assertRaises(ValueError):configure('https://example.com',{'infrastructure':{'expected_ips':['127.0.0.1']}})
        self.assertEqual(configure('https://shop.example.com',{'infrastructure':{'registered_domain':'example.com'}})['infrastructure']['registered_domain'],'example.com')


class ModuleBehaviorTests(unittest.TestCase):
    def test_api_status_json_shape_and_empty_204_are_distinct_contracts(self):
        config=configure(Context.origin,{'api':{'paths':['/health'],'required_keys':['status']}})['api']
        checks=list(api_app_guard.run(Context(),config));self.assertTrue(all(c.status=='pass' for c in checks))
        checks=list(api_app_guard.run(Context((503,'application/json',b'{}')),config))
        self.assertEqual(checks[0].status,'fail');self.assertEqual(len(checks),1)
        checks=list(api_app_guard.run(Context((200,'application/json',b'{}')),config))
        self.assertEqual(checks[-1].status,'fail');self.assertEqual(checks[-1].code,'json-contract')
        config=configure(Context.origin,{'api':{'paths':['/health'],'statuses':[204],'require_json':False}})['api']
        self.assertEqual(list(api_app_guard.run(Context((204,'',b'')),config))[0].status,'pass')

    def test_json_health_values_are_checked_without_retaining_response_values(self):
        config=configure(Context.origin,{'api':{'paths':['/health'],'json_equals':{'status':'ok'}}})['api']
        checks=list(api_app_guard.run(Context((200,'application/json',b'{"status":"error"}')),config))
        self.assertEqual(checks[-1].status,'fail')
        self.assertNotIn('error',json.dumps(checks[-1].evidence))
        with self.assertRaises(ValueError):configure(Context.origin,{'api':{'paths':['/health'],'json_equals':{'status':'gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ'}}})

    def test_invalid_duplicate_json_and_secrets_never_enter_module_results(self):
        secret='gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        config=configure(Context.origin,{'api':{'paths':['/health']}})['api']
        for body in (b'{bad',b'{"status":1,"status":2}',b'{"status":NaN}'):
            checks=list(api_app_guard.run(Context((200,'application/json',body)),config))
            self.assertEqual(checks[-1].code,'json-contract');self.assertEqual(checks[-1].status,'fail')
        checks=list(api_app_guard.run(Context((200,'application/json',json.dumps({'status':'ok','token':secret}).encode())),config))
        self.assertNotIn(secret,json.dumps([c.as_dict() for c in checks]))

    def test_product_expectations_do_not_place_orders_or_treat_zero_price_as_failure(self):
        config=configure(Context.origin,{'commerce':{'paths':['/product/table'],'require_product':True,'expected_currency':'EUR'}})['commerce']
        product={'@type':'Product','offers':{'price':'0','priceCurrency':'EUR'}}
        html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        context=Context((200,'text/html',html.encode()));checks=list(commerce_guard.run(context,config))
        self.assertTrue(all(c.status=='pass' for c in checks));self.assertEqual(context.calls,['/product/table'])
        product['offers']['price']='-1';html='<script type="application/ld+json">'+json.dumps(product)+'</script>'
        self.assertEqual(list(commerce_guard.run(Context((200,'text/html',html.encode())),config))[-1].status,'fail')
        self.assertEqual(list(commerce_guard.run(Context((200,'text/html',b'<h1>Table</h1>')),config))[-1].status,'fail')

    def test_dns_and_tls_expiry_are_verified_not_guessed(self):
        config=configure(Context.origin,{'infrastructure':{'expected_ips':['93.184.216.34']}})['infrastructure']
        checks=list(infrastructure_guard.run(Context(),config,now=100));self.assertTrue(all(c.status=='pass' for c in checks))
        context=Context();context.certificate_expiry=lambda:100+86400*7
        self.assertEqual(list(infrastructure_guard.run(context,config,now=100))[-1].status,'fail')
        context.certificate_expiry=Mock(side_effect=ValueError('untrusted cert'))
        self.assertEqual(list(infrastructure_guard.run(context,config,now=100))[-1].status,'unknown')

    def test_registry_expiry_binds_authority_and_domain_without_retaining_contact_data(self):
        context=Context();calls=[]
        def get(url,**kwargs):
            calls.append(url)
            if url==infrastructure_guard.BOOTSTRAP:return 200,'application/json',json.dumps({'services':[[['com'],['https://registry.example/rdap/']]]}).encode()
            return 200,'application/rdap+json',json.dumps({'objectClassName':'domain','ldhName':'EXAMPLE.COM','events':[{'eventAction':'expiration','eventDate':'2030-01-01T00:00:00Z'}],'entities':[{'private':'registrant-data'}]}).encode()
        context.get=get
        config=configure(Context.origin,{'infrastructure':{'registered_domain':'example.com'}})['infrastructure']
        checks=list(infrastructure_guard.run(context,config,now=100))
        self.assertEqual(checks[-1].status,'pass');self.assertEqual(calls[-1],'https://registry.example/rdap/domain/example.com')
        self.assertNotIn('registrant-data',json.dumps([c.as_dict() for c in checks]))


class GuardNetworkTests(unittest.TestCase):
    def test_same_pinned_https_transport_no_credentials_and_no_redirect_following(self):
        raw=b'HTTP/1.1 302 Found\r\nLocation: https://127.0.0.1/\r\nContent-Length: 0\r\n\r\n'
        reserve=Mock();context=GuardNetwork('https://example.com',before_request=reserve)
        with patch('guard_network._https_request_exchange',return_value=raw) as exchange:
            with self.assertRaises(ValueError):context.site('/health')
        exchange.assert_called_once();reserve.assert_called_once()
        self.assertNotIn('Authorization',str(exchange.call_args));self.assertNotIn('Cookie',str(exchange.call_args))
        with patch('guard_network._https_request_exchange') as exchange:
            with self.assertRaises(ValueError):context.get('https://other.example/health')
            exchange.assert_not_called()

    def test_certificate_connection_is_always_closed(self):
        connection=Mock();connection.getpeercert.side_effect=ValueError('malformed certificate')
        with patch('guard_network.create_verified_connection',return_value=connection):
            with self.assertRaises(ValueError):GuardNetwork('https://example.com').certificate_expiry()
        connection.close.assert_called_once()

class ComposedGuardTests(unittest.TestCase):
    def test_shared_budget_covers_all_enabled_modules_and_never_calls_ai(self):
        from guard_module_scan import GuardModuleScan
        body=b'{"status":"ok"}'
        raw=b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        settings={'website':False,'api':{'paths':['/one','/two','/three']},'infrastructure':{}}
        with patch('guard_network._https_request_exchange',return_value=raw) as exchange,patch('guard_network.resolve_public_ips') as dns,patch('guard_network.create_verified_connection') as tls:
            report=GuardModuleScan(settings,min_gap=0)('https://example.com',max_requests=2)
        self.assertEqual(exchange.call_count,2);dns.assert_not_called();tls.assert_not_called()
        self.assertEqual(report.requests,2);self.assertFalse(report.complete)
        self.assertTrue(any(check['status']=='unknown' for check in report.module_checks))
        self.assertTrue(all(check['autofix'] is False for check in report.module_checks))

    def test_existing_website_results_survive_extension_failure(self):
        from guard_module_scan import GuardModuleScan
        from monitoring_scan import make_report
        def website(origin,**kwargs):
            kwargs['before_request']()
            return make_report([dict(page=origin,http_status=200,title='Page',meta_description='',h1_count=1,images_missing_alt=0)],[],[],1)
        with patch('guard_network._https_request_exchange',side_effect=OSError('secret failure')):
            report=GuardModuleScan({'api':{'paths':['/health']}},website=website,min_gap=0)('https://example.com',max_requests=4)
        self.assertTrue(any(f['problem']=='Missing meta description' for f in report.findings))
        self.assertEqual(report.requests,2);self.assertFalse(report.complete)
        self.assertNotIn('secret failure',json.dumps(report.module_checks))

    def test_success_and_failure_share_scope_so_recovery_can_resolve_the_right_issue(self):
        from guard_module_scan import GuardModuleScan
        settings={'website':False,'api':{'paths':['/health'],'required_keys':['status']}}
        def wire(body):return b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
        with patch('guard_network._https_request_exchange',return_value=wire(b'{bad')):
            failed=GuardModuleScan(settings,min_gap=0)('https://example.com',max_requests=1)
        with patch('guard_network._https_request_exchange',return_value=wire(b'{"status":"ok"}')):
            passed=GuardModuleScan(settings,min_gap=0)('https://example.com',max_requests=1)
        self.assertEqual(failed.findings[0]['scope_kind'],'api:json-contract')
        self.assertIn(('api:json-contract','https://example.com/health'),passed.scope)
        self.assertEqual(passed.findings,())
