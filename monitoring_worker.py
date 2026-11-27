"""Durable periodic read-only worker. Start explicitly on an authorized host.

No deployment, scheduling service, credential use or email sending occurs merely
by importing this module. --once processes a bounded batch; normal mode polls.
"""
import argparse
import json
import signal
import threading
from monitoring_configuration import configured_monitoring
from monitoring_email_configuration import configured_email_dispatcher


def main(argv=None,*,service=None,stop_event=None,email_dispatcher=None,account_dispatcher=None):
    parser=argparse.ArgumentParser(description='FILIP GUARD authorized read-only monitoring worker')
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--poll-seconds',type=int,default=30)
    parser.add_argument('--max-jobs',type=int,default=5)
    args=parser.parse_args(argv)
    if not 10<=args.poll_seconds<=300 or not 1<=args.max_jobs<=20:
        parser.error('Polling must be 10–300 seconds and batches 1–20 jobs')
    try:service=service if service is not None else configured_monitoring()
    except Exception:
        print(json.dumps({'status':'configuration_unavailable'}));return 2
    if service is None:
        print(json.dumps({'status':'not_configured'}));return 2
    email_config_failed=False
    try:email_dispatcher=email_dispatcher if email_dispatcher is not None else configured_email_dispatcher(service)
    except Exception:
        email_dispatcher=None;email_config_failed=True
    try:
        from customer_recovery_configuration import configured_account_dispatcher
        account_dispatcher=account_dispatcher if account_dispatcher is not None else configured_account_dispatcher(service)
    except Exception:account_dispatcher=None
    stop=stop_event if stop_event is not None else threading.Event()
    previous={}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM,signal.SIGINT):
            previous[sig]=signal.signal(sig,lambda *_:stop.set())
    try:
        while not stop.is_set():
            summary={'processed':0,'complete':0,'partial':0,'error':0,'repairs_authorized':False}
            try:
                for _ in range(args.max_jobs):
                    if stop.is_set():break
                    result=service.run_once();status=result['status']
                    if status=='idle':break
                    summary['processed']+=1
                    if status in ('complete','partial','error'):summary[status]+=1
                if account_dispatcher is not None:
                    try:summary['account_email']=account_dispatcher.dispatch_once()
                    except Exception:summary['account_email']={'status':'unavailable'}
                summary['email']=email_dispatcher.dispatch_once() if email_dispatcher is not None else {'status':'configuration_unavailable' if email_config_failed else 'disabled','sent':0}
            except Exception:
                summary['error']+=1
                print(json.dumps(summary))
                if args.once:return 1
            else:print(json.dumps(summary))
            if args.once:return 0
            stop.wait(args.poll_seconds)
    finally:
        for sig,handler in previous.items():signal.signal(sig,handler)
    return 0


if __name__=='__main__':raise SystemExit(main())
