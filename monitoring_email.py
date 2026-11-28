"""Opt-in email adapter and durable dispatcher; no real sender is configured.

Recipients come from trusted server-side verified account bindings, never from
notification content. SMTP cannot guarantee exactly-once delivery after a lost
acknowledgment: uncertain sends are quarantined, not automatically repeated.
"""
from dataclasses import dataclass
from email.message import EmailMessage
import re
import json
import smtplib
import ssl
import uuid

from customer_auth import instant


class EmailNotConfigured(RuntimeError):pass
class DeliveryNotStarted(ConnectionError):pass
class DeliveryUncertain(ConnectionError):pass


def _address(value):
    if (type(value) is not str or len(value)>254 or not value.isascii()
            or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value)):
        raise ValueError('Invalid verified email address')
    return value


@dataclass(frozen=True)
class VerifiedEmailBinding:
    customer_id:str
    address:str


@dataclass(frozen=True)
class SMTPConfig:
    host:str
    sender:str
    port:int=465
    mode:str='ssl'

    def validate(self):
        if (type(self.host) is not str or len(self.host)>253 or not re.fullmatch('[A-Za-z0-9.-]+',self.host)
                or self.mode not in ('ssl','starttls') or type(self.port) is not int
                or self.port!=(465 if self.mode=='ssl' else 587)):
            raise ValueError('Verified TLS SMTP configuration required')
        _address(self.sender);return self


class SMTPNotificationSender:
    def __init__(self,config,credential_provider,*,authorized=False):
        if type(config) is not SMTPConfig or not callable(credential_provider):raise ValueError('Explicit SMTP configuration required')
        self.config=config.validate();self.credentials=credential_provider;self.authorized=authorized is True

    def send(self,notification,recipient):
        if not self.authorized:raise EmailNotConfigured('Email delivery has not been authorized')
        if type(recipient) is not VerifiedEmailBinding or recipient.customer_id!=notification['customer_id']:
            raise DeliveryNotStarted('Recipient does not belong to the notification account')
        destination=_address(recipient.address)
        identifier=notification['notification_id']
        if type(identifier) is not str or not re.fullmatch('[0-9a-f]{32}',identifier):raise DeliveryNotStarted('Invalid notification identifier')
        message=EmailMessage();message['Subject']='FILIP GUARD website monitoring'
        message['From']=self.config.sender;message['To']=destination
        message['Message-ID']='<'+identifier+'@'+self.config.sender.split('@')[1]+'>'
        payload=notification['payload'];lines=['FILIP GUARD monitoring update',payload['origin'],'']
        for event in payload['events']:
            if 'new_count' in event:
                lines.append(f"New issues: {event['new_count']}; resolved: {event['resolved_count']}; changed pages: {event['changed_count']}.")
            elif 'message' in event:lines.append(str(event['message'])[:300])
        lines+=['','Sign in to FILIP GUARD to review the details. No repairs were authorized by this notification.']
        message.set_content('\n'.join(lines)[:20000])
        return self._deliver(message,destination)

    def send_account_challenge(self,challenge):
        # Only the trusted encrypted account queue calls this; never expose as a raw client endpoint.
        if not self.authorized:raise EmailNotConfigured('Account email delivery has not been authorized')
        if type(challenge) is not dict or set(challenge)!={'challenge_id','customer_id','purpose','address','token'}:
            raise DeliveryNotStarted('Invalid account email request')
        if (challenge['purpose'] not in ('verify','recover') or not re.fullmatch('[0-9a-f]{32}',challenge['customer_id'])
            or not re.fullmatch('[0-9a-f]{32}',challenge['challenge_id']) or not re.fullmatch('[A-Za-z0-9_-]{43}',challenge['token'])):
            raise DeliveryNotStarted('Invalid account email request')
        destination=_address(challenge['address']);message=EmailMessage()
        purpose='Email verification' if challenge['purpose']=='verify' else 'Password recovery'
        message['Subject']='FILIP GUARD — '+purpose
        message['From']=self.config.sender;message['To']=destination
        message['Message-ID']='<'+challenge['challenge_id']+'@'+self.config.sender.split('@')[1]+'>'
        message.set_content(purpose+' code (valid for 15 minutes from your request):\n\n'+challenge['token']+
            '\n\nEnter this code only in your FILIP GUARD account form. No password, login session or repair is granted by this email. If you did not request it, ignore it.')
        return self._deliver(message,destination)

    def _deliver(self,message,destination):
        connection=None;started=False
        try:
            credentials=self.credentials()
            if type(credentials) is not tuple or len(credentials)!=2 or any(type(value) is not str or not value for value in credentials):
                raise ValueError('Explicit SMTP credentials required')
            context=ssl.create_default_context()
            if self.config.mode=='ssl':
                connection=smtplib.SMTP_SSL(self.config.host,self.config.port,timeout=10,context=context)
                connection.ehlo()
            else:
                connection=smtplib.SMTP(self.config.host,self.config.port,timeout=10)
                connection.ehlo();connection.starttls(context=context);connection.ehlo()
            connection.login(*credentials)
            started=True
            rejected=connection.send_message(message,from_addr=self.config.sender,to_addrs=[destination])
            if rejected:raise DeliveryUncertain('SMTP delivery could not be confirmed')
        except Exception:
            if started:raise DeliveryUncertain('Email acceptance unknown; do not retry automatically') from None
            raise DeliveryNotStarted('Email delivery did not start') from None
        finally:
            if connection is not None:
                try:connection.close()
                except Exception:pass
        return {'accepted':True}


