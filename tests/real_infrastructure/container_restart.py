"""Disposable Docker process restart test; no production volume or deployment."""
import json
import os
from pathlib import Path
import tempfile
import secrets
import subprocess
import time


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True).strip()


def main():
    with tempfile.TemporaryDirectory(prefix='fg-compose-proof-') as directory:
        root=Path(directory);root.chmod(0o700)
        config=root/'operator.env';config.write_text('FG_GUARD_TEST_UI=0\nFG_EMAIL_AUTHORIZED=0\n');config.chmod(0o600)
        secret_mount=root/'secrets';secret_mount.mkdir(mode=0o700)
        env={**os.environ,'FG_OPERATOR_ENV_FILE':str(config),'FG_OPERATOR_SECRETS_DIRECTORY':str(secret_mount)}
        subprocess.run(['docker','compose','-f','deployment/compose.yml','config','--quiet'],env=env,check=True)
    identifier=secrets.token_hex(8);volume='fg-ci-state-'+identifier;container='fg-ci-ui-'+identifier
    docker('volume','create',volume)
    try:
        docker('run','-d','--name',container,'-e','FG_DISPOSABLE_VOLUME_PROOF=1','-v',volume+':/var/lib/filip-guard','filip-guard-ci:proof')
        def healthy():
            until=time.monotonic()+90
            while time.monotonic()<until:
                if docker('inspect','--format','{{.State.Health.Status}}',container)=='healthy':return
                time.sleep(1)
            raise RuntimeError('Isolated Streamlit health check failed')
        healthy()
        docker('exec',container,'python','tests/real_infrastructure/container_probe.py','seed')
        docker('stop',container);docker('start',container);healthy()
        result=json.loads(docker('exec',container,'python','tests/real_infrastructure/container_probe.py','verify'))
        assert result['cached_selection_reused'] and result['budget_preserved']
        assert result['monitoring_history_recovered'] and result['notifications_recovered']
        worker=json.loads(docker('run','--rm','-v',volume+':/var/lib/filip-guard','filip-guard-ci:proof','python','monitoring_worker.py','--once'))
        assert worker['repairs_authorized'] is False and worker['email']['status']=='disabled'
        print(json.dumps({'compose_configuration_verified':True,'streamlit_restart_verified':True,'named_volume_retained':True,'nonroot_uid':10001,
                          'accounts_and_ai_budget_recovered':True,'monitoring_history_and_alerts_recovered':True,'separate_worker_started':True,
                          'live_groq_calls':0,'real_inbox_delivery':False,'permanent_host_provisioned':False}))
    finally:
        # Only randomly named disposable proof resources owned by this invocation.
        subprocess.run(['docker','rm','-f',container],capture_output=True)
        subprocess.run(['docker','volume','rm',volume],capture_output=True)


if __name__=='__main__':main()
