"""Prepared five-case synthetic live evaluation; offline/approval-required by default.

No repeated original fixtures, key probe, budget reset, retry or service control.
Only explicit CLI opt-in constructs the already configured current provider.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import time
from advisor_complex_evaluation import complex_cases
from advisor_context import VERSION
from ai_advisor import analyze_pages


def _write(path,data):
    encoded=json.dumps(data,sort_keys=True).encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as output:output.write(encoded);output.flush();os.fsync(output.fileno())
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(directory)
    finally:os.close(directory)


def _read(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as source:
        info=os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or info.st_mode&0o077 or info.st_size>65536:raise ValueError('Private bounded evaluation receipt required')
        return json.loads(source.read(65537))


def _passed(report):
    return report.get('status')=='model-assisted' and all(report.get(key) is True for key in ('response_contract_validated','fixture_relevance_passed','all_findings_retained','no_repair_authority'))

def run_complex_validation(engine=None,*,authorized=False,directory=None,wait=time.sleep):
    cases=complex_cases()
    if not authorized:return {'status':'approval-required','new_synthetic_cases':len(cases),'provider_calls':0,'original_cases_repeated':0}
    if engine is None or directory is None or engine.tokens>1200 or engine.daily_calls>20:raise ValueError('Bounded existing advisor and private receipt directory required')
    root=Path(directory)
    if any(parent.is_symlink() for parent in (root,*root.absolute().parents)):raise ValueError('No symlink receipt path')
    if not root.exists():root.mkdir(mode=0o700)
    info=root.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o077:raise ValueError('Owner-private receipt directory required')
    reports=[];fresh=0
    for spec in cases:
        name=spec['name']
        fingerprint=hashlib.sha256(json.dumps([VERSION,engine.provider.name,engine.provider.model,spec],sort_keys=True).encode()).hexdigest()
        result_path=root/(name+'.result.json');attempt_path=root/(name+'.attempt.json')
        if result_path.exists() or result_path.is_symlink():
            previous=_read(result_path)
            if previous.get('fingerprint')!=fingerprint or previous.get('case')!=name:raise ValueError('Different evaluation receipt requires review')
            reports.append(previous['report'])
            if not _passed(previous['report']):return {'status':'held-previous-validation-failure','fresh_case_admissions':fresh,'cases':reports}
            continue
        if attempt_path.exists() or attempt_path.is_symlink():return {'status':'held-uncertain-validation-attempt','fresh_case_admissions':fresh,'cases':reports}
        if fresh:
            # Respect the existing provider admission interval; never retry a rejection.
            remaining=max(0,getattr(engine.provider,'minimum_interval',0))
            while remaining:
                pause=min(60,remaining);wait(pause);remaining-=pause
        _write(attempt_path,{'case':name,'fingerprint':fingerprint,'status':'reserved-before-analysis'})
        fresh+=1
        scope='e'*32+':'+hashlib.sha256(('complex-v1/'+name).encode()).hexdigest()[:32]
        result=engine.analyze(spec['rows'],spec['contexts'],scope=scope,language='en')
        expected={row['page']:next(iter(spec['contexts'].get(row['page'],[])),None) for row in spec['rows']}
        selected=[item for item in result['recommendations'] if item['source']=='model-assisted']
        relevant=bool(selected) and all(expected.get(item['page']) is None or any(e['text']==expected[item['page']] for e in item['evidence']) for item in selected)
        report={'case':name,'status':result['status'],'response_contract_validated':result.get('response_contract_validated') is True,
                'fixture_relevance_passed':relevant,'all_findings_retained':len(result['recommendations'])==len(analyze_pages(spec['rows'])),
                'no_repair_authority':all(item.get('autofix') is False and item.get('repair_supported') is False for item in result['recommendations']),
                'human_semantic_quality_validated':False}
        review=[{key:item[key] for key in ('finding_id','page','problem','priority','source','evidence','missing_information','seo_draft','solution','cause','risk') if key in item} for item in result['recommendations']]
        _write(result_path,{'case':name,'fingerprint':fingerprint,'report':report,'review':review})
        reports.append(report)
        if not _passed(report):
            return {'status':'held-validation-failure','fresh_case_admissions':fresh,'cases':reports}
    return {'status':'synthetic-evaluation-recorded','fresh_case_admissions':fresh,'original_cases_repeated':0,'cases':reports,'human_semantic_quality_validated':False}


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--allow-live',action='store_true');parser.add_argument('--receipt-directory');args=parser.parse_args(argv)
    if not args.allow_live:print(json.dumps(run_complex_validation(),sort_keys=True));return 0
    try:
        if not args.receipt_directory:raise ValueError('Private receipts required')
        import resource
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
        from contextual_advisor import configured_advisor
        engine=configured_advisor()
        if engine is None or engine.provider.name!='groq-free' or not engine.require_existing_ledger:raise ValueError('Existing current-provider runtime only')
        report=run_complex_validation(engine,authorized=True,directory=args.receipt_directory)
    except Exception:report={'status':'held-operator-review-required','provider_retry':False,'secret_values_printed':False}
    print(json.dumps(report,sort_keys=True));return 0 if report['status']=='synthetic-evaluation-recorded' else 1


if __name__=='__main__':raise SystemExit(main())
