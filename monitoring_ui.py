"""Authenticated monitoring controls and notification inbox. No repair controls."""
from datetime import datetime,timezone
from monitoring_configuration import configured_monitoring
from guard_module_ui import render_asset_authorization,render_guard_settings,observation_rows


def _when(value):
    return datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M UTC') if value is not None else 'Not checked yet'


def render_monitoring(st_module=None,*,service=None):
    if st_module is None:
        import streamlit as st_module
    ui=st_module
    with ui.expander('Website monitoring',expanded=False):
        try:service=service if service is not None else configured_monitoring()
        except Exception:
            ui.warning('Monitoring is unavailable for this deployment.');return
        if service is None:
            ui.info('Monitoring is not configured for this deployment.');return
        session=ui.session_state.get('fg_customer_session')
        if not session:
            ui.info('Sign in to manage monitoring for your authorized sites.');return
        try:
            render_asset_authorization(ui,service,session)
            sites=service.directory.list_sites(session)
        except PermissionError:
            ui.warning('Your session has expired. Sign in again.');return
        if not sites:
            ui.info('No authorized sites or endpoints are connected to this account.');return
        names={site['site_id']:site['origin'] for site in sites}
        if ui.session_state.get('fg_customer_monitor_site') not in names:ui.session_state.pop('fg_customer_monitor_site',None)
        site_id=ui.selectbox('Authorized site',list(names),format_func=lambda value:names[value],key='fg_customer_monitor_site')
        try:
            current=service.snapshot(session,site_id);schedule=current['schedule'] or {}
            prefix='fg_customer_monitor_'+site_id
            choices={900:'Every 15 minutes',3600:'Hourly',21600:'Every 6 hours',86400:'Daily',604800:'Weekly'}
            interval=schedule.get('interval_seconds',3600)
            if interval not in choices:choices[interval]=f'Every {interval//60} minutes'
            options=list(choices)
            with ui.form(prefix+'_settings'):
                enabled=ui.checkbox('Enable periodic monitoring',value=bool(schedule.get('enabled')),key=prefix+'_enabled')
                frequency=ui.selectbox('Check frequency',options,index=options.index(interval),format_func=lambda value:choices[value],key=prefix+'_interval')
                pages=ui.number_input('Maximum pages per check',min_value=1,max_value=30,
                    value=schedule.get('page_limit',5),step=1,key=prefix+'_pages')
                submitted=ui.form_submit_button('Save monitoring settings')
            if submitted:
                service.configure(session,site_id,enabled=enabled,interval_seconds=frequency,
                    page_limit=int(pages),max_requests=max(20,int(pages)))
                ui.success('Monitoring settings saved.');current=service.snapshot(session,site_id)
            render_guard_settings(ui,service,session,site_id,names[site_id])
            if not service.health()['worker_recent']:
                ui.warning('Periodic checks are waiting for the monitoring service to run.')
            last=current['last_check']
            ui.write('Last check: '+_when(last['finished_at'] if last else None))
            if last:
                ui.caption('Check status: '+last['state'])
                latest=service.history(session,site_id,limit=1)
                checks=(latest[0].get('report') or {}).get('module_checks',[]) if latest else []
                if checks:
                    ui.write('Guard observations')
                    ui.dataframe(observation_rows(checks),hide_index=True)
            ui.write('Known open issues')
            if current['findings']:
                ui.dataframe([dict(Page=f['page'],Problem=f['problem'],Priority=f['priority']) for f in current['findings']],hide_index=True)
            else:ui.info('No open issues recorded in the checked scope.')
            history=service.history(session,site_id,limit=10)
            if history:
                ui.write('Check history')
                ui.dataframe([{'Checked':_when(row['finished_at']),'Status':row['state'],'Requests':row['requests']} for row in history],hide_index=True)
            ui.write('Account notifications')
            notifications=service.notifications(session,limit=20)
            if not notifications:ui.info('No monitoring notifications yet.')
            for notice in notifications:
                ui.write(notice['kind'].replace('_',' ').title()+' · '+notice['payload']['origin'])
                for event in notice['payload']['events'][-3:]:
                    if 'new_count' in event:
                        ui.caption(f"New: {event['new_count']} · Resolved: {event['resolved_count']} · Changed pages: {event['changed_count']}")
                    else:ui.caption(event.get('message','Monitoring update'))
                if notice['read_at'] is None and ui.button('Mark as read',key='fg_customer_notice_'+notice['notification_id']):
                    service.mark_read(session,notice['notification_id']);ui.rerun()
            ui.caption('Monitoring is read-only. Email requires a separately authorized sender and verified recipient; SMTP acceptance does not prove inbox delivery.')
        except PermissionError:
            ui.warning('Monitoring access is unavailable. Sign in again.')
