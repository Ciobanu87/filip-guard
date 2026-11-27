"""Opt-in Groq Free adapter; fixed DNS-pinned HTTPS, no SDK/ambient credentials.

The provider account MUST remain Free with no payment method/upgrade. Inference
responses cannot prove billing tier. The owner confirms that out of band; local
limits are an additional guard, never a billing guarantee for an upgraded account.
"""
import json
import re
import time
import socket
import ssl
from advisor_diagnostics import AdvisorFailure
from advisor_quota import quota_metadata
from advisor_credentials import credential_failure,valid_groq_key
from advisor_provider import ProviderUnavailable,strict_json
from wordpress_secure_https import create_verified_connection,parse_http_response

HOST='api.groq.com'
PATH='/openai/v1/chat/completions'
MODEL='qwen/qwen3.8-27b'


def framed_complete(raw):
    """Stop at a verified CL/chunked message boundary, not a peer idle timeout."""
    split=raw.find(b'\r\n\r\n')
    if split<0:return False
    header=raw[:split].lower();body=raw[split+4:]
    lengths=re.findall(rb'(?:^|\r\n)content-length:[ \t]*([0-9]+)[ \t]*(?=\r\n|$)',header)
    if lengths:
        if len(lengths)!=1 or len(lengths[0])>10:raise ValueError()
        size=int(lengths[0])
        if size>65536 or len(body)>size:raise ValueError()
        if len(body)==size:
            parse_http_response(bytes(raw));return True
    elif b'transfer-encoding:' in header and (body==b'0\r\n\r\n' or body.endswith(b'\r\n0\r\n\r\n')):
        parse_http_response(bytes(raw));return True
    return False


def cloud_exchange(body,key,timeout):
    """Credentials go only to a fixed verified public host; no redirects/retries."""
    if type(body) is not bytes or len(body)>32768 or not 1<=timeout<=20:raise ValueError('Bounded cloud request required')
    if type(key) is not str or not re.fullmatch(r'gsk_[A-Za-z0-9_-]{16,200}',key):raise ValueError('Explicit Groq key required')
    deadline=time.monotonic()+timeout;connection=None;stage='connect';status_hint=None
    try:
        connection=create_verified_connection(HOST,timeout=timeout)
        def remaining():
            duration=deadline-time.monotonic()
            if duration<=0:raise TimeoutError()
            connection.settimeout(duration)
        remaining();stage='send'
        head=('POST '+PATH+' HTTP/1.1\r\nHost: '+HOST+'\r\nAuthorization: Bearer '+key+
            '\r\nContent-Type: application/json\r\nAccept: application/json\r\nAccept-Encoding: identity\r\nConnection: close\r\nContent-Length: '+str(len(body))+'\r\n\r\n')
        connection.sendall(head.encode('ascii')+body)
        raw=bytearray();stage='read'
        while True:
            remaining();chunk=connection.recv(min(4096,98305-len(raw)))
            if not chunk:break
            raw.extend(chunk)
            if len(raw)>98304:raise ValueError()
            hint=re.match(rb'HTTP/1\.[01] ([2-5][0-9]{2}) ',raw)
            if hint:status_hint=int(hint[1])
            if framed_complete(raw):break
            if b'\r\n\r\n' not in raw and len(raw)>16384:raise ValueError()
        stage='http';response=parse_http_response(bytes(raw))
        if response.status!=200:
            error={}
            try:
                envelope=strict_json(response.body.decode('utf-8'))
                if type(envelope) is dict and type(envelope.get('error')) is dict:error=envelope['error']
            except Exception:pass
            raise AdvisorFailure('http_error','http',http_status=response.status,provider_code=error.get('code'),provider_type=error.get('type'),quota=quota_metadata(response.headers,error,now=time.time()))
        types=[v.lower().split(';')[0].strip() for k,v in response.headers if k=='content-type']
        if types!=['application/json'] or len(response.body)>65536:raise ValueError()
        stage='json';payload=strict_json(response.body.decode('utf-8'))
        if type(payload) is dict:payload['_fg_quota']=quota_metadata(response.headers,now=time.time())
        return payload
    except AdvisorFailure:raise
    except (TimeoutError,socket.timeout):raise AdvisorFailure('timeout',stage) from None
    except ssl.SSLError:raise AdvisorFailure('tls_failed',stage) from None
    except OSError:raise AdvisorFailure('network_failed',stage) from None
    except Exception:raise AdvisorFailure('invalid_json' if stage=='json' else 'invalid_http',stage,http_status=status_hint) from None
    finally:
        key=None
        if connection is not None:connection.close()


