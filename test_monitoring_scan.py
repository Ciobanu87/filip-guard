import socket
import unittest
from unittest.mock import Mock,patch
from monitoring_scan import SecureMonitoringScan,target_url,MonitoringCancelled,make_report


def wire(body,status=200,extra=b''):
    body=body.encode()
    return (f'HTTP/1.1 {status} Result\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {len(body)}\r\n'.encode()+extra+b'\r\n'+body)


class MonitoringScanTests(unittest.TestCase):
    def scan(self,responses,**kwargs):
        connections=[]
        def connection(*args,**kw):
            obj=Mock();obj.recv.side_effect=[responses.pop(0),b''];connections.append(obj);return obj
        with patch('wordpress_secure_https.create_verified_connection',side_effect=connection):
            report=SecureMonitoringScan(min_gap=0)('https://example.com',**kwargs)
        self.assertTrue(all(obj.close.call_count==1 for obj in connections))
        return report,connections

    def test_existing_scanner_advisor_detect_seo_http_and_broken_links(self):
        report,connections=self.scan([wire('<title>Home</title><h1>Home</h1><a href="/missing">missing</a>'),
            wire('not found',404)],page_limit=1,max_requests=3)
        self.assertTrue(report.complete)
        self.assertTrue(any(f['problem']=='Missing meta description' for f in report.findings))
        self.assertTrue(any(f['problem']=='Broken internal link' for f in report.findings))
        self.assertTrue(all(f['autofix'] is False for f in report.findings))
        self.assertEqual(report.requests,2)
        for obj in connections:
            request=obj.sendall.call_args.args[0]
            self.assertTrue(request.startswith(b'GET '));self.assertNotIn(b'Authorization:',request)
            self.assertIn(b'Accept: text/html,application/xhtml+xml',request)

    def test_private_and_external_urls_blocked_before_connection(self):
        for url in ('http://example.com','https://127.0.0.1','https://169.254.169.254',
            'https://localhost','https://user:secret@example.com','https://example.com:444','https://example.com/\r\n'):
            with self.subTest(url=url),patch('wordpress_secure_https.create_verified_connection') as connect:
                with self.assertRaises(ValueError):SecureMonitoringScan(min_gap=0)(url,page_limit=1,max_requests=1)
                connect.assert_not_called()
        with self.assertRaises(ValueError):target_url('https://other.example/','example.com')

    def test_redirect_never_followed_and_cannot_resolve_old_findings(self):
        report,connections=self.scan([wire('',302,b'Location: https://127.0.0.1/private\r\n')],page_limit=1,max_requests=1)
        self.assertFalse(report.complete);self.assertEqual(len(connections),1)
        self.assertEqual(report.scope,())

    def test_mixed_public_private_dns_never_reaches_tls(self):
        answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),
                 (socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('wordpress_dns_deadline.getaddrinfo_with_deadline',return_value=answers), \
             patch('wordpress_https_deadline.connect_pinned_addresses') as connect:
            report=SecureMonitoringScan(min_gap=0)('https://example.com',page_limit=1,max_requests=1)
            self.assertFalse(report.complete);connect.assert_not_called()

    def test_verified_dns_is_pinned_once_per_uncached_request(self):
        answers=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        connection=Mock();connection.recv.side_effect=[wire('<title>Good</title><h1>Good</h1>'),b'']
        with patch('wordpress_dns_deadline.getaddrinfo_with_deadline',return_value=answers) as resolve, \
             patch('wordpress_https_deadline.connect_pinned_addresses',return_value=connection) as connect:
            report=SecureMonitoringScan(min_gap=0)('https://example.com',page_limit=1,max_requests=1)
        self.assertTrue(report.complete);resolve.assert_called_once()
        self.assertEqual(connect.call_args.args[:2],('example.com',['93.184.216.34']))

    def test_request_budget_and_cached_link_checks_bound_load(self):
        body='<title>Home</title><h1>Home</h1>'+''.join(f'<a href="/{i}">link</a>' for i in range(500))
        responses=[wire(body),wire('<title>Other</title><h1>Other</h1>')]
        report,connections=self.scan(responses,page_limit=2,max_requests=2)
        self.assertEqual(report.requests,2);self.assertEqual(len(connections),2)

    def test_network_failures_are_incomplete_not_evidence_of_resolution(self):
        with patch('wordpress_secure_https.create_verified_connection',side_effect=TimeoutError('private detail')):
            report=SecureMonitoringScan(min_gap=0)('https://example.com',page_limit=1,max_requests=1)
        self.assertFalse(report.complete);self.assertEqual(report.findings,());self.assertEqual(report.scope,())
        self.assertNotIn('private detail',repr(report))

    def test_cancelled_scan_never_opens_connection(self):
        def cancel():raise MonitoringCancelled('Disabled')
        with patch('wordpress_secure_https.create_verified_connection') as connect:
            with self.assertRaises(MonitoringCancelled):
                SecureMonitoringScan(min_gap=0)('https://example.com',page_limit=1,max_requests=1,checkpoint=cancel)
            connect.assert_not_called()

    def test_truncated_response_is_not_accepted(self):
        report,_=self.scan([wire('<title>Home</title>')[:-3]],page_limit=1,max_requests=1)
        self.assertFalse(report.complete)

    def test_report_scope_does_not_assume_disappeared_pages_are_fixed(self):
        report=make_report([dict(page='https://example.com',http_status=200,title='Good',meta_description='Good',
            h1_count=1,images_missing_alt=0)],[],[],1)
        self.assertNotIn(('seo','https://example.com/old'),report.scope)
        self.assertIn(('seo','https://example.com'),report.scope)
