"""Read-only credential-presence metadata. Never load/print a Groq key or call Groq."""
import json
import os
from pathlib import Path
import shlex
from operations_oracle_ssh_probe import run_pinned_command

REMOTE = r'''
import json,os,pwd,stat,subprocess
from pathlib import Path
settings={}
config=Path('/etc/filip-guard/runtime.env')
if config.is_file():
    for line in config.read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            name,value=line.split('=',1);settings[name]=value.strip().strip('"').strip("'")
key_path=settings.get('FG_GROQ_API_KEY_FILE')
candidates=[]
if key_path:candidates.append(Path(key_path))
secret_root=Path('/etc/filip-guard/secrets')
if secret_root.is_dir():
    for path in secret_root.rglob('*'):
        if len(path.relative_to(secret_root).parts)<=3 and 'groq' in path.name.lower():candidates.append(path)
for value in ('/run/credentials/filip-guard/groq-key','/etc/filip-guard/secrets/groq-key','/etc/filip-guard/secrets/groq.key','/etc/filip-guard/secrets/groq-api-key'):
    candidates.append(Path(value))
present=private=readable=False
for path in set(candidates):
    try:info=path.lstat()
    except FileNotFoundError:continue
    if not stat.S_ISREG(info.st_mode) or info.st_size==0:continue
    present=True
    safe=not bool(info.st_mode & 0o077) and info.st_nlink==1
    private=private or safe
    result=subprocess.run(['/usr/sbin/runuser','-u','filipguard','--','/usr/bin/python3','-c',
        'import os,sys;sys.exit(0 if os.access(sys.argv[1],os.R_OK) else 1)',str(path)],capture_output=True,timeout=10)
    readable=readable or (safe and result.returncode==0)
units={}
for name in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.timer'):
    result=subprocess.run(['/usr/bin/systemctl','is-active',name],capture_output=True,text=True,timeout=10)
    units[name]=result.stdout.strip()=='inactive'
print(json.dumps({'status':'groq-presence-read-only-verified','configured_key_file_reference':bool(key_path),
 'groq_named_nonempty_file_found':present,'private_key_file_found':private,'private_key_file_readable_by_app':readable,
 'inline_groq_secret_configured':any(bool(settings.get(k)) for k in ('GROQ_API_KEY','FG_GROQ_API_KEY')),
 'free_provider_configured':settings.get('FG_AI_PROVIDER')=='groq-free',
 'free_plan_confirmation_configured':settings.get('FG_AI_FREE_PLAN_CONFIRMED')=='1',
 'ai_authorization_off':settings.get('FG_AI_AUTHORIZED')=='0',
 'services_remain_inactive':all(units.values()),'groq_api_calls':0,'key_file_contents_read':False}))
'''


def main():
    if os.environ.get('GITHUB_REF')!='refs/heads/filip-guard-development' or os.environ.get('GITHUB_REPOSITORY')!='Ciobanu87/filip-guard':
        raise ValueError('Development branch only')
    report=json.loads(run_pinned_command('sudo -n -- /usr/bin/python3 -c '+shlex.quote(REMOTE)))
    if report.get('status')!='groq-presence-read-only-verified':raise ValueError('Presence not verified')
    report['github_standard_groq_secret_available']=any(bool(os.environ.get(k)) for k in ('FG_GROQ_API_KEY','GROQ_API_KEY'))
    print(json.dumps(report,sort_keys=True))


if __name__=='__main__':
    try:main()
    except Exception:
        print('{"status":"groq-presence-unverified","groq_api_calls":0}');raise SystemExit(1)