def build_payload(messages,schema,*,model=MODEL,max_output_tokens=1200):
    content_bytes=sum(len(m['content'].encode('utf-8')) for m in messages)
    schema_bytes=len(json.dumps(schema,separators=(',',':'),ensure_ascii=False).encode())
    if content_bytes+schema_bytes>6000:raise AdvisorFailure('input_bound','input')
    payload={'model':model,'messages':messages,'stream':False,'temperature':0,
        'reasoning_effort':'none','reasoning_format':'hidden','max_completion_tokens':max_output_tokens,
        'response_format':{'type':'json_schema','json_schema':{'name':'filip_guard_advice','strict':True,'schema':schema}}}
    body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
    metrics={'request_bytes':len(body),'prompt_and_schema_bytes':content_bytes+schema_bytes,
        'estimated_input_tokens_heuristic':(content_bytes+schema_bytes+3)//4,'max_output_tokens':max_output_tokens,
        'token_estimate_method':'UTF-8 bytes / 4 heuristic; not provider accounting'}
    return body,metrics


class GroqFreeProvider:
    name='groq-free'
    legacy_quota_recovery=True
    selection_contract='indexed-evidence-v3'
    minimum_interval=61
    def __init__(self,key_provider,*,model=MODEL,free_plan_confirmed=False,data_consent=False):
        if model!=MODEL or not callable(key_provider):raise ValueError('Reviewed cloud model and explicit key provider required')
        if free_plan_confirmed is not True or data_consent is not True:
            raise ValueError('Free organization and sanitized-data transfer must be explicitly confirmed')
        self.model=model;self.keys=key_provider;self.successful_exchanges=0;self.last_usage=None;self.last_diagnostic=None;self.attempted_exchanges=0;self.last_request_metrics=None;self.last_quota=None
    def check_ready(self):
        try:valid_groq_key(self.keys())
        except Exception as error:raise credential_failure(error) from None

    def generate(self,messages,schema,*,timeout=15,max_output_tokens=1200):
        if not 1<=timeout<=20 or not 64<=max_output_tokens<=1600:raise ValueError('Bounded inference required')
        body,self.last_request_metrics=build_payload(messages,schema,model=self.model,max_output_tokens=max_output_tokens)
        self.last_diagnostic=None;self.last_usage=None;self.last_quota=None
        try:
            try:key=valid_groq_key(self.keys())
            except Exception as error:raise credential_failure(error) from None
            try:
                self.attempted_exchanges+=1
                result=cloud_exchange(body,key,timeout)
            finally:key=None
            if type(result) is not dict or result.get('model')!=self.model:raise AdvisorFailure('model_identity','provider',http_status=200)
            choices=result.get('choices');usage=result.get('usage')
            if type(choices) is not list or len(choices)!=1 or type(choices[0]) is not dict or choices[0].get('finish_reason')!='stop':raise AdvisorFailure('completion_incomplete','provider',http_status=200)
            message=choices[0].get('message')
            if (type(message) is not dict or message.get('role')!='assistant' or message.get('tool_calls')
                    or message.get('function_call') or message.get('refusal') or type(message.get('content')) is not str):raise AdvisorFailure('unsafe_message','provider',http_status=200)
            if type(usage) is not dict or any(type(usage.get(k)) is not int for k in ('prompt_tokens','completion_tokens','total_tokens')):raise AdvisorFailure('usage_rejected','provider',http_status=200)
            if not 0<usage['completion_tokens']<=max_output_tokens or not 0<usage['prompt_tokens']<=8192 or usage['total_tokens']!=usage['prompt_tokens']+usage['completion_tokens']:raise AdvisorFailure('usage_rejected','provider',http_status=200)
            payload=strict_json(message['content'])
            self.last_quota=result.get('_fg_quota',{})
            self.last_diagnostic={'stage':'provider','code':'ok','http_status':200}
            self.successful_exchanges+=1;self.last_usage={k:usage[k] for k in ('prompt_tokens','completion_tokens','total_tokens')}
            return payload
        except AdvisorFailure as error:
            self.last_diagnostic=error.diagnostic;raise
        except Exception:
            error=AdvisorFailure('response_rejected','provider',http_status=200);self.last_diagnostic=error.diagnostic;raise error from None
