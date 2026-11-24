"""Continuation after the completed live probe: observable quality, not API uptime.

Expected evidence is an explicit fixture oracle and is never sent to the model.
No claim of blind human scoring or unrestricted multilingual generation.
"""
import statistics
import time
from validate_cloud_advisor import run_validation,validation_cases


def quality_cases():
    cases=[]
    for name,text,problem in validation_cases():
        if name=='craft':continue  # Already executed; audit that response offline.
        cases.append({'name':name,'text':text,'problem':problem,'language':'ro' if name=='international' else 'en',
            'expected_evidence':[] if text is None else [text],'expect_abstention':text is None})
    cases += [
        {'name':'heading-context-en','text':None,'problem':'H1 structure needs review','language':'en',
         'contexts':['Installation instructions and upgrade instructions are the two main headings.','Newsletter preferences and promotional updates are managed separately.'],
         'row_overrides':{'http_status':200,'title':'Guide','meta_description':'Installation guide overview','h1_count':2},
         'expected_evidence':['Installation instructions and upgrade instructions are the two main headings.'],'expect_abstention':True},
        {'name':'image-caption-ro','text':None,'problem':'Images missing ALT text','language':'ro',
         'contexts':['Legenda fotografiei: masă din stejar în atelier.','Programul magazinului și politica de livrare sunt prezentate separat.'],
         'row_overrides':{'http_status':200,'title':'Galerie','meta_description':'Catalogul atelierului','images_missing_alt':1},
         'expected_evidence':['Legenda fotografiei: masă din stejar în atelier.'],'expect_abstention':True},
        {'name':'sparse-context-en','text':None,'problem':'Missing meta description','language':'en',
         'row_overrides':{'http_status':200,'title':'Home'},'contexts':[],
         'expected_evidence':['Home'],'expect_abstention':True}
    ]
    return cases


def observable_quality(event,spec):
    if event['status']=='not-run':return None
    sample=event['review_sample'];selected=event.get('selected_evidence',[])
    expected=spec['expected_evidence']
    selected_text=[item['text'] for item in selected]
    expected_selected=bool(set(expected)&set(selected_text)) if expected else not selected
    content_present=bool(spec.get('contexts') or spec.get('text'))
    uncertainty_consistent=not (content_present and 'content_unavailable' in sample['missing_information'])
    accepted=event.get('selection_validated',False)
    checks={'selection_accepted':accepted,'fixture_relevant_evidence_selected':expected_selected,
        'uncertainty_consistent_with_input':uncertainty_consistent,
        'draft_grounded_or_abstained':event['draft_grounded_or_abstained'],
        'required_abstention_respected':not spec['expect_abstention'] or sample['draft'] is None,
        'requested_display_language':event['rendered_language']==spec['language'],
        'no_repair_authority':event['no_repair_authority'],
        'scanner_issue_retained':event['diagnosis_matches_scanner'],
        'missing_content_acknowledged':content_present or 'content_unavailable' in sample['missing_information']}
    return {'checks':checks,'observable_gates_passed':all(checks.values()),
        'limitations':'Fixture evidence matching and reviewed-template language, not an automatic semantic/human quality judgment.',
        'human_relevance_score':None,'human_precision_score':None,'human_language_score':None}


def run_quality_evaluation(advisor,*,live=False,wait=time.sleep,progress=None):
    if advisor.tokens>256:raise ValueError('Single-finding quality cases require bounded 256-token output')
    cases=quality_cases();lookup={case['name']:case for case in cases}
    def emit(event):
        # Base progress omits review text; assess the complete report below.
        if progress:progress(event)
    report=run_validation(advisor,live=live,wait=wait,progress=emit,case_specs=cases,max_consecutive_invalid=2)
    for event in report['cases']:
        event['quality_review']=observable_quality(event,lookup[event['case']])
    attempted=[x['latency_seconds'] for x in report['cases'] if x.get('provider_request_attempted')]
    report.update({'validation_phase':'quality-continuation','completed_stage_not_repeated':'craft single live probe',
        'planned_provider_calls_max':len(cases),'observable_quality_passes':sum(bool((x.get('quality_review') or {}).get('observable_gates_passed')) for x in report['cases']),
        'latency_summary':{'attempted_samples':len(attempted),'mean_seconds':round(statistics.mean(attempted),3) if attempted else None,
                           'max_seconds':max(attempted) if attempted else None,'stability_validated':False},
        'quality_validated':False,'oracle_sent_to_model':False,
        'rubric':'Separate structural acceptance, fixture relevance, evidence grounding, uncertainty consistency, requested display language, abstention and repair safety. Human semantic judgments remain unset.'})
    return report
