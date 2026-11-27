import ast
from pathlib import Path
import unittest
from unittest.mock import patch
from public_scan_workflow import secure_public_fetch,run_public_scan,public_wordpress_items,verified_wordpress_suggestions,_Budget
from website_scanner import fetch,scan,MAX_BYTES


def wire(body=b'<h1>Public content</h1>',status=200,kind=b'text/html'):
    return b'HTTP/1.1 '+str(status).encode()+b' Result\r\nContent-Type: '+kind+b'\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body


class PublicScanWorkflowTests(unittest.TestCase):
    def test_default_scanner_fetch_uses_existing_verified_transport_not_requests(self):
        with patch('public_scan_workflow._https_request_exchange',return_value=wire()) as exchange,patch('requests.request',side_effect=AssertionError('No ambient transport')):
            result=fetch('https://example.com/page','example.com')
        self.assertEqual(result,(200,'https://example.com/page','<h1>Public content</h1>'))
        self.assertEqual(exchange.call_args.args[:2],('example.com','/page'))
    def test_unsafe_targets_or_mutating_methods_are_blocked_before_transport(self):
        for url,method in [('http://example.com/','GET'),('https://127.0.0.1/','GET'),('https://other.example/','GET'),('https://user:secret@example.com/','GET'),('https://example.com/','POST')]:
            with patch('public_scan_workflow._https_request_exchange') as exchange,self.assertRaises(ValueError):secure_public_fetch(url,'example.com',method)
            exchange.assert_not_called()
    def test_default_scan_rejects_plain_http_before_dns_or_requests(self):
        with patch('socket.getaddrinfo',side_effect=AssertionError('No DNS')),patch('requests.request',side_effect=AssertionError('No request')),self.assertRaises(ValueError):scan('http://example.com/',1)
    def test_redirects_partial_and_oversized_responses_never_become_success(self):
        for response in (wire(status=301),wire(status=206),wire(body=b'x'*(MAX_BYTES+1))):
            with patch('public_scan_workflow._https_request_exchange',return_value=response),self.assertRaises(ValueError):secure_public_fetch('https://example.com/','example.com')
    def test_transport_error_details_do_not_escape(self):
        with patch('public_scan_workflow._https_request_exchange',side_effect=OSError('private connection detail')),self.assertRaises(ValueError) as caught:secure_public_fetch('https://example.com/','example.com')
        self.assertNotIn('private connection detail',str(caught.exception))
    def test_scan_composes_real_parser_context_and_broken_links_without_network(self):
        def exchange(host,path,*args,**kwargs):
            if path=='/missing':return wire(b'',404)
            return wire(b'<title>Guide</title><h1>Guide</h1><p>Installation steps for a public library.</p><a href="/missing">More</a>')
        with patch('monitoring_scan._https_request_exchange',side_effect=exchange) as network:
            result=run_public_scan('https://example.com/',1)
        self.assertTrue(result['complete']);self.assertEqual(len(result['broken']),1)
        self.assertEqual(result['checked'],1);self.assertEqual(network.call_count,2)
        self.assertIn('https://example.com/',result['contexts'])
    def test_wordpress_inventory_is_all_or_nothing_and_same_origin(self):
        with patch('public_scan_workflow.fetch_public_wordpress',side_effect=[[{'link':'https://example.com/a'}],ValueError('invalid')]):
            self.assertEqual(public_wordpress_items('example.com'),[])
        with patch('public_scan_workflow.fetch_public_wordpress',return_value=[{'link':'https://other.example/a'}]):
            self.assertEqual(public_wordpress_items('example.com'),[])
    def test_verified_candidates_remain_review_only_and_share_bounded_budget(self):
        item={'id':1,'status':'publish','link':'https://example.com/missing-fixed','title':{'rendered':'Missing fixed'},'slug':'missing-fixed'}
        budget=_Budget(max_requests=3,clock=lambda:0)
        with patch('public_scan_workflow._Budget',return_value=budget),patch('public_scan_workflow.fetch_public_wordpress',side_effect=[[item],[]]) as inventory,patch('public_scan_workflow.secure_public_fetch',return_value=(200,item['link'],'')) as probe:
            result=verified_wordpress_suggestions([{'link':'https://example.com/missing'}])
        self.assertEqual(inventory.call_count,2);self.assertEqual(probe.call_count,1)
        self.assertTrue(result[0]['verified']);self.assertTrue(result[0]['requires_review']);self.assertEqual(budget.remaining,0)
    def test_suggestion_budget_exhaustion_never_retries(self):
        budget=_Budget(max_requests=2,clock=lambda:0)
        item={'link':'https://example.com/missing-fixed','slug':'missing-fixed'}
        with patch('public_scan_workflow._Budget',return_value=budget),patch('public_scan_workflow.fetch_public_wordpress',side_effect=[[item],[]]),patch('public_scan_workflow.secure_public_fetch') as probe:
            self.assertEqual(verified_wordpress_suggestions([{'link':'https://example.com/missing'}]),[])
        probe.assert_not_called()
    def test_public_app_has_no_legacy_requests_call_or_raw_exception_display(self):
        tree=ast.parse(Path('app.py').read_text())
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='requests']
        self.assertEqual(calls,[])
        self.assertIn("result.get('complete') is False",Path('app.py').read_text())

    def test_shared_monitoring_reader_marks_redirects_incomplete_without_seo_claims(self):
        with patch('monitoring_scan._https_request_exchange',return_value=wire(status=301)) as exchange:
            result=run_public_scan('https://example.com/',1)
        self.assertFalse(result['complete']);self.assertEqual(result['rows'][0]['http_status'],'ERROR')
        self.assertEqual(exchange.call_count,1)
