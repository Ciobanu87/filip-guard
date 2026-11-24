"""One-cell continuation in the owner's EXISTING Colab runtime only.

No browser login, new runtime, credential file, ledger reset or AutoFix imports.
The executable evaluation implementation is pinned to the tested development SHA.
"""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

REVISION = '61f27e7a86ed3515647c520117596c814318a7cf'
REPOSITORY = 'https://github.com/Ciobanu87/filip-guard.git'
REQUIRED = {'documentation', 'nonprofit', 'international', 'insufficient',
            'wordpress-post', 'injection', 'image-caption-ro', 'sparse-context-en'}


def existing_ledger(namespace):
    candidate = namespace.get('ledger')
    if candidate is None:
        candidate = getattr(namespace.get('advisor'), 'path', None)
    if candidate is None:
        candidate = '/content/filip-guard-cloud-validation-state/ledger.sqlite'
    ledger = Path(candidate)
    if not ledger.is_file():
        raise RuntimeError('Istoricul existent lipsește. Oprire fără registru nou sau apel AI.')
    with sqlite3.connect(ledger.resolve().as_uri()+'?mode=ro', uri=True) as db:
        db.execute('SELECT count(*) FROM advisor_requests').fetchone()
    return ledger


def completed_required(advisor, completed_fixtures, quality_cases):
    completed = completed_fixtures(advisor, quality_cases())
    missing = REQUIRED - set(completed)
    if missing:
        raise RuntimeError('Rezultate anterioare lipsă: '+', '.join(sorted(missing))+'. Niciun apel nou.')
    return completed


def run(namespace):
    # Validate persistence before invalidating objects or doing any network work.
    ledger = existing_ledger(namespace)
    namespace['advisor'] = None
    previous = namespace.get('credential')
    if hasattr(previous, 'close'):
        previous.close()
    namespace['credential'] = None
    checkout = Path('/content/filip-guard-ai-validation-'+REVISION[:12])
    if not checkout.exists():
        subprocess.run(['git', 'clone', '--single-branch', '--branch',
                        'filip-guard-development', REPOSITORY, str(checkout)],
                       check=True, capture_output=True)
        subprocess.run(['git', 'checkout', '--detach', REVISION], cwd=checkout,
                       check=True, capture_output=True)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=checkout, text=True).strip()
    if revision != REVISION:
        raise RuntimeError('Versiune diferită de cea verificată; nicio inferență executată.')
    for name, module in list(sys.modules.items()):
        origin = getattr(module, '__file__', None)
        if isinstance(origin, str) and origin.startswith('/content/filip-guard-ai-validation'):
            del sys.modules[name]
    sys.path[:] = [p for p in sys.path if not str(p).startswith('/content/filip-guard-ai-validation')]
    sys.path.insert(0, str(checkout))

    from advisor_credentials import SessionCredential
    from advisor_diagnostics import AdvisorFailure
    from advisor_groq import GroqFreeProvider
    from contextual_advisor import ContextualAdvisor
    from advisor_quality_evaluation import run_quality_evaluation, _completed_fixtures, quality_cases
    from google.colab import userdata, files

    # Prior authorization covers synthetic tests on Free, not billing or sites.
    # No key read is needed to inspect exact existing fixture results.
    provider = GroqFreeProvider(lambda: None, free_plan_confirmed=True, data_consent=True)
    advisor = ContextualAdvisor(ledger, provider, daily_calls=20, timeout=20, max_output_tokens=256)
    completed = completed_required(advisor, _completed_fixtures, quality_cases)
    print('Rezultate păstrate:', len(completed), '| Maximum cazuri noi:', len(quality_cases())-len(completed))
    if len(completed) < len(quality_cases()):
        try:
            credential = SessionCredential.load(lambda: userdata.get('GROQ_API_KEY'))
        except AdvisorFailure as error:
            print('Acces secret:', error.diagnostic['code'])
            raise RuntimeError('Acces la secret indisponibil; niciun apel Groq executat.') from None
        namespace['credential'] = credential
        provider.keys = credential
    namespace.update(ledger=ledger, checkout=checkout, revision=revision, advisor=advisor)
    report = run_quality_evaluation(advisor, live=True, progress=lambda event: print(
        json.dumps(event, ensure_ascii=False), flush=True))
    report['repository_revision'] = revision
    report['continuation_method'] = 'existing-colab-runtime-one-cell'
    namespace['report'] = report
    destination = ledger.parent/('cloud-validation-'+uuid.uuid4().hex+'.json')
    # Exclusive creation and private permissions; never overwrite prior reports.
    import os
    fd = os.open(destination, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    namespace['report_path'] = destination
    print(json.dumps({key: report[key] for key in (
        'real_inference_executed', 'new_provider_responses', 'accepted_ai_cases',
        'completed_before_this_run', 'observable_quality_passes', 'quality_validated')}, ensure_ascii=False))
    print('Raport salvat:', str(destination))
    files.download(str(destination))
    return report


if __name__ == '__main__':
    run(globals())
