"""Opt-in Brevo-compatible verified TLS SMTP, mounted secrets, trusted recipients."""
import json
import os
import re
from datetime import datetime,timezone
from customer_auth import instant
from monitoring_email import (SMTPConfig,SMTPNotificationSender,MonitoringEmailDispatcher,
    VerifiedEmailBinding,DeliveryNotStarted,_address)
from operator_secrets import private_file


class DailyBudgetSender:
    """Reserve attempts before network I/O; restarts/concurrent workers share cap.

    Uncertain sends keep their reservation. The cap is global to this deployment;
    provider account caps must also be configured for other applications.
    """
    def __init__(self,monitor,sender,*,limit=300,clock=instant):
        if type(limit) is not int or not 1<=limit<=300:raise ValueError('Free-tier daily email budget required')
        self.monitor,self.sender,self.limit,self.clock=monitor,sender,limit,clock
        with monitor.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS smtp_daily_budget (day TEXT PRIMARY KEY,attempts INTEGER NOT NULL)')
    def send(self,notification,recipient):
        day=datetime.fromtimestamp(self.clock(),timezone.utc).strftime('%Y-%m-%d')
        with self.monitor.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO smtp_daily_budget VALUES (?,0)',(day,))
            changed=db.execute('UPDATE smtp_daily_budget SET attempts=attempts+1 WHERE day=? AND attempts<?',(day,self.limit))
            if changed.rowcount!=1:raise DeliveryNotStarted('Daily deployment email budget exhausted')
        return self.sender.send(notification,recipient)


def configured_email_dispatcher(monitor):
    if os.environ.get('FG_EMAIL_AUTHORIZED')!='1':return None
    # Fail before reserving queue items if any secret or binding is unavailable.
    secret_path=os.environ['FG_SMTP_CREDENTIALS_FILE'];bindings_path=os.environ['FG_EMAIL_BINDINGS_FILE']
    def credentials():
        data=json.loads(private_file(secret_path,8192))
        return data['username'],data['password']
    credentials()
    def recipient(customer_id):
        rows=json.loads(private_file(bindings_path,1024*1024))
        if type(rows) is not list:raise ValueError('Trusted verified recipient registry required')
        matches=[r for r in rows if type(r) is dict and r.get('customer_id')==customer_id]
        if len(matches)!=1:return None
        row=matches[0]
        if (not re.fullmatch('[0-9a-f]{32}',customer_id) or row.get('consent') is not True
                or type(row.get('verified_at')) not in (int,float) or not 0<row['verified_at']<=instant()
                or row.get('revoked') is True):return None
        return VerifiedEmailBinding(customer_id,_address(row['address']))
    # Parse the file before claiming messages; per-send lookup observes revocations.
    if type(json.loads(private_file(bindings_path,1024*1024))) is not list:raise ValueError('Verified recipient registry required')
    sender=SMTPNotificationSender(SMTPConfig(os.environ.get('FG_SMTP_HOST','smtp-relay.brevo.com'),
        os.environ['FG_SMTP_SENDER'],587,'starttls'),credentials,authorized=True)
    budget=DailyBudgetSender(monitor,sender,limit=int(os.environ.get('FG_SMTP_DAILY_LIMIT','300')))
    return MonitoringEmailDispatcher(monitor,sender=budget,recipient_resolver=recipient)
