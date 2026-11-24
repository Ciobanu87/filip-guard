"""One bounded authenticated Streamlit -> real Groq integration probe.

Synthetic WordPress/storage fixture, real application UI/account/scan/advice path.
No repair buttons are clicked. Existing nine-case model evaluation is not rerun.
Owner-key live execution remains opt-in; offline tests cannot claim live inference.
"""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

CASE_ID='authenticated-streamlit-ai-v1'
REQUIRED_UI_CHECKS={'cross_account_inference_denied','ui_login_verified','scanner_visible',
    'guarded_model_selection_accepted','model_source_visible','grounded_evidence_visible','review_guidance_visible',
    'no_repair_authority','romanian_render_visible','only_one_ui_inference_invocation',
    'saved_advice_after_login','no_wordpress_change','no_apply_button_exposed'}
PAGE_CONTEXT='Maintenance guide: review published page metadata after a verified WordPress restoration.'


def validate_authenticated_ui(advisor,*,live=False):
    from advisor_groq import GroqFreeProvider
    if live and type(advisor.provider) is not GroqFreeProvider:
        raise ValueError('Reviewed Groq provider required for live UI validation')
    from streamlit.testing.v1 import AppTest
    import test_guard_application as fixture
    from monitoring_scan import make_report
    f=fixture.UnifiedFlowTests();f.setUp()
    provider=advisor.provider
    attempts=lambda:getattr(provider,'attempted_exchanges',getattr(provider,'calls',0))
    responses=lambda:getattr(provider,'successful_exchanges',getattr(provider,'calls',0))
    before_attempts,before_responses=attempts(),responses()
    report={'case':CASE_ID,'mode':'live-cloud' if live else 'simulated-contract',
            'wordpress':'local-simulator','external_storage':'simulated','production_enabled':False,
            'real_inference_executed':False,'new_provider_responses':0,'provider_request_attempted':False,
            'accepted':False,'quality_validated':False,'checks':{},'diagnostic':None}
    class OneInvocation:
        used=False
        last=None
        def analyze(self,*args,**kwargs):
            if self.used:raise PermissionError('One UI inference invocation only; no automatic retry')
            self.used=True;self.last=advisor.analyze(*args,**kwargs);return self.last
    once=OneInvocation();original_scan=f.application.scanner
    def scan(origin,**kwargs):
        scanned=original_scan(origin,**kwargs)
        rows=[{**row,'meta_description':''} for row in scanned.rows]
        return make_report(rows,scanned.broken,[],scanned.requests,
            link_sources={origin+'/missing-destination/':{origin+'/source/'}},
            page_context={row['page']:[PAGE_CONTEXT] for row in rows})
    f.application.scanner=scan
    try:
        # Backend ownership checks must reject an unrelated account before AI.
        seeded=f.application.scan(f.a,f.site_a,start_url=f.origins[0]+'/source/',page_limit=1)
        try:f.application.advice(f.b,f.site_a,seeded['scan_id'],generate=True,advisor=once)
        except PermissionError:report['checks']['cross_account_inference_denied']=not once.used
        else:raise ValueError('Ownership validation failed')
        with patch('guard_application_ui.configured_guard_application',return_value=f.application),patch('contextual_advisor.configured_advisor',return_value=once):
            at=AppTest.from_file(str(Path(__file__).with_name('app.py')),default_timeout=60).run()
            def rerun():
                at.run()
                if list(at.exception):raise ValueError('Application UI execution failed')
            next(x for x in at.text_input if x.label=='Account username').set_value('alice')
            next(x for x in at.text_input if x.label=='Account password').set_value('Alice-unified-password')
            next(x for x in at.button if x.label=='Sign in').click();rerun()
            token=at.session_state['fg_customer_session'];f.auth.resolve(token)
            report['checks']['ui_login_verified']=True
            next(x for x in at.selectbox if x.label=='Page to scan').set_value(f.origins[0]+'/source/')
            next(x for x in at.button if x.label=='Scan authorized site').click();rerun()
            report['checks']['scanner_visible']=bool(at.dataframe)
            snapshot=f.sites.read_resource(token,f.site_a,'post',1)
            next(x for x in at.button if x.label=='Analyze context with AI').click();rerun()
            result=once.last
            if result is None:raise ValueError('UI did not invoke Advisor')
            report['status']=result['status'];report['diagnostic']=result.get('diagnostic');report['cooldown']=result.get('cooldown')
            items=result['recommendations'];accepted=result['status']=='model-assisted'
            report['checks']['guarded_model_selection_accepted']=accepted
            report['checks']['model_source_visible']=accepted and any('model-assisted' in x.value for x in at.caption)
            report['checks']['grounded_evidence_visible']=accepted and any(PAGE_CONTEXT in x.value for x in at.text)
            report['checks']['review_guidance_visible']=any('Verify the missing' in x.value for x in at.text)
            report['checks']['no_repair_authority']=all(item['autofix'] is False and item['repair_supported'] is False for item in items)
            next(x for x in at.selectbox if x.label=='Advisor language').set_value('ro');rerun()
            report['checks']['romanian_render_visible']=any('Verifică în HTML' in x.value for x in at.text)
            report['checks']['only_one_ui_inference_invocation']=once.used and attempts()-before_attempts<=1
            next(x for x in at.button if x.label=='Sign out').click();rerun()
            next(x for x in at.text_input if x.label=='Account username').set_value('alice')
            next(x for x in at.text_input if x.label=='Account password').set_value('Alice-unified-password')
            next(x for x in at.button if x.label=='Sign in').click();rerun()
            report['checks']['saved_advice_after_login']=any(PAGE_CONTEXT in x.value for x in at.text)
            new_token=at.session_state['fg_customer_session']
            after=f.sites.read_resource(new_token,f.site_a,'post',1)
            report['checks']['no_wordpress_change']=snapshot==after and f.application.history(new_token,f.site_a)==[]
            report['checks']['no_apply_button_exposed']=not any(x.label=='Approve and apply test change' for x in at.button)
            report['selection_sample']=[{'problem':item['problem'],'evidence':item['evidence'],'source':item['source'],'model':item['model']} for item in items]
            report['accepted']=set(report['checks'])==REQUIRED_UI_CHECKS and all(report['checks'].values())
    except Exception:
        report['ui_error']='integration-check-failed'  # Never exception bodies/locals/keys.
    finally:
        report['new_provider_responses']=responses()-before_responses
        report['provider_request_attempted']=attempts()>before_attempts
        report['real_inference_executed']=bool(live and report['new_provider_responses']>0)
        if live:report['accepted']=report['accepted'] and report['new_provider_responses']==1 and report['provider_request_attempted']
        report['usage']=getattr(provider,'last_usage',None) if report['new_provider_responses'] else None
        report['request_metrics']=getattr(provider,'last_request_metrics',None) if report['provider_request_attempted'] else None
        f.doCleanups()
    return report


def prior_success(path,*,model):
    """Private receipt prevents unnecessary repeat calls, not an approval token."""
    from operator_secrets import private_file
    path=Path(path)
    if not path.exists() and not path.is_symlink():return None
    data=json.loads(private_file(path,128*1024))
    if (data.get('case')!=CASE_ID or data.get('model')!=model or data.get('accepted') is not True
            or data.get('real_inference_executed') is not True or data.get('mode')!='live-cloud'
            or data.get('new_provider_responses')!=1 or type(data.get('checks')) is not dict
            or set(data['checks'])!=REQUIRED_UI_CHECKS or not all(value is True for value in data['checks'].values())):
        raise ValueError('Previous validation receipt cannot be verified; no automatic retry')
    return {**deepcopy(data),'completed_before_this_run':True,'prior_live_verified':True,
            'real_inference_executed':False,'new_provider_responses':0,'provider_request_attempted':False,'usage':None,'request_metrics':None}
