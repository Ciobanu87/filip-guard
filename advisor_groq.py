"""Opt-in Groq Free adapter; fixed DNS-pinned HTTPS, no SDK/ambient credentials.

The provider account MUST remain Free with no payment method/upgrade. Inference
responses cannot prove billing tier. The owner confirms that out of band; local
limits are an additional guard, never a billing guarantee for an upgraded account.
"""
import json
import re
import time
from advisor_provider import ProviderUnavailable,strict_json
from wordpress_secure_https import create_verified_connection,parse_http_response

HOST='api.groq.com'
PATH='/openai/v1/chat/completions'
MODEL='qwen/qwen3.8-27b'


def cloud_exchange(body,key,timeout):
    """Credentials go only to a fixed verified public host; no redirects/retries."""
    if type(body) is not bytes or len(body)>32768 or not 1<=timeout<=20:raise ValueError('Bounded cloud request required')
    if type(key) is not str or not re.fullmatch(r'gsk_[A-Za-z0-9_-]{16,200}',key):raise ValueError('Explicit Groq key required')
    deadline=time.monotonic()+timeout;connection=None
    try:
        connection=create_verified_connection(HOST,timeout=timeout)
        def remaining():
            duration=deadline-time.monotonic()
            if duration<=0:raise TimeoutError()
            connection.settimeout(duration)
        remaining()
        head=('POST '+PATH+' HTTP/1.1\r\nHost: '+HOST+'\r\nAuthorization: Bearer '+key+
            '\r\nContent-Type: application/json\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\nContent-Length: '+str(len(body))+'\r\n\r\n')
        connection.sendall(head.encode('ascii')+body)
        raw=bytearray()
        while True:
            remaining();chunk=connection.recv(min(4096,98305-len(raw)))
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>98304:raise ValueError()
            if b'\r\n\r\n' not in raw and len(raw)>16384:raise ValueError()
        response=parse_http_response(bytes(raw))
        if response.status!=200:raise ValueError()  # 401/403/429/5xx all fail closed, no retries.
        types=[v.lower().split(';')[0].strip() for k,v in response.headers if k=='content-type']
        if types!=['application/json'] or len(response.body)>65536:raise ValueError()
        return strict_json(response.body.decode('utf-8'))
    except Exception:raise ProviderUnavailable('Cloud inference unavailable or invalid; rules retained') from None
    finally:
        key=None
        if connection is not None:connection.close()


class GroqFreeProvider:
    name='groq-free'
    def __init__(self,key_provider,*,model=MODEL,free_plan_confirmed=False,data_consent=False):
        if model!=MODEL or not callable(key_provider):raise ValueError('Reviewed cloud model and explicit key provider required')
        if free_plan_confirmed is not True or data_consent is not True:
            raise ValueError('Free organization and sanitized-data transfer must be explicitly confirmed')
        self.model=model;self.keys=key_provider
    def generate(self,messages,schema,*,timeout=15,max_output_tokens=1200):
        if not 1<=timeout<=20 or not 64<=max_output_tokens<=1600:raise ValueError('Bounded inference required')
        # Schema constraints still undergo full independent semantic validation.
        body=json.dumps({'model':self.model,'messages':messages,'stream':False,'temperature':0,
            'reasoning_effort':'none','reasoning_format':'hidden','max_completion_tokens':max_output_tokens,
            'response_format':{'type':'json_schema','json_schema':{'name':'filip_guard_advice','strict':True,'schema':schema}}},ensure_ascii=False).encode()
        try:
            result=cloud_exchange(body,self.keys(),timeout)
            if type(result) is not dict or result.get('model')!=self.model:raise ValueError()
            choices=result.get('choices');usage=result.get('usage')
            if type(choices) is not list or len(choices)!=1 or type(choices[0]) is not dict or choices[0].get('finish_reason')!='stop':raise ValueError()
            message=choices[0].get('message')
            if (type(message) is not dict or message.get('role')!='assistant' or message.get('tool_calls')
                    or message.get('function_call') or message.get('refusal') or type(message.get('content')) is not str):raise ValueError()
            if type(usage) is not dict or any(type(usage.get(k)) is not int for k in ('prompt_tokens','completion_tokens','total_tokens')):raise ValueError()
            if not 0<usage['completion_tokens']<=max_output_tokens or not 0<usage['prompt_tokens']<=8192 or usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']:raise ValueError()
            return strict_json(message['content'])
        except Exception:raise ProviderUnavailable('Cloud response rejected; rules retained') from None