class MonitoringEmailDispatcher:
    def __init__(self,monitor,*,sender=None,recipient_resolver=None):
        self.monitor,self.sender,self.recipients=monitor,sender,recipient_resolver
        with monitor.db() as db:
            db.execute('BEGIN IMMEDIATE')
            columns={row[1] for row in db.execute('PRAGMA table_info(monitor_email_outbox)')}
            if 'attempted_at' not in columns:db.execute('ALTER TABLE monitor_email_outbox ADD COLUMN attempted_at REAL')

    def dispatch_once(self,*,now=None):
        if self.sender is None or not callable(self.recipients):return {'status':'disabled','sent':0}
        timestamp=instant(now)
        with self.monitor.db() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE monitor_email_outbox SET state='unknown',error='Delivery interrupted; manual reconciliation required' WHERE state='sending' AND lease_until<=?",(timestamp,))
            db.execute("UPDATE monitor_email_outbox SET state='expired' WHERE state='pending' AND notification_id IN (SELECT notification_id FROM monitor_notifications WHERE created_at<?)",(timestamp-86400,))
            candidates=db.execute('''SELECT e.*,n.customer_id,n.site_id,n.payload,n.kind FROM monitor_email_outbox e
                JOIN monitor_notifications n ON n.notification_id=e.notification_id
                WHERE e.state='pending' AND e.not_before<=? AND e.attempts<3 ORDER BY e.not_before LIMIT 50''',(timestamp,)).fetchall()
            chosen=None
            for row in candidates:
                if not self.monitor._binding(row['customer_id'],row['site_id'],json.loads(row['payload'])['origin']):
                    db.execute("UPDATE monitor_email_outbox SET state='blocked',error='Account/site authorization unavailable' WHERE notification_id=?",(row['notification_id'],));continue
                recent=db.execute('''SELECT MAX(e.attempted_at) FROM monitor_email_outbox e JOIN monitor_notifications n
                    ON e.notification_id=n.notification_id WHERE n.customer_id=?''',(row['customer_id'],)).fetchone()[0]
                if recent is not None and timestamp-recent<3600:
                    db.execute('UPDATE monitor_email_outbox SET not_before=? WHERE notification_id=?',(recent+3600,row['notification_id']));continue
                busy=db.execute('''SELECT 1 FROM monitor_email_outbox e JOIN monitor_notifications n ON e.notification_id=n.notification_id
                    WHERE n.customer_id=? AND e.state='sending' AND e.lease_until>?''',(row['customer_id'],timestamp)).fetchone()
                if busy:continue
                chosen=dict(row);token=uuid.uuid4().hex
                db.execute("UPDATE monitor_email_outbox SET state='sending',lease_token=?,lease_until=?,attempts=attempts+1,attempted_at=? WHERE notification_id=?",
                    (token,timestamp+120,timestamp,row['notification_id']));break
        if chosen is None:return {'status':'idle','sent':0}
        chosen['payload']=json.loads(chosen['payload'])
        status='sent';error=None
        try:
            recipient=self.recipients(chosen['customer_id'])
            if type(recipient) is not VerifiedEmailBinding or recipient.customer_id!=chosen['customer_id']:
                status='blocked';error='Verified account email unavailable'
            else:
                receipt=self.sender.send(chosen,recipient)
                if type(receipt) is not dict or receipt.get('accepted') is not True:
                    raise DeliveryUncertain('Email acceptance could not be verified')
        except EmailNotConfigured:
            status='blocked';error='Email delivery not authorized/configured'
        except DeliveryNotStarted:
            status='failed' if chosen['attempts']+1>=3 else 'pending';error='Email delivery did not start'
        except Exception:
            status='unknown';error='Email acceptance unknown; manual reconciliation required'
        with self.monitor.db() as db:
            changed=db.execute('''UPDATE monitor_email_outbox SET state=?,sent_at=?,error=?,not_before=?,lease_token=NULL,lease_until=NULL
                WHERE notification_id=? AND state='sending' AND lease_token=?''',
                (status,timestamp if status=='sent' else None,error,timestamp+3600,chosen['notification_id'],token))
            if changed.rowcount!=1:return {'status':'unknown','sent':0}
        return {'status':status,'sent':1 if status=='sent' else 0}
