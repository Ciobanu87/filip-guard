"""Reproducible small rubric, not a claim of measured LLM quality improvement."""
import argparse
import json
import tempfile
from pathlib import Path
from contextual_advisor import rule_result,configured_advisor

CASES=[
 ('craft','Handmade oak dining tables built in our workshop.','Missing meta description'),
 ('documentation','Python package installation and version compatibility guide.','Missing meta description'),
 ('nonprofit','Community library opening hours and public reading events.','Missing meta description'),
 ('international','Atelier de mobilier din lemn pentru spații de locuit.','Missing meta description'),
 ('insufficient',None,'Page unavailable or scan failed'),
]

def evaluate(advisor=None):
    results=[]
    for index,(name,text,problem) in enumerate(CASES):
        page='https://evaluation.test/'+name
        rows=[dict(page=page,http_status=503 if text is None else 200,title='' if text is None else name,
            meta_description='',h1_count=1,images_missing_alt=0)]
        contexts={} if text is None else {page:[text]}
        baseline=rule_result(rows,contexts)
        candidate=advisor.analyze(rows,contexts,scope='e'*32+':'+format(index+1,'032x')) if advisor else baseline
        item=candidate['recommendations'][0];old=baseline['recommendations'][0]
        results.append({'case':name,'mode':candidate['status'],'correct_detected_problem':item['problem']==problem,
            'baseline_topic_specific':bool(text and text in old['solution']),
            'candidate_topic_specific':bool(text and text in item['solution']),
            'draft_grounded_or_abstained':item['seo_draft'] is None or (text is not None and item['seo_draft'] in text),
            'unsupported_autofix_blocked':item['autofix'] is False and item['repair_supported'] is False,
            'missing_business_context_explicit':'business_goal_unknown' in item['missing_information']})
    return {'cases':results,'count':len(results),'real_model_quality_validated':False,
        'rubric':'Correct findings; page-specific solution; exact supported draft or abstention; explicit missing context; no repair authority.',
        'limitations':'Synthetic public-page cases. Passing contracts or a simulated selection does not measure real model relevance, multilingual quality, latency, ranking impact or adversarial robustness.'}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--local-model',action='store_true');args=parser.parse_args(argv)
    advisor=configured_advisor() if args.local_model else None
    if args.local_model and advisor is None:parser.error('Explicit authorized local model configuration required')
    print(json.dumps(evaluate(advisor),ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
