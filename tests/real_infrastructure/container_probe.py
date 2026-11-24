"""Disposable named-volume proof only. Never run against an operator volume."""
import json
import os
from pathlib import Path
import sys
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
    assert auth.resolve(token).username=='restart-proof';auth.logout(token)
    directory=CustomerSites(auth,os.environ['FG_CUSTOMER_DATA_ROOT'],None)
    monitor=MonitoringService(directory,os.environ['FG_MONITOR_DB'])
    provider=SimulatedProvider();advisor=ContextualAdvisor(os.environ['FG_AI_LEDGER_DB'],provider)
    result=advisor.analyze(ROWS,CONTEXT,scope=SCOPE)
    assert result['status']=='model-assisted'
    assert provider.calls==(1 if phase=='seed' else 0)
    with advisor.db() as db:assert db.execute('SELECT SUM(calls) FROM advisor_budget').fetchone()[0]==1
    for path in (auth.path,advisor.path,Path(os.environ['FG_MONITOR_DB'])):
        assert Path(path).stat().st_mode&0o077==0
    print(json.dumps({'phase':phase,'nonroot':True,'accounts_recovered':True,'cached_selection_reused':phase!='seed',
                      'budget_preserved':True,'external_model_calls':0,'repairs_authorized':False}))


if __name__=='__main__':main(sys.argv[1])
