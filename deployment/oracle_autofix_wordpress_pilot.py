"""One-shot private ARM64 PHP/SQL installation and disposable WordPress pilot.

Controller runs as root; signed packages have no scriptlets and are installed
only under a temporary installroot. Tests run as nobody in a loopback-only netns.
No application files, real state, service definitions or host RPM DB are changed.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types

PHASE='admission'
ROOT=None
BEFORE=None
RPM_BEFORE=None
H=None
DIAGNOSTICS=[]
DEADLINE=None
BASE='https://yum.oracle.com/repo/OracleLinux/OL9/'
TESTS=(
 'test_real_production_profile_refuses_arbitrary_content_and_unadmitted_resource',
 'test_real_production_candidate_full_flow_uses_public_verification_and_reviewed_restore',
 'test_real_write_lost_or_incomplete_response_never_replays',
 'test_real_verification_disconnect_triggers_verified_rollback',
 'test_real_rollback_does_not_overwrite_later_wordpress_edit',
 'test_real_permission_revocation_before_application',
 'test_real_conditional_restore_and_idempotency',
 'test_real_race_at_the_sql_condition',
 'test_real_restore_lost_reply_is_explicitly_unverified')


def rpm_state():
    result=subprocess.run(['rpm','-qa','--qf','%{NAME} %{VERSION}-%{RELEASE} %{ARCH}\\n'],capture_output=True,check=True,timeout=20)
    return hashlib.sha256(b'\n'.join(sorted(result.stdout.splitlines()))).hexdigest()


def descendant_rss(parent_pid):
    """Sum resident memory for the private process tree, including new sessions."""
    records={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            fields=(entry/'stat').read_text().rsplit(')',1)[1].split()
            memory=(entry/'status').read_text().splitlines()
            rss=next((int(line.split()[1])*1024 for line in memory if line.startswith('VmRSS:')),0)
            records[int(entry.name)]=(int(fields[1]),rss)
        except (OSError,ValueError,IndexError):continue
    selected={parent_pid}
    while True:
        expanded=selected|{pid for pid,(ppid,_) in records.items() if ppid in selected}
        if expanded==selected:break
        selected=expanded
    return sum(records.get(pid,(0,0))[1] for pid in selected)


def bounded(args, *, env, cwd, log, seconds=360):
    """Never expose command output; cap private disk, free space and wall time."""
    with open(log,'ab') as output:
        process=subprocess.Popen(args,cwd=cwd,env=env,stdout=output,stderr=output,start_new_session=True)
        started=time.monotonic()
        try:
            while process.poll() is None:
                if (DEADLINE is not None and time.monotonic()>DEADLINE) or time.monotonic()-started>seconds or H.directory_bytes(ROOT)>2*1024**3 or shutil.disk_usage(ROOT).free<5*1024**3 or descendant_rss(process.pid)>2*1024**3:
                    raise RuntimeError('Private pilot resource bound reached')
                time.sleep(.5)
            if process.returncode:
                diagnostic=Path(log).read_text(errors='replace')[-20000:]
                for label,needle in (('no-package-match','No match for argument'),('repo-download-failed','Failed to download'),('gpg-check-failed','GPG check FAILED'),('gpg-key-unavailable','GPG key retrieval failed'),('module-unavailable','missing groups or modules'),('php-warning','PHP Warning'),('sql-init-failed','Installation of system tables failed'),('python-traceback','Traceback'),('test-errors','FAILED (errors='),('test-failures','FAILED (failures='),('permission-denied','Permission denied'),('sql-start-failed','SQL server failed to start'),('php-extension-load','Unable to load dynamic library'),('loader-error','error while loading shared libraries'),('undefined-symbol','undefined symbol'),('called-process-error','CalledProcessError'),('assertion-error','AssertionError'),('module-not-found','ModuleNotFoundError'),('name-error','NameError'),('missing-path','No such file or directory'),('fixture-command-failed','Local fixture command failed'),('db-connection-error','database connection'),('undefined-php-function','undefined function'),('sql-unknown-option','unknown variable')):
                    if needle in diagnostic and label not in DIAGNOSTICS:DIAGNOSTICS.append(label)
                DIAGNOSTICS.extend('python-line-'+n for n in __import__('re').findall(r'File "<string>", line (\d+)',diagnostic) if 'python-line-'+n not in DIAGNOSTICS)
                raise RuntimeError('Private command failed')
        finally:
            # Terminate descendants even when their parent has already exited.
            try:os.killpg(process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)


def run(data, helper):
    global H,ROOT,PHASE,BEFORE,RPM_BEFORE,DEADLINE
    H=types.ModuleType('native_helpers');exec(helper,H.__dict__)
    if os.geteuid()!=0 or platform.machine()!='aarch64':raise RuntimeError('ARM64 root controller required')
    identity=pwd.getpwnam('nobody')
    if identity.pw_uid in (0,pwd.getpwnam('filipguard').pw_uid):raise RuntimeError('Separate existing identity required')
    BEFORE=H.units();RPM_BEFORE=rpm_state()
    if any(x not in ('inactive','failed') for x in BEFORE):raise RuntimeError('Guard units must stay inactive')
    if shutil.disk_usage('/var/tmp').free<7*1024**3:raise RuntimeError('Insufficient free disk')
    mem=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(mem['MemAvailable'].split()[0])<2*1024**2:raise RuntimeError('Insufficient memory')
    import urllib.request
    req=urllib.request.Request('http://169.254.169.254/opc/v2/instance/',headers={'Authorization':'Bearer Oracle'})
    with urllib.request.urlopen(req,timeout=2) as r:meta=json.loads(r.read(65536))
    shape=meta.get('shapeConfig',{})
    if meta.get('shape')!='VM.Standard.A1.Flex' or shape.get('ocpus')!=1 or shape.get('memoryInGBs')!=6 or not any(meta.get(k)=='eu-frankfurt-1' for k in ('region','canonicalRegionName')):raise RuntimeError('Allocation mismatch')
    disks=json.loads(subprocess.run(['lsblk','-b','-J','-o','TYPE,SIZE'],check=True,capture_output=True,text=True,timeout=5).stdout)['blockdevices']
    if not 0<sum(int(d['size']) for d in disks if d['type']=='disk')<=47*1024**3:raise RuntimeError('Storage mismatch')
    files=H.archive_files(data)
    unshare=shutil.which('unshare');runuser=shutil.which('runuser');ip=shutil.which('ip');dnf=shutil.which('dnf')
    if not all((unshare,runuser,ip,dnf)):raise RuntimeError('Existing isolation/package manager required')
    subprocess.run([unshare,'--net','--','/usr/bin/true'],check=True,capture_output=True,timeout=5)
    keys=[p for p in Path('/etc/pki/rpm-gpg').glob('RPM-GPG-KEY-oracle*') if p.is_file() and p.stat().st_uid==0 and not p.stat().st_mode&0o022]
    if not keys:raise RuntimeError('Trusted installed Oracle signing key required')
    started=time.monotonic();DEADLINE=started+820
    with tempfile.TemporaryDirectory(prefix='fg-wp-private-',dir='/var/tmp') as temp:
        ROOT=Path(temp);os.chmod(ROOT,0o711)
        runtime=ROOT/'runtime';runtime.mkdir(mode=0o755)
        logs=ROOT/'logs';logs.mkdir(mode=0o700)
        source=ROOT/'candidate';source.mkdir(mode=0o755)
        for name,content in files:
            target=source/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o755);target.write_bytes(content);target.chmod(0o444)
        work=ROOT/'work';work.mkdir(mode=0o700);os.chown(work,identity.pw_uid,identity.pw_gid)
        env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8','HOME':str(ROOT),'TMPDIR':str(logs),'PYTHONDONTWRITEBYTECODE':'1'}
        keydir=ROOT/'keys';keydir.mkdir(mode=0o700)
        for n,key in enumerate(keys):shutil.copyfile(key,keydir/str(n))
        args=[dnf,'-y','--noplugins','--installroot='+str(runtime),'--releasever=9','--disablerepo=*',
              '--repofrompath=fg_baseos,'+BASE+'baseos/latest/aarch64/',
              '--repofrompath=fg_appstream,'+BASE+'appstream/aarch64/',
              '--enablerepo=fg_baseos','--enablerepo=fg_appstream',
              '--setopt=module_platform_id=platform:el9','--setopt=install_weak_deps=False',
              '--setopt=tsflags=noscripts,nodocs','--setopt=keepcache=False','--setopt=sslverify=True',
              '--setopt=cachedir='+str(logs/'cache'),'--setopt=persistdir='+str(logs/'persist'),
              '--setopt=logdir='+str(logs),'--setopt=gpgcheck=True',
              '--setopt=fg_baseos.gpgcheck=True','--setopt=fg_appstream.gpgcheck=True',
              '--setopt=fg_baseos.gpgkey='+','.join('file://'+str(p) for p in keydir.iterdir()),
              '--setopt=fg_appstream.gpgkey='+','.join('file://'+str(p) for p in keydir.iterdir())]
        PHASE='private-module-enable'
        bounded(args+['module','enable','php:8.3','mariadb:10.11'],env=env,cwd=ROOT,log=logs/'install.log')
        PHASE='private-signed-package-install'
        bounded(args+['install','php-cli','php-mysqlnd','php-mbstring','php-xml','mariadb-server'],env=env,cwd=ROOT,log=logs/'install.log',seconds=480)
        if rpm_state()!=RPM_BEFORE:raise RuntimeError('Host RPM package set changed')
        PHASE='official-wordpress-download'
        bounded(['/usr/bin/python3',str(source/'tests/real_wordpress/download.py'),str(ROOT/'official')],env=env,cwd=ROOT,log=logs/'download.log',seconds=100)
        for directory,dirs,names in os.walk(ROOT/'official'):
            os.chmod(directory,0o755)
            for name in names:os.chmod(Path(directory)/name,0o444)
        php=runtime/'usr/bin/php';sql=runtime/'usr/libexec/mariadbd'
        if not php.is_file() or not sql.is_file():raise RuntimeError('Private binaries missing')
        modules=runtime/'usr/lib64/php/modules'
        ini=ROOT/'php.ini'
        extensions=('mysqlnd','mysqli','mbstring','ctype','iconv','tokenizer','zlib','phar','openssl','xml','dom','simplexml','xmlreader','xmlwriter')
        ini.write_text('extension_dir='+str(modules)+'\n'+''.join('extension='+m+'.so\n' for m in extensions if (modules/(m+'.so')).is_file())+'memory_limit=256M\ndisplay_errors=stderr\nlog_errors=On\nerror_log=/dev/stderr\nsendmail_path=/usr/bin/false\n');ini.chmod(0o444)
        plugins=next((p for p in (runtime/'usr/lib64/mariadb/plugin',runtime/'usr/lib64/mysql/plugin') if p.is_dir()),None)
        messages=next((p for p in (runtime/'usr/share/mariadb',runtime/'usr/share/mysql') if (p/'english/errmsg.sys').is_file()),None)
        if not plugins or not messages:raise RuntimeError('Private SQL support paths missing')
        import shlex
        wrapper=ROOT/'sql-server'
        wrapper.write_text('#!/bin/sh\nexec '+shlex.quote(str(sql))+' "$@" '+ ' '.join(shlex.quote(x) for x in ('--plugin-dir='+str(plugins),'--lc-messages-dir='+str(messages),'--socket='+str(work/'sql.sock'),'--innodb-buffer-pool-size=64M','--max-connections=10'))+'\n');wrapper.chmod(0o555)
        result=work/'result.json'
        stage=work/'stage.json'
        child_env={**env,'HOME':str(work),'TMPDIR':str(work),'PATH':str(runtime/'usr/bin')+':/usr/bin:/bin',
          'LD_LIBRARY_PATH':str(runtime/'usr/lib64')+':'+str(runtime/'lib64'), 'PHP_INI_SCAN_DIR':str(work/'no-ini'),
          'FG_WP_PHP_BINARY':str(php),'FG_WP_PHP_INI':str(ini),'FG_WP_CLI':str(ROOT/'official/wp-cli.phar'),
          'FG_WP_SOURCE':str(ROOT/'official/wordpress'),'FG_WP_DB_SERVER':str(wrapper),
          'FG_WP_DB_BASEDIR':str(runtime/'usr'),'FG_WP_DB_DATADIR':str(work/'sql-data'),
          'FG_AI_AUTHORIZED':'0','FG_EMAIL_AUTHORIZED':'0','FG_STATE_BACKUP_AUTHORIZED':'0','FG_AUTOFIX_PRODUCTION_AUTHORIZED':'0'}
        harness=r'''import os,json,resource,pwd,subprocess,runpy,unittest,sys
os.environ.clear();os.environ.update(ENV)
def progress(name):
 with open(STAGE,'w') as f:json.dump({'stage':name},f)
progress('namespace-admission')
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_AS,(1536*1024**2,1536*1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,256*1024**2))
assert os.readlink('/proc/self/ns/net')!=HOST_NET
import socket
assert [name for _,name in socket.if_nameindex()]==['lo']
assert len(open('/proc/net/route').read().splitlines())==1
assert os.geteuid() not in (0,pwd.getpwnam('filipguard').pw_uid)
assert not os.access('/srv/filip-guard/state',os.R_OK|os.W_OK)
progress('php-runtime-probe')
p=subprocess.run([PHP,'-c',INI,'-r','echo json_encode([PHP_VERSION,extension_loaded("mysqli"),class_exists("Phar")]);'],capture_output=True,text=True,check=True,timeout=10)
versions=json.loads(p.stdout);assert versions[0].startswith('8.3.') and versions[1:]==[True,True]
progress('private-sql-initialization')
init=[INIT,'--no-defaults','--basedir='+BASE_DIR,'--datadir='+DATA_DIR,'--auth-root-authentication-method=normal','--skip-test-db','--user=nobody','--plugin-dir='+PLUGINS,'--lc-messages-dir='+MESSAGES]
subprocess.run(init,check=True,timeout=90)
progress('wordpress-fixture-and-tests')
namespace=runpy.run_path(RUNNER,run_name='private_wordpress_pilot')
extra=[]
def classify(text):
 for label,needle in [('sql-permission','Permission denied'),('sql-unknown-option','unknown variable'),('sql-missing-file','No such file'),('sql-innodb','InnoDB'),('sql-unsupported','unsupported'),('db-connect','Connection refused'),('php-missing-function','undefined function'),('php-missing-class','Class '),('fixture-db-error','database connection')]:
  if needle in text and label not in extra:extra.append(label)
 import re
 for name in re.findall(r'undefined function ([a-zA-Z_][a-zA-Z_0-9]*)\(',text):
  if len(name)<80:extra.append('undefined-function:'+name)
fixture_cls=namespace['RealWordPress'];original_command=fixture_cls.command;original_start=fixture_cls.start_database
def guarded_command(self,*args,**kwargs):
 try:return original_command(self,*args,**kwargs)
 except Exception as error:
  classify(str(error));raise
def guarded_start(self):
 try:return original_start(self)
 except Exception:
  log=self.root/'database.log'
  if log.is_file():classify(log.read_text(errors='replace')[-10000:])
  raise
fixture_cls.command=guarded_command;fixture_cls.start_database=guarded_start
cls=namespace['RealWordPressTests'];suite=unittest.TestSuite(cls(name) for name in NAMES)
r=unittest.TextTestRunner(verbosity=2).run(suite)
def safe_error(trace):
 import re
 frames=[(os.path.basename(path),int(line)) for path,line in re.findall(r'File "([^"\n]+)", line ([0-9]+)',trace)]
 last=trace.strip().splitlines()[-1]
 last=re.sub(r"'[^']*'",'[quoted]',last)
 last=re.sub(r'"[^"]*"','[quoted]',last)
 last=re.sub(r'[^ \t\n]{12,}','[redacted]',last)
 return {'frames':frames[-4:],'summary':last[:300]}
errors=[safe_error(trace) for _,trace in r.errors+r.failures]
with open(RESULT,'w') as f:json.dump(dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),php_version=versions[0],diagnostics=extra,error_summaries=errors,failed_cases=[getattr(t,'_testMethodName','setUpClass') for t,_ in r.failures+r.errors]),f)
raise SystemExit(0 if r.wasSuccessful() else 1)
'''
        replacements={'ENV':child_env,'HOST_NET':os.readlink('/proc/self/ns/net'),'PHP':str(php),'INI':str(ini),
          'INIT':str(runtime/'usr/bin/mariadb-install-db'),'BASE_DIR':str(runtime/'usr'),'DATA_DIR':str(work/'sql-data'),
          'PLUGINS':str(plugins),'MESSAGES':str(messages),'RUNNER':str(source/'tests/real_wordpress/run.py'),'NAMES':TESTS,'RESULT':str(result),'STAGE':str(stage)}
        # Identifier substitution avoids modifying user data or string contents.
        import re
        harness=re.sub(r'\b('+ '|'.join(replacements)+r')\b',lambda m:repr(replacements[m[0]]),harness)
        # The privileged namespace launcher uses only host binaries and a clean env.
        launch="import subprocess,os;subprocess.run("+repr([ip,'link','set','lo','up'])+",check=True);os.execv("+repr(runuser)+","+repr([runuser,'-u','nobody','--','/opt/filip-guard/.venv/bin/python','-c',harness])+")"
        PHASE='isolated-real-wordpress-tests'
        try:bounded([unshare,'--net','--pid','--fork','--kill-child=SIGKILL','--','/usr/bin/python3','-c',launch],env=env,cwd=source,log=logs/'tests.log',seconds=240)
        except RuntimeError:
            if not result.is_file():
                if stage.is_file():PHASE=json.loads(stage.read_text())['stage']
                raise
        measured=json.loads(result.read_text())
        PHASE='cleanup'
        report=dict(status='private-wordpress-pilot-passed' if measured['tests']==len(TESTS) and not any(measured[k] for k in ('errors','failures','skipped')) else 'private-wordpress-pilot-failed',
          measured=measured,diagnostics=DIAGNOSTICS,candidate='ee593326f89b5db8a1f0700c6a9f18424a36e0e6',
          elapsed_seconds=round(time.monotonic()-started,2),private_disk_bytes=H.directory_bytes(ROOT),
          private_packages_gpg_checked=True,package_scriptlets_disabled=True,arm64=True,
          real_wordpress_version='7.1.5',sql_family='MariaDB 10.11',network_namespace_loopback_only=True,
          global_installations=0,public_listeners_created=0,actual_customer_or_master_keys_used=False,
          groq_calls=0,smtp_messages=0,b2_calls=0,production_autofix_activated=False)
    report.update(temporary_files_removed=not ROOT.exists(),guard_unit_states_unchanged=H.units()==BEFORE,host_rpm_packages_unchanged=rpm_state()==RPM_BEFORE)
    if not all(report[k] for k in ('temporary_files_removed','guard_unit_states_unchanged','host_rpm_packages_unchanged')):report['status']='private-wordpress-pilot-failed'
    return report


def main(helper):
    try:report=run(sys.stdin.buffer.read(2017281),helper)
    except Exception:
        report=dict(status='private-wordpress-pilot-held-or-failed',phase=PHASE,diagnostics=DIAGNOSTICS,temporary_files_removed=ROOT is None or not ROOT.exists(),production_autofix_activated=False,
                    guard_unit_states_unchanged=BEFORE is None or H.units()==BEFORE,host_rpm_packages_unchanged=RPM_BEFORE is None or rpm_state()==RPM_BEFORE)
    print(json.dumps(report,sort_keys=True))
