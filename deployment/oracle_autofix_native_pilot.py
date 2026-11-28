"""Approved synthetic Python-only host pilot. Root controls temporary isolation only.

No PHP/SQL install, actual state/key access, application change or public listener.
The child uses an existing unprivileged non-application user and no host network.
"""
import hashlib
import io
import json
import os
from pathlib import Path,PurePosixPath
import pwd
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

SOURCE_SHA256='75dbf433f0859ca93d6d970bd08af27a5280fc06526aa4f202d9f54222320902'
SOURCE_BYTES=2017280
TESTS=('test_autofix_failure_boundaries','test_autofix_recovery_review','test_recovery_state_integration',
       'test_wordpress_production.ProductionFlowTests')
UNITS=('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer')
PHASE='admission'
TEMP_ROOT=None
BEFORE=None


def units():
    states=[]
    for name in UNITS:
        p=subprocess.run(['systemctl','is-active',name],capture_output=True,text=True,timeout=3)
        states.append(p.stdout.strip())
    return states


def archive_files(data):
    if len(data)!=SOURCE_BYTES or hashlib.sha256(data).hexdigest()!=SOURCE_SHA256:raise ValueError('Candidate integrity mismatch')
    files=[]
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:') as archive:
        for member in archive.getmembers():
            path=PurePosixPath(member.name)
            if path.is_absolute() or any(part in ('..','.git','.venv') for part in path.parts) or not(member.isdir() or member.isfile()):
                raise ValueError('Unsafe candidate entry')
            if member.isfile():
                if member.size>2*1024**2:raise ValueError('Oversized candidate entry')
                files.append((member.name,archive.extractfile(member).read()))
    if len(files)!=367:raise ValueError('Candidate file count mismatch')
    return files


def directory_bytes(root):
    total=0
    for directory,_,names in os.walk(root,followlinks=False):
        for name in names:
            try:total+=os.stat(Path(directory)/name,follow_symlinks=False).st_size
            except FileNotFoundError:pass
    return total


def child_limits():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(120,120))
    resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))


