"""Phone-only one-cell loader; existing Colab history/key, one NEW UI probe.

No cloud-browser login, runtime reset, accepted-case rerun, billing or repair.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

REVISION = 'f03d20ad6c7b9ab9454c82971ac5c8b12d7244fc'


def require_completed_quality(advisor):
    from advisor_quality_evaluation import quality_cases,_completed_fixtures
    cases=quality_cases();completed=_completed_fixtures(advisor,cases)
    if set(completed)!={case['name'] for case in cases}:
        raise RuntimeError('Cele nouă rezultate acceptate nu sunt toate disponibile. Oprire fără apel nou.')
    return len(completed)


def session_credential(namespace,secret_reader):
    from advisor_credentials import SessionCredential
    previous=namespace.get('credential')
    if callable(previous):
        try:return SessionCredential(previous())
        except Exception:pass
    return SessionCredential.load(secret_reader)


def run(namespace):
    os.umask(0o077)
    candidate=namespace.get('ledger')
    if candidate is None:candidate=getattr(namespace.get('advisor'),'path',None)
    ledger=Path(candidate or '/content/filip-guard-cloud-validation-state/ledger.sqlite')
    if not ledger.is_file():raise RuntimeError('Istoricul existent lipsește. Nu se creează un buget nou.')
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro',uri=True) as db:
        db.execute('SELECT count(*) FROM advisor_requests').fetchone()
    checkout=Path('/content/filip-guard-ai-validation-'+REVISION[:12])
    if not checkout.exists():
        subprocess.run(['git','clone','--single-branch','--branch','filip-guard-development',
                        'https://github.com/Ciobanu87/filip-guard.git',str(checkout)],check=True,capture_output=True)
        subprocess.run(['git','checkout','--detach',REVISION],cwd=checkout,check=True,capture_output=True)
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=checkout,text=True).strip()!=REVISION:
        raise RuntimeError('Versiunea verificată nu este disponibilă; niciun apel AI.')
    # Streamlit AppTest runs in this existing CPU runtime; no external server.
    subprocess.run([sys.executable,'-m','pip','install','-q','-r',str(checkout/'requirements.txt')],check=True,capture_output=True)
    for name,module in list(sys.modules.items()):
        origin=getattr(module,'__file__',None)
        if isinstance(origin,str) and origin.startswith('/content/filip-guard-ai-validation'):
            del sys.modules[name]
    sys.path[:]=[p for p in sys.path if not str(p).startswith('/content/filip-guard-ai-validation')]
    sys.path.insert(0,str(checkout))
    from advisor_groq import GroqFreeProvider
    from contextual_advisor import ContextualAdvisor
    from advisor_diagnostics import AdvisorFailure
    from validate_app_ai import validate_authenticated_ui,prior_success
    from google.colab import userdata,files
    provider=GroqFreeProvider(lambda:None,free_plan_confirmed=True,data_consent=True)
    advisor=ContextualAdvisor(ledger,provider,daily_calls=20,timeout=20,max_output_tokens=256)
    completed=require_completed_quality(advisor)
    receipt=ledger.parent/'app-live-ai-v1.receipt.json'
    report=prior_success(receipt,model=provider.model)
    if report is None:
        print('Cele',completed,'cazuri acceptate sunt păstrate. Urmează cel mult un apel NOU, prin interfața aplicației.')
        try:credential=session_credential(namespace,lambda:userdata.get('GROQ_API_KEY'))
        except AdvisorFailure as error:
            print('Acces secret:',error.diagnostic['code'])
            raise RuntimeError('Cheia nu este disponibilă; niciun apel Groq.') from None
        provider.keys=credential
        try:report=validate_authenticated_ui(advisor,live=True)
        finally:credential.close()
        report['model']=provider.model;report['repository_revision']=REVISION
        if report['accepted'] and report['real_inference_executed']:
            fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as output:
                json.dump(report,output,ensure_ascii=False,indent=2);output.flush();os.fsync(output.fileno())
    else:print('Proba aplicației este deja validată; zero apeluri noi.')
    report['execution_revision']=REVISION;report['accepted_quality_cases_preserved']=completed
    destination=ledger.parent/('app-ai-validation-'+uuid.uuid4().hex+'.json')
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as output:json.dump(report,output,ensure_ascii=False,indent=2)
    namespace['app_ai_report']=report;namespace['app_ai_report_path']=destination
    print(json.dumps({key:report.get(key) for key in ('accepted','real_inference_executed','new_provider_responses','status','diagnostic','ui_error')},ensure_ascii=False))
    print('Raport:',str(destination));files.download(str(destination))
    return report


if __name__=='__main__':run(globals())
