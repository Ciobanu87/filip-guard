"""Offline recovery of supplied evaluation evidence, never of quota or live cache.

Reports are unsigned historical observations. Acceptance is rechecked against the
immutable fixture oracle, not treated as authenticated provider/account history.
This module neither imports an inference client nor opens/creates a SQLite ledger.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

MAX_BYTES = 2 * 1024 * 1024


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _invalid_number(value):
    raise ValueError('Non-finite JSON number')


def recover_reports(paths):
    from advisor_quality_evaluation import quality_cases, observable_quality
    specs = {item['name']: item for item in quality_cases()}
    sources, accepted, seen = [], {}, set()
    paths = list(paths)
    if not 1 <= len(paths) <= 32:
        raise ValueError('Provide between one and 32 historical reports')
    for path in paths:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            raise ValueError('Bounded regular report required')
        raw = path.read_bytes()
        if len(raw) > MAX_BYTES:
            raise ValueError('Report too large')
        report = json.loads(raw, object_pairs_hook=_object, parse_constant=_invalid_number)
        if not isinstance(report, dict):
            raise ValueError('Report object required')
        digest = hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False,
            separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        if (report.get('mode') != 'live-cloud' or
                report.get('model') != 'qwen/qwen3.8-27b' or
                not re.fullmatch('[0-9a-f]{40}', str(report.get('repository_revision', '')))):
            raise ValueError('Unsupported historical report provenance')
        events = report.get('cases')
        if not isinstance(events, list) or len(events) > 32:
            raise ValueError('Bounded case list required')
        names = [event.get('case') for event in events if isinstance(event, dict)]
        if len(names) != len(events) or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names):
            raise ValueError('Unique case names required')
        recovered = []
        for event in events:
            name = event['case']
            if name not in specs or event.get('status') != 'model-assisted':
                continue
            # Old v2 and cached failures cannot become accepted v3 evidence.
            if event.get('response_contract') != 'indexed-evidence-v3':
                continue
            flags = ('selection_validated', 'draft_grounded_or_abstained',
                     'no_repair_authority', 'diagnosis_matches_scanner')
            if any(event.get(flag) is not True for flag in flags):
                continue
            try:
                review = observable_quality(event, specs[name])
            except (KeyError, TypeError, ValueError):
                continue
            if not review or not review['observable_gates_passed']:
                continue
            recovered.append(name)
            # Deliberately exclude report text, secrets, old errors and usage.
            item = accepted.setdefault(name, {'case': name, 'language': specs[name]['language'],
                'observable_checks': review['checks'], 'source_sha256': [],
                'human_semantic_review': 'not-recovered'})
            item['source_sha256'].append(digest)
        sources.append({'sha256': digest, 'repository_revision': report['repository_revision'],
            'accepted_fixture_evidence': sorted(recovered)})
    return {'schema': 'filip-guard-historical-evidence-v1',
        'source_trust': 'owner-supplied-unsigned-reports',
        'sources': sorted(sources, key=lambda x: x['sha256']),
        'accepted_cases': [accepted[name] for name in sorted(accepted)],
        'accepted_case_count': len(accepted),
        'all_nine_fixture_results_preserved': set(accepted) == set(specs),
        'real_inference_executed_this_recovery': False, 'new_provider_calls': 0,
        'ledger_reconstructed': False, 'usage_history_complete': False,
        'remaining_api_budget': None, 'provider_cooldown_expires_at': None,
        'live_inference_blocked_pending_usage_reconciliation': True,
        'safe_to_repeat_accepted_cases': False,
        'limitations': ['Historical fixture evidence only; not live-site advice or an inference cache.',
            'No reservation times, daily counters, refunds or quota reset times are inferred.',
            'Structural/oracle checks do not establish full human semantic quality.',
            'Recover the original ledger or reconcile provider usage before enabling new calls.']}


def write_recovery(report, destination):
    """Private exclusive output: never overwrite a ledger, receipt or prior report."""
    data = (json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode()
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = recover_reports(args.reports)
    write_recovery(report, args.output)
    print(json.dumps({key: report[key] for key in ('accepted_case_count',
        'all_nine_fixture_results_preserved', 'new_provider_calls', 'ledger_reconstructed')}))


if __name__ == '__main__':
    main()
