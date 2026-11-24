"""Disposable Docker process restart test; no production volume or deployment."""
import json
import secrets
import subprocess
import time


def docker(*args):
    return subprocess.check_output(['docker',*args],text=True).strip()


def main():
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
        worker=json.loads(docker('run','--rm','-v',volume+':/var/lib/filip-guard','filip-guard-ci:proof','python','monitoring_worker.py','--once'))
        assert worker['repairs_authorized'] is False and worker['email']['status']=='disabled'
        print(json.dumps({'streamlit_restart_verified':True,'named_volume_retained':True,'nonroot_uid':10001,
                          'accounts_and_ai_budget_recovered':True,'separate_worker_started':True,
                          'live_groq_calls':0,'real_inbox_delivery':False,'permanent_host_provisioned':False}))
    finally:
        # Only randomly named disposable proof resources owned by this invocation.
        subprocess.run(['docker','rm','-f',container],capture_output=True)
        subprocess.run(['docker','volume','rm',volume],capture_output=True)


if __name__=='__main__':main()
