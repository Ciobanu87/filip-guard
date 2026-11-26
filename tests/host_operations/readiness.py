"""New native-host process/SQLite proof only; synthetic private state, no providers.

Never starts/enables a systemd service. Never opens production state or secrets.
No inference, master-key operations, backup upload, SMTP or public-site requests.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import selectors
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time

CODE = Path(os.environ.get('FG_VALIDATION_CODE_ROOT', '/opt/filip-guard'))
sys.path.insert(0, str(CODE))
from customer_auth import CustomerAuth
from customer_sites import CustomerSites
from monitoring_service import MonitoringService, LeaseLost
from monitoring_scan import make_report
from runtime_state import require_existing_guard_state


def deny_external(event, args):
    if event.startswith('socket.') or event in ('urllib.Request', 'http.client.connect'):
        raise RuntimeError('Network access is forbidden during host validation')
    if event in ('open', 'os.listdir', 'os.scandir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.fsdecode(args[0])
        if path.startswith(('/srv/filip-guard/state', '/etc/filip-guard/secrets')):
            raise RuntimeError('Production state/secret access is forbidden during host validation')


def services(root):
    auth = CustomerAuth(root / 'accounts.sqlite', session_ttl=86400, idle_ttl=86400)
    directory = CustomerSites(auth, root / 'sites', master_keys=None)
    return auth, directory, MonitoringService(directory, root / 'monitor.sqlite')


def fixture_report(origin):
    return make_report([dict(page=origin, http_status=200, title='Synthetic host readiness',
                             meta_description='', h1_count=1, images_missing_alt=0)], [], [], 1, True)


def scan(origin, *, before_request, checkpoint, **kwargs):
    checkpoint(); before_request(); return fixture_report(origin)


def child_code():
    return "import runpy,sys; source=sys.stdin.read(); exec(compile(source,'host-readiness-child','exec'))"


def spawned(source, *, env=None):
    return subprocess.Popen([sys.executable, '-c', child_code()], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)


def run_child(source):
    process = spawned(source)
    try:
        output, error = process.communicate(source, timeout=30)
        if process.returncode: raise RuntimeError('Isolated subprocess validation failed')
        return json.loads(output)
    finally:
        try: os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        process.wait(timeout=10)


def sqlite_crash(root):
    path = root / 'crash-recovery.sqlite'
    connection = sqlite3.connect(path)
    connection.execute('CREATE TABLE durability (value TEXT NOT NULL)')
    connection.execute("INSERT INTO durability VALUES ('committed-before-crash')")
    connection.commit(); connection.close(); path.chmod(0o600)
    # The child pauses with an actual uncommitted WAL transaction. SIGKILL must
    # leave the prior committed value intact under SQLite's normal recovery.
    source = ("import sqlite3,signal,sys; db=sqlite3.connect(" + repr(str(path)) + "); "
              "db.execute('PRAGMA journal_mode=WAL'); db.execute('PRAGMA synchronous=FULL'); "
              "db.execute('BEGIN IMMEDIATE'); db.execute(\"UPDATE durability SET value='uncommitted'\"); "
              "print('transaction-open',flush=True); signal.pause()")
    process = subprocess.Popen([sys.executable, '-c', source], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, start_new_session=True)
    try:
        with selectors.DefaultSelector() as ready:
            ready.register(process.stdout, selectors.EVENT_READ)
            if not ready.select(timeout=15) or process.stdout.readline().strip() != 'transaction-open':
                raise RuntimeError('Crash fixture did not open transaction')
        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        db = sqlite3.connect(path)
        try:
            if db.execute('PRAGMA integrity_check').fetchone() != ('ok',): raise RuntimeError('SQLite crash corruption')
            if db.execute('SELECT value FROM durability').fetchone()[0] != 'committed-before-crash':
                raise RuntimeError('Uncommitted write survived process kill')
        finally: db.close()
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)


def check():
    if os.environ.get('FG_DISPOSABLE_HOST_VALIDATION') != '1' or os.geteuid() == 0:
        raise ValueError('Explicit unprivileged disposable validation required')
    if any(os.environ.get(k) == '1' for k in ('FG_AI_AUTHORIZED', 'FG_EMAIL_AUTHORIZED', 'FG_STATE_BACKUP_AUTHORIZED')):
        raise ValueError('Provider/service activation must remain off')
    os.umask(0o077)
    sys.addaudithook(deny_external)
    with tempfile.TemporaryDirectory(prefix='fg-host-readiness-', dir=os.environ['HOME']) as temporary:
        root = Path(temporary); root.chmod(0o700)
        auth, directory, monitor = services(root); monitor.scanner = scan
        alice = auth.register('host-alice', 'Synthetic-Host-Alice-Password')
        bob = auth.register('host-bob', 'Synthetic-Host-Bob-Password')
        a = auth.login('host-alice', 'Synthetic-Host-Alice-Password', now=100)
        b = auth.login('host-bob', 'Synthetic-Host-Bob-Password', now=100)
        sa, sb = 'a' * 32, 'b' * 32
        origins = ('https://host-alice.example.test', 'https://host-bob.example.test')
        with directory.db() as db:
            for sid, principal, origin in ((sa, alice, origins[0]), (sb, bob, origins[1])):
                db.execute('INSERT INTO customer_sites VALUES (?,?,?,?,?,?,?)',
                           (sid, principal.customer_id, origin, 7, 'synthetic-no-key', b'not-a-credential', 100))
        for token, sid in ((a, sa), (b, sb)):
            monitor.configure(token, sid, enabled=True, interval_seconds=900, page_limit=1, max_requests=3, now=100)
        assert monitor.run_once(now=100)['status'] == 'complete'
        assert monitor.run_once(now=100)['status'] == 'complete'
        assert monitor.snapshot(a, sa, now=101)['findings'][0]['page'] == origins[0]
        assert monitor.snapshot(b, sb, now=101)['findings'][0]['page'] == origins[1]
        for operation in (lambda: monitor.history(b, sa, now=101),
                          lambda: monitor.snapshot(b, sa, now=101),
                          lambda: monitor.configure(b, sa, enabled=False, now=101)):
            try: operation()
            except PermissionError: pass
            else: raise RuntimeError('Cross-tenant access was not blocked')
        note = monitor.notifications(a, now=101)[0]
        try: monitor.mark_read(b, note['notification_id'], now=101)
        except PermissionError: pass
        else: raise RuntimeError('Cross-tenant notification access was not blocked')
        # Reopen all stores in a NEW Python process, without serializing keys or
        # production sessions. Tokens below belong only to this temporary fixture.
        prefix = ("import sys,json; from pathlib import Path; sys.path.insert(0," + repr(str(CODE)) + "); "
                  "from customer_auth import CustomerAuth; from customer_sites import CustomerSites; "
                  "from monitoring_service import MonitoringService; root=Path(" + repr(str(root)) + "); "
                  "auth=CustomerAuth(root/'accounts.sqlite',session_ttl=86400,idle_ttl=86400); "
                  "directory=CustomerSites(auth,root/'sites',None); m=MonitoringService(directory,root/'monitor.sqlite'); ")
        restart = run_child(prefix + "assert len(m.history(" + repr(a) + "," + repr(sa) + ",now=102))==1; "
                            + "assert len(m.history(" + repr(b) + "," + repr(sb) + ",now=102))==1; print(json.dumps({'restored':True}))")
        assert restart['restored']
        monitor.configure(b, sb, enabled=False, now=103)
        # SQLite locking must fence competing OPERATING SYSTEM processes, not
        # merely threads sharing one connection. Only one slot is currently due.
        claim_source = prefix + "print(json.dumps(m.claim(now=1000)))"
        with ThreadPoolExecutor(max_workers=6) as pool:
            jobs = list(pool.map(lambda unused: run_child(claim_source), range(6)))
        claimed = [job for job in jobs if job is not None]
        assert len(claimed) == 1
        old = claimed[0]
        restarted = MonitoringService(directory, root / 'monitor.sqlite', scanner=scan)
        new = restarted.claim(now=1090)
        assert new['run_id'] == old['run_id'] and new['lease_token'] != old['lease_token']
        try: restarted.publish(old, fixture_report(origins[0]), now=1091)
        except LeaseLost: pass
        else: raise RuntimeError('Stale process result was accepted')
        restarted.publish(new, fixture_report(origins[0]), now=1091)
        assert len(restarted.history(a, sa, now=1092)) == 2
        restarted.configure(a, sa, enabled=False, now=1093)
        sqlite_crash(root)
        # Run the ACTUAL worker entry point in this disposable environment, with
        # no due jobs and audit-blocked networking. No systemd unit is started.
        env = dict(os.environ)
        env.update(FG_CUSTOMER_AUTH_DB=str(root / 'accounts.sqlite'), FG_CUSTOMER_DATA_ROOT=str(root / 'sites'),
                   FG_MONITOR_DB=str(root / 'monitor.sqlite'), FG_EMAIL_AUTHORIZED='0', FG_AI_AUTHORIZED='0')
        for key in list(env):
            if key.startswith(('FG_GROQ', 'FG_B2', 'FG_GUARD_S3', 'FG_GUARD_KEY', 'FG_AI_LEDGER')): env.pop(key)
        wrapper = ("import sys,runpy; sys.path.insert(0," + repr(str(CODE)) + "); "
                   "sys.addaudithook(lambda event,args: (_ for _ in ()).throw(RuntimeError('No network')) if event.startswith('socket.') else None); "
                   "sys.argv=['monitoring_worker.py','--poll-seconds','10','--max-jobs','1']; "
                   "runpy.run_path(" + repr(str(CODE / 'monitoring_worker.py')) + ",run_name='__main__')")
        process = subprocess.Popen([sys.executable, '-c', wrapper], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   env=env, start_new_session=True)
        try:
            seen = None; stable = False
            for unused in range(35):
                if process.poll() is not None: raise RuntimeError('Idle worker exited unexpectedly')
                current = restarted.health()
                if current['worker_recent']:
                    if seen is None: seen = current['last_worker_seen']
                    elif current['last_worker_seen'] > seen: stable = True; break
                time.sleep(0.5)
            assert stable
            os.killpg(process.pid, signal.SIGTERM)
            assert process.wait(timeout=15) == 0
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        # Restore holds and lost-state checks must refuse fresh initialization.
        hold = root / 'held'; hold.mkdir(mode=0o700); (hold / 'FG-RESTORE-REVIEW-REQUIRED').write_text('fixture-only')
        try: CustomerAuth(hold / 'accounts.sqlite')
        except ValueError: pass
        else: raise RuntimeError('Restore reconciliation hold was bypassed')
        assert not (hold / 'accounts.sqlite').exists()
        paths = {'FG_CUSTOMER_AUTH_DB': str(root / 'accounts.sqlite'), 'FG_CUSTOMER_DATA_ROOT': str(root / 'sites'),
                 'FG_MONITOR_DB': str(root / 'monitor.sqlite')}
        require_existing_guard_state(paths)
        missing = root / 'missing-monitor.sqlite'; paths['FG_MONITOR_DB'] = str(missing)
        try: require_existing_guard_state(paths)
        except ValueError: pass
        else: raise RuntimeError('Missing persistent state was silently accepted')
        assert not missing.exists()
        for path in root.rglob('*'):
            assert not path.is_symlink()
            assert path.stat().st_mode & 0o077 == 0
        return {'status': 'native-host-isolated-readiness-verified', 'tenant_boundaries_verified': True,
                'state_reopened_in_fresh_process': True, 'single_multiprocess_claim': True,
                'stale_lease_rejected': True, 'sqlite_sigkill_recovery_verified': True,
                'idle_worker_heartbeat_advanced': True, 'worker_sigterm_exit_clean': True,
                'restore_hold_enforced': True, 'missing_state_not_recreated': True,
                'fixture_permissions_private': True, 'provider_requests': 0, 'groq_calls': 0,
                'production_state_accessed': False, 'master_key_operations': 0}


if __name__ == '__main__':
    try: report = check()
    except Exception:
        print('{"status":"native-host-readiness-unverified","provider_requests":0,"groq_calls":0}'); raise SystemExit(1)
    print(json.dumps(report, sort_keys=True))
