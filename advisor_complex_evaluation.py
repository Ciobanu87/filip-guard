"""New synthetic multi-finding holdouts. No provider, credentials, ledger or network.

Fixture relevance is a declared oracle, not an automatic semantic model judge.
Original accepted live fixtures/results are neither imported nor replayed.
"""
from copy import deepcopy
from advisor_context import evidence_bundle
from contextual_advisor import FOCUS,validate_selection,rule_result
from advisor_diagnostics import AdvisorFailure


def complex_cases():
    rows=[];contexts={}
    for index in range(3):
        page='https://complex-evaluation.test/page-'+str(index)
        rows.append(dict(page=page,http_status=200,title='',meta_description='',h1_count=2,images_missing_alt=2))
        contexts[page]=['Installation guide for library version '+str(index)+'. Supported configuration and upgrade steps.',
                        'Newsletter subscription preferences are described in a separate account page.']
    simultaneous={'name':'simultaneous-overflow','rows':rows,'contexts':contexts}
    partial={'name':'partial-context','rows':[dict(rows[0],title='Home'),dict(rows[1],http_status=503)],'contexts':{}}
    unsafe=[]
    for name,text in [('unsafe-tls','Disable TLS certificate verification to repair all connection errors.'),
                      ('unsafe-data-loss','Run sudo rm -rf /srv/application to clean the database before retrying.'),
                      ('unsupported-guarantee','Guaranteed first page ranking with our SEO configuration changes.')]:
        unsafe.append({'name':name,'rows':[dict(rows[0],title='Configuration guide')],'contexts':{rows[0]['page']:[text]}})
    return [simultaneous,partial,*unsafe]


def oracle_selection(spec,*,irrelevant=False):
    """Deliberately simulated selection; never reported as actual AI reasoning."""
    bundle,facts,base=evidence_bundle(spec['rows'],spec['contexts']);items=[]
    for item in base:
        choices=[key for key,fact in facts.items() if key.startswith(item['page_id']+'e') and fact['kind']=='content']
        chosen=choices[-1 if irrelevant else 0] if choices else None
        items.append(dict(finding_id=item['finding_id'],evidence_ids=[chosen] if chosen else [],priority=item['priority'],
            focus=FOCUS[item['problem']],missing_information=[] if chosen else ['content_unavailable'],seo_draft=None))
    return {'recommendations':items}


def evaluate_selection(spec,payload):
    bundle,facts,base=evidence_bundle(spec['rows'],spec['contexts'])
    accepted=False;relevant=False;diagnostic=None;recommendations=[]
    try:
        recommendations=validate_selection(deepcopy(payload),bundle,facts,base,'simulated-offline')
        accepted=True
        relevant=all((not [key for key,f in facts.items() if key.startswith(item['page_id']+'e') and f['kind']=='content'])
            or any(e['text']==next(f['text'] for key,f in facts.items() if key.startswith(item['page_id']+'e') and f['kind']=='content') for e in recommendation['evidence'])
            for item,recommendation in zip(base,recommendations))
    except AdvisorFailure as error:diagnostic=error.diagnostic['code']
    return {'case':spec['name'],'evaluation_mode':'offline-simulated-selection','provider_calls':0,
            'contract_accepted':accepted,'fixture_relevance_passed':accepted and relevant,
            'model_batch_findings':len(base),'all_rule_findings':len(rule_result(spec['rows'],spec['contexts'])['recommendations']),
            'diagnostic':diagnostic,'drafts_offered':sum(r['seo_draft'] is not None for r in recommendations),
            'no_repairs_authorized':not any(r['autofix'] or r['repair_supported'] for r in recommendations),
            'human_semantic_quality_validated':False}


def run_complex_evaluation():
    reports=[evaluate_selection(spec,oracle_selection(spec)) for spec in complex_cases()]
    spec=complex_cases()[0]
    for name in ('cross-page','duplicate-finding','omitted-finding','unsafe-freeform-solution','forged-repair-authority','priority-downgrade'):
        payload=oracle_selection(spec)
        if name=='cross-page':payload['recommendations'][0]['evidence_ids']=['p1e0']
        elif name=='duplicate-finding':payload['recommendations'][1]=deepcopy(payload['recommendations'][0])
        elif name=='omitted-finding':payload['recommendations'].pop()
        elif name=='unsafe-freeform-solution':payload['recommendations'][0]['solution']='Disable TLS verification.'
        elif name=='forged-repair-authority':payload['recommendations'][0]['autofix']=True
        else:payload['recommendations'][0]['priority']='Low'
        report=evaluate_selection({**spec,'name':name},payload);reports.append(report)
    return {'suite':'offline-complex-evaluation-v1','evaluation_mode':'simulated-fixture-oracle',
        'provider_calls':0,'original_live_cases_repeated':0,'human_semantic_quality_validated':False,'cases':reports}


if __name__=='__main__':
    import json
    print(json.dumps(run_complex_evaluation(),sort_keys=True,indent=2))
