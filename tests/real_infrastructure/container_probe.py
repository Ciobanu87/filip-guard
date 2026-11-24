"""Disposable named-volume proof only. Never run against an operator volume."""
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from monitoring_service import MonitoringService
from contextual_advisor import ContextualAdvisor
from test_contextual_advisor import SimulatedProvider,ROWS,CONTEXT,SCOPE


def main(phase):
    if os.environ.get('FG_DISPOSABLE_VOLUME_PROOF')!='1':raise PermissionError('Disposable proof volume required')
    root=Path('/var/lib/filip-guard')
    assert os.getuid()==10001 and root.stat().st_mode&0o077==0
    auth=CustomerAuth(os.environ['FG_CUSTOMER_AUTH_DB'])
    if phase=='seed':auth.register('restart-proof','Synthetic-persistence-password')
    token=auth.login('restart-proof','Synthetic-persistence-password')
    principal=auth.resolve(token)
    assert principal.username=='restart-proof'
    directory=CustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],None)
    def synthetic_scan(origin,*,before_request,checkpoint,**kwargs):
        from monitoring_scan import make_report
        checkpoint();before_request()
        rows=[dict(page=origin,http_status=200,title='Fixture',meta_description='',h1_count=1,images_missing_alt=0)]
        return make_report(rows,[],[],1,True)
    monitor=MonitoringService(directory,os.environ['FG_MONITOR_DB'],scanner=synthetic_scan)
    site_id='a'*32
    if phase=='seed':
        # Synthetic ownership metadata only; no real WordPress credentials/site.
        with directory.db() as db:
            db.execute('INSERT INTO customer_sites VALUES (?,?,?,7,?,?,?)',
                (site_id,principal.customer_id,'https://persistence.example.test','fixture-only',b'not-decrypted',time.time()))
        monitor.configure(token,site_id,enabled=True,interval_seconds=900,page_limit=1,max_requests=3)
        assert monitor.run_once()['status']=='complete'
    assert monitor.history(token,site_id) and monitor.notifications(token)
    auth.logout(token)
    provider=SimulatedProvider();advisor=ContextualAdvisor(os.environ['FG_AI_LEDGER_DB'],provider)
    result=advisor.analyze(ROWS,CONTEXT,scope=SCOPE)
    assert result['status']=='model-assisted'
    assert provider.calls==(1 if phase=='seed' else 0)
    with advisor.db() as db:assert db.execute('SELECT SUM(calls) FROM advisor_budget').fetchone()[0]==1
    for path in (auth.path,advisor.path,Path(os.environ['FG_MONITOR_DB'])):
        assert Path(path).stat().st_mode&0o077==0
    print(json.dumps({'phase':phase,'nonroot':True,'accounts_recovered':True,'cached_selection_reused':phase!='seed',
                      'budget_preserved':True,'monitoring_history_recovered':True,'notifications_recovered':True,'external_model_calls':0,'repairs_authorized':False}))


if __name__=='__main__':main(sys.argv[1])
