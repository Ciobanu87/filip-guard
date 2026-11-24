"""Real local HTTP framing/timeouts with a simulated Ollama protocol server.

No model weights, inference, external credentials or paid service are used.
"""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import http.client
import json
import threading
import time
import unittest
from unittest.mock import patch
from advisor_provider import OllamaProvider,ProviderUnavailable

class LocalModelProtocolTests(unittest.TestCase):
    def serve(self,mode='normal'):
        test=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):self.reply({'models':[{'name':'qwen3:8b'}]})
            def do_POST(self):
                test.request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if mode=='body-drip':
                    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length','100');self.end_headers()
                    try:
                        for byte in b'{'+b' '*99:
                            self.connection.sendall(bytes([byte]));time.sleep(.1)
                    except OSError:pass
                    return
                if mode=='header-drip':
                    try:
                        for byte in b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n':
                            self.connection.sendall(bytes([byte]));time.sleep(.1)
                    except OSError:pass
                    return
                payload={'model':'qwen3:8b','done':True,'done_reason':'stop','eval_count':20,
                    'message':{'role':'assistant','content':'{"recommendations":[]}'}}
                self.reply(payload)
            def reply(self,payload):
                body=json.dumps(payload).encode()
                self.send_response(302 if mode=='redirect' else 200);self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)+(10 if mode=='truncated' else 0)));self.end_headers()
                try:self.wfile.write(body)
                except OSError:pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.daemon_threads=True
        thread=threading.Thread(target=lambda:server.serve_forever(poll_interval=.02),daemon=True);thread.start()
        self.addCleanup(lambda:(server.shutdown(),server.server_close(),thread.join(timeout=1)))
        original=http.client.HTTPConnection
        def connection(host,port,**kwargs):
            self.assertEqual((host,port),('127.0.0.1',11434))
            return original(host,server.server_port,**kwargs)
        patcher=patch('advisor_provider.http.client.HTTPConnection',side_effect=connection);patcher.start();self.addCleanup(patcher.stop)
    def test_actual_http_payload_is_bounded_local_and_tool_free(self):
        self.serve();self.assertEqual(OllamaProvider().generate([],{},timeout=2),{'recommendations':[]})
        self.assertFalse(self.request['stream']);self.assertNotIn('tools',self.request)
    def test_slow_headers_have_a_hard_total_deadline(self):
        self.serve('header-drip');began=time.monotonic()
        with self.assertRaises(ProviderUnavailable):OllamaProvider().generate([],{},timeout=1)
        self.assertLess(time.monotonic()-began,2.5)
    def test_truncated_declared_body_is_rejected_even_when_json_is_complete(self):
        self.serve('truncated')
        with self.assertRaises(ProviderUnavailable):OllamaProvider().generate([],{},timeout=2)
    def test_redirect_never_followed(self):
        self.serve('redirect')
        with self.assertRaises(ProviderUnavailable):OllamaProvider().generate([],{},timeout=2)

    def test_slow_response_body_also_obeys_total_deadline(self):
        self.serve('body-drip');began=time.monotonic()
        with self.assertRaises(ProviderUnavailable):OllamaProvider().generate([],{},timeout=1)
        self.assertLess(time.monotonic()-began,2.5)
