"""Shared provider interface and existing opt-in local adapter; no auto activation.

Groq transport/credentials live in advisor_groq. Runtime selection is explicit.
"""
import http.client
import json
import re
import socket
import threading
import time
from typing import Protocol

class AdvisorProvider(Protocol):
    name:str
    model:str
    def generate(self,messages,schema,*,timeout,max_output_tokens):...

class ProviderUnavailable(RuntimeError):pass

def strict_json(value):
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:raise ValueError('Duplicate JSON field')
            result[k]=v
        return result
    return json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))

class OllamaProvider:
    name='ollama-local'
    def __init__(self,model='qwen3:8b'):
        # Explicit local models only. No cloud model names, URL routing or pulls.
        if not re.fullmatch(r'(qwen3:(?:0\.6b|1\.7b|4b|8b)|llama3\.2:(?:1b|3b))',model):
            raise ValueError('Explicit supported locally installed model required')
        self.model=model
    def _exchange(self,path,body,deadline):
        connection=http.client.HTTPConnection('127.0.0.1',11434,timeout=max(.01,deadline-time.monotonic()))
        expired=threading.Event();active=[None]
        def interrupt():
            expired.set()
            sock=connection.sock or active[0]
            if sock:
                try:sock.shutdown(socket.SHUT_RDWR)
                except OSError:pass
            connection.close()
        timer=threading.Timer(max(.01,deadline-time.monotonic()),interrupt);timer.daemon=True;timer.start()
        try:
            connection.connect();active[0]=connection.sock
            if expired.is_set():raise TimeoutError()
            connection.request('POST' if body is not None else 'GET',path,body=body,
                headers={'Content-Type':'application/json','Connection':'close'})
            response=connection.getresponse()
            if response.status!=200 or response.getheader('Content-Type','').split(';')[0]!='application/json':raise ValueError()
            chunks=[];size=0
            while True:
                if response.isclosed():break
                remaining=deadline-time.monotonic()
                if expired.is_set() or remaining<=0:raise TimeoutError()
                if active[0]:active[0].settimeout(remaining)
                chunk=response.read1(4096)
                if not chunk:break
                size+=len(chunk)
                if size>65536:raise ValueError()
                chunks.append(chunk)
            if expired.is_set():raise TimeoutError()
            lengths=response.headers.get_all('Content-Length',[])
            if len(lengths)>1 or (lengths and (not lengths[0].isdigit() or int(lengths[0])!=size)):raise ValueError()
            return strict_json(b''.join(chunks).decode('utf-8'))
        except Exception:raise ProviderUnavailable('Local model exchange unavailable or invalid') from None
        finally:timer.cancel();connection.close()
    def generate(self,messages,schema,*,timeout=15,max_output_tokens=1200):
        if not 1<=timeout<=20 or not 64<=max_output_tokens<=1600:raise ValueError('Model request limits required')
        deadline=time.monotonic()+timeout
        tags=self._exchange('/api/tags',None,deadline)
        if type(tags) is not dict or self.model not in [m.get('name') for m in tags.get('models',[]) if type(m) is dict]:
            raise ProviderUnavailable('Authorized model is not installed locally')
        body=json.dumps({'model':self.model,'messages':messages,'format':schema,'stream':False,'think':False,
            'keep_alive':0,'options':{'temperature':0,'num_ctx':8192,'num_predict':max_output_tokens}}).encode()
        if len(body)>32768:raise ValueError('Model context exceeds safe bound')
        result=self._exchange('/api/chat',body,deadline)
        if (type(result) is not dict or result.get('done') is not True or result.get('done_reason')!='stop'
                or result.get('model')!=self.model or type(result.get('eval_count')) is not int
                or not 0<result['eval_count']<=max_output_tokens or type(result.get('message')) is not dict
                or result['message'].get('role')!='assistant' or result['message'].get('tool_calls')):
            raise ProviderUnavailable('Incomplete or unsafe local model result')
        content=result['message'].get('content')
        if type(content) is not str or len(content)>24000:raise ProviderUnavailable('Invalid model content')
        return strict_json(content)
