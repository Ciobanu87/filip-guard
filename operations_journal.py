"""Read allowlisted private journal events; loss/corruption is itself an incident."""
import json
import re
import subprocess
from operations_alerting import opaque


def ingest(journal,records):
    if len(records)>=1000:raise ValueError('Journal window saturated; operator review required')
    cursor=None
    for item in records:
        cursor=item.get('__CURSOR',cursor)
        try:message=json.loads(item.get('MESSAGE',''))
        except (ValueError,TypeError):continue
        if type(message) is not dict or message.get('fg_operator_event')!=1:continue
        if set(message)!={'fg_operator_event','kind','state','reference'}:raise ValueError('Malformed operator evidence')
        kind=message['kind'];state=message['state'];reference=message['reference']
        if kind not in ('autofix','rollback','ai','backup') or state not in ('failed','verified') or type(reference) is not str or not re.fullmatch('[0-9a-f]{64}',reference):raise ValueError('Invalid operator evidence')
        at=int(item['__REALTIME_TIMESTAMP'])/1e6
        source=opaque('journal',kind,reference)
        if state=='failed':journal.fail(kind,source,at)
        elif kind=='ai':
            active={row[0]:row for row in journal.active()}
            if source in active and at>active[source][2]:journal.confirm(source,opaque('verified-provider-event',cursor),at)
        # Ordinary apply/rollback success never clears a prior uncertain mutation.
    if cursor:
        with journal.db() as db:db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('journal_cursor',cursor))


def collect_journal(journal,runner=subprocess.run):
    with journal.db() as db:row=db.execute("SELECT value FROM metadata WHERE name='journal_cursor'").fetchone()
    command=['journalctl','--no-pager','--output=json','-n','1000']
    for unit in ('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service'):command+=['-u',unit]
    if row:
        if len(row[0])>512 or '\n' in row[0]:raise ValueError('Invalid private cursor')
        command+=['--after-cursor='+row[0]]
    result=runner(command,capture_output=True,text=True,check=True,timeout=5)
    if len(result.stdout)>4*1024**2:raise ValueError('Bounded journal evidence exceeded')
    ingest(journal,[json.loads(line) for line in result.stdout.splitlines() if line.strip()])