def run(data):
    global PHASE,TEMP_ROOT,BEFORE
    if os.geteuid()!=0:raise ValueError('Trusted temporary-directory controller required')
    identity=pwd.getpwnam('nobody')
    if identity.pw_uid==0 or identity.pw_name=='filipguard':raise ValueError('Independent existing test identity required')
    python=Path('/opt/filip-guard/.venv/bin/python')
    unshare=shutil.which('unshare');runuser=shutil.which('runuser')
    if not python.is_file() or not unshare or not runuser:raise ValueError('Existing isolation/runtime dependency unavailable')
    before=units();BEFORE=before
    if any(state not in ('inactive','failed') for state in before):raise ValueError('Application units must remain inactive')
    if shutil.disk_usage('/var/tmp').free<7*1024**3:raise ValueError('Insufficient existing disk capacity')
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(memory['MemAvailable'].split()[0])<2*1024**2:raise ValueError('Insufficient memory capacity')
    import urllib.request
    request=urllib.request.Request('http://169.254.169.254/opc/v2/instance/',headers={'Authorization':'Bearer Oracle'})
    with urllib.request.urlopen(request,timeout=2) as response:metadata=json.loads(response.read(65536))
    allocation=metadata.get('shapeConfig',{})
    if (metadata.get('shape')!='VM.Standard.A1.Flex' or allocation.get('ocpus')!=1 or allocation.get('memoryInGBs')!=6
        or not any(metadata.get(k)=='eu-frankfurt-1' for k in ('region','canonicalRegionName'))):raise ValueError('Unreviewed host allocation')
    devices=json.loads(subprocess.run(['lsblk','-b','-J','-o','TYPE,SIZE'],capture_output=True,text=True,check=True,timeout=4).stdout)['blockdevices']
    sizes=[int(d['size']) for d in devices if d['type']=='disk']
    if not sizes or not 0<sum(sizes)<=47*1024**3:raise ValueError('Unreviewed storage allocation')
    files=archive_files(data)
    # Fail before temporary files if the existing kernel cannot isolate networking.
    subprocess.run([unshare,'--net','--','/usr/bin/true'],check=True,capture_output=True,timeout=5)
    PHASE='temporary-source'
    with tempfile.TemporaryDirectory(prefix='fg-autofix-native-',dir='/var/tmp') as directory:
        root=Path(directory);TEMP_ROOT=str(root);os.chown(root,identity.pw_uid,identity.pw_gid)
        source=root/'candidate';source.mkdir(mode=0o700);os.chown(source,identity.pw_uid,identity.pw_gid)
        for name,content in files:
            target=source/name
            for parent in reversed(target.parent.relative_to(source).parents):
                if str(parent)=='.':continue
                (source/parent).mkdir(exist_ok=True,mode=0o700);os.chown(source/parent,identity.pw_uid,identity.pw_gid)
            target.parent.mkdir(exist_ok=True,mode=0o700);os.chown(target.parent,identity.pw_uid,identity.pw_gid)
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
            with os.fdopen(fd,'wb') as output:output.write(content);os.fchown(output.fileno(),identity.pw_uid,identity.pw_gid)
        temporary=root/'temporary';temporary.mkdir(mode=0o700);os.chown(temporary,identity.pw_uid,identity.pw_gid)
        # Explicit clean environment: no mounted source/state paths or credentials.
        env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','TMPDIR':str(temporary),'PYTHONDONTWRITEBYTECODE':'1',
             'FG_AI_AUTHORIZED':'0','FG_EMAIL_AUTHORIZED':'0','FG_STATE_BACKUP_AUTHORIZED':'0',
             'FG_ACCOUNT_RECOVERY_AUTHORIZED':'0','FG_AUTOFIX_PRODUCTION_AUTHORIZED':'0'}
        PHASE='isolated-native-tests'
        result_path=root/'results.json';log_path=root/'private-test.log'
        harness="""import json,os,unittest,resource,pwd
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
resource.setrlimit(resource.RLIMIT_CPU,(120,120))
resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,64*1024**2))
assert os.readlink('/proc/self/ns/net')!=HOST_NET, 'Host networking must be unavailable'
assert os.geteuid() not in (0,pwd.getpwnam('filipguard').pw_uid), 'Separate existing test identity required'
assert not os.access('/srv/filip-guard/state',os.W_OK), 'Application state must not be writable'
suite=unittest.defaultTestLoader.loadTestsFromNames(TESTS)
result=unittest.TextTestRunner(verbosity=1).run(suite)
with open(RESULT,'w') as output:json.dump(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)),output)
raise SystemExit(0 if result.wasSuccessful() else 1)
""".replace('TESTS',repr(TESTS)).replace('RESULT',repr(str(result_path))).replace('HOST_NET',repr(os.readlink('/proc/self/ns/net')))
        with open(log_path,'xb') as log:
            os.chmod(log_path,0o600)
            process=subprocess.Popen([unshare,'--net','--',runuser,'-u',identity.pw_name,'--',str(python),'-c',harness],
                cwd=source,env=env,stdout=log,stderr=log,start_new_session=True,preexec_fn=child_limits)
            began=time.monotonic();peak_disk=0
            try:
                while process.poll() is None:
                    peak_disk=max(peak_disk,directory_bytes(root))
                    if time.monotonic()-began>840 or peak_disk>2*1024**3 or shutil.disk_usage(root).free<5*1024**3:
                        raise RuntimeError('Pilot execution limit reached')
                    time.sleep(.5)
            except BaseException:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
                raise
        measured=json.loads(result_path.read_text()) if result_path.is_file() else dict(tests=0,failures=0,errors=1,skipped=0)
        report=dict(status='native-python-pilot-passed' if process.returncode==0 and measured['tests']==19 and not measured['skipped'] else 'native-python-pilot-failed',
            scope='synthetic-python-sqlite-memory-store-only',candidate='ee593326f89b5db8a1f0700c6a9f18424a36e0e6',
            measured=measured,arm64=__import__('platform').machine()=='aarch64',network_namespace_isolated=True,
            allocation_verified_before_run=True,non_application_uid=True,application_state_writable_by_child=False,peak_private_disk_bytes=peak_disk,
            elapsed_seconds=round(time.monotonic()-began,2),real_wordpress_php_executed=False,
            actual_customer_or_master_keys_used=False,groq_calls=0,smtp_messages=0,b2_calls=0,
            production_autofix_activated=False,global_installations=0,public_listeners_created=0)
        PHASE='cleanup'
    report['temporary_files_removed']=not root.exists()
    report['guard_unit_states_unchanged']=units()==before
    if not report['temporary_files_removed'] or not report['guard_unit_states_unchanged']:raise RuntimeError('Cleanup/unchanged state not verified')
    return report


if __name__=='__main__':
    try:report=run(sys.stdin.buffer.read(SOURCE_BYTES+1))
    except Exception:
        print(json.dumps({'status':'native-python-pilot-held-or-failed','phase':PHASE,'temporary_files_removed':TEMP_ROOT is None or not Path(TEMP_ROOT).exists(),'production_autofix_activated':False,'global_installations':0}));raise SystemExit(0)
    print(json.dumps(report,sort_keys=True))
    raise SystemExit(0)
