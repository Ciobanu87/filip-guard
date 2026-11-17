import unittest
from wordpress_http_headers import validate_request_headers

class HeaderSafetyTests(unittest.TestCase):
    def test_safe_headers(self):
        self.assertEqual(validate_request_headers([('User-Agent','FilipGuard-Test')]),(('User-Agent','FilipGuard-Test'),))
    def test_reject_auth_before_review(self):
        with self.assertRaises(ValueError):
            validate_request_headers([('Authorization','Basic secret')])
    def test_reject_injection(self):
        for name,value in [('User-Agent','ok\r\nHost: evil'),('User-Agent','ok\n'),('User-Agent','é'),('Bad\nName','ok')]:
            with self.subTest(name=name,value=value),self.assertRaises(ValueError):
                validate_request_headers([(name,value)])
    def test_reject_overrides(self):
        for name in ('Host','Connection','Content-Length','Transfer-Encoding','Cookie','Proxy-Authorization','Accept','Accept-Encoding','Authorization'):
            with self.subTest(name=name),self.assertRaises(ValueError):
                validate_request_headers([(name,'x')])
    def test_reject_duplicates(self):
        with self.assertRaises(ValueError):
            validate_request_headers([('User-Agent','a'),('user-agent','b')])
    def test_reject_invalid_shapes(self):
        for headers in (None,{},[('User-Agent',)], [('User-Agent',42)], [('User-Agent','a')]*21):
            with self.subTest(headers=str(headers)[:30]),self.assertRaises(ValueError):
                validate_request_headers(headers)
if __name__=='__main__':unittest.main()
