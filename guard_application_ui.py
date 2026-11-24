"""One customer workspace from login to verified test repair and monitoring."""
from customer_account_ui import render_customer_account
from guard_application_configuration import configured_guard_application
from monitoring_ui import render_monitoring
from contextual_advisor_ui import render_advice


def render_guard_application(st_module=None,*,application=None):
    if st_module is None:
        import streamlit as st_module
    ui=st_module
    try:application=application if application is not None else configured_guard_application()
    except Exception:
        ui.warning('The unified test workspace is not configured. Site changes remain disabled.')
        return False
    if application is None or not application.origins:return False
    ui.subheader('FILIP GUARD — integrated test workspace')
    ui.caption('Authorized isolated WordPress sites only. Customer production AutoFix is disabled.')
    if application.simulated_storage:
        ui.warning('External backup storage is simulated in this isolated demonstration.')
    render_customer_account(ui,auth=application.auth,allow_registration=application.allow_registration,sites=application.sites)
    session=ui.session_state.get('fg_customer_session')
    if not session:return True
    try:
        application.auth.resolve(session)
        with ui.expander('Connect an authorized WordPress test site',expanded=True):
            with ui.form('fg_guard_connect',clear_on_submit=True):
                origin=ui.selectbox('Authorized WordPress test site',sorted(application.origins),key='fg_customer_guard_connect_origin')
                username=ui.text_input('WordPress username')
                password=ui.text_input('WordPress Application Password',type='password')
                connect=ui.form_submit_button('Authorize site')
            if connect:
                try:
                    site=application.connect(session,origin,username,password)
                except Exception:
                    ui.error('Site authorization failed or secure storage is unavailable. No repair was performed.')
                else:
                    ui.session_state['fg_customer_guard_site']=site['site_id'];ui.rerun()
        sites=[site for site in application.sites.list_sites(session) if site['origin'] in application.origins]
        if not sites:
            ui.info('Authorize a WordPress test site for AutoFix, or a domain-owned resource below for read-only guards.')
            render_monitoring(ui,service=application.monitor);return True
        names={site['site_id']:site['origin'] for site in sites};site_key='fg_customer_guard_site'
        if ui.session_state.get(site_key) not in names:ui.session_state.pop(site_key,None)
        site_id=ui.selectbox('Connected test site',list(names),format_func=lambda value:names[value],key=site_key)
        prefix='fg_customer_guard_'+site_id
        inventory_key=prefix+'_inventory'
        if inventory_key not in ui.session_state:ui.session_state[inventory_key]=application.resources(session,site_id)
        inventory=ui.session_state[inventory_key]
        targets=[names[site_id]]+[item['link'] for item in inventory]
        with ui.form(prefix+'_scan'):
            target=ui.selectbox('Page to scan',targets,key=prefix+'_target')
            pages=ui.number_input('Maximum pages for this scan',min_value=1,max_value=30,value=3,step=1,key=prefix+'_pages')
            submitted=ui.form_submit_button('Scan authorized site')
        if submitted:
            application.scan(session,site_id,start_url=target,page_limit=int(pages));ui.rerun()
        scan=application.scan_record(session,site_id)
        if scan:
            ui.write('Scanner results');ui.dataframe(scan['report']['rows'],hide_index=True)
            ui.write('AI Advisor recommendations')
            ui.caption('Rules detect problems. Optional AI selects sanitized public page evidence; it cannot authorize repairs.')
            language=ui.selectbox('Advisor language',['en','ro'],key=prefix+'_advisor_language')
            if ui.button('Analyze context with AI',key=prefix+'_advisor_'+scan['scan_id']):
                application.advice(session,site_id,scan['scan_id'],generate=True,language=language);ui.rerun()
            advice=application.advice(session,site_id,scan['scan_id'],language=language)
            render_advice(ui,advice)
            if scan['report']['broken']:ui.dataframe(scan['report']['broken'],hide_index=True)
            if not scan['report']['complete']:ui.warning('This scan is incomplete; absence of findings does not prove the site is healthy.')
            proposals=application.proposals(session,site_id,scan['scan_id'])
            if proposals:
                with ui.form(prefix+'_proposal_'+scan['scan_id']):
                    chosen=ui.selectbox('Supported broken-link repair',list(range(len(proposals))),
                        format_func=lambda index:proposals[index]['source_url']+' → '+proposals[index]['broken_url'])
                    proposal=proposals[chosen]
                    suggestions=[item['candidate_url'] for item in proposal['candidates']]
                    replacements=[item['link'] for item in scan['inventory'] if item['link'] not in (proposal['source_url'],proposal['broken_url'])]
                    replacements=list(dict.fromkeys(suggestions+replacements))
                    if replacements:
                        replacement=ui.selectbox('Replacement page',replacements)
                        prepare=ui.form_submit_button('Prepare exact repair proposal')
                    else:
                        ui.info('No replacement page is available in the sampled published inventory.')
                        prepare=False
                if prepare:
                    review=application.prepare_repair(session,site_id,scan['scan_id'],proposal['issue_key'],proposal['resource_id'],replacement)
                    ui.session_state[prefix+'_plan']=review['plan_id'];ui.rerun()
            else:ui.info('No supported broken-link repair is available in this scan. Other recommendations remain read-only.')
        plan_id=ui.session_state.get(prefix+'_plan')
        if plan_id:
            try:review=application.review(session,site_id,plan_id)
            except Exception:
                ui.warning('This review is stale, expired or belongs to a previous session. Prepare a fresh review from history.')
            else:
                if review['state']=='proposed':
                    ui.write('Review the exact change');ui.code(review['diff'],language='diff')
                    confirmed=ui.checkbox('I approve exactly this change',key='fg_customer_guard_confirm_'+plan_id)
                    ready=application.sites.object_store is not None and callable(application.sites.master_keys)
                    if not ready:ui.warning('Verified encrypted backup storage and keys must be configured before a repair.')
                    if ui.button('Approve and apply test change',disabled=not confirmed or not ready,key='fg_customer_guard_apply_'+plan_id):
                        try:application.approve_and_apply(session,site_id,plan_id,confirmed=confirmed)
                        except Exception:ui.error('The operation was blocked or interrupted. Review its recorded status before continuing.')
                        else:ui.rerun()
        history=application.history(session,site_id)
        if history:
            ui.write('Repair and recovery history')
            restored={item['parent_plan_id'] for item in history if item['kind']=='restore' and (item['repair']['result'] or {}).get('status')=='applied'}
            for item in history:
                state=item['repair']['state'];result=item['repair']['result'] or {};status=result.get('status',state)
                ui.write(('Rollback' if item['kind']=='restore' else 'Repair')+' · '+status)
                if status=='applied':
                    ui.success('Content change applied and verified.')
                    ui.caption('An encrypted content backup was verified before the change. This is not a full-site backup.')
                    if ui.button('Recheck changed page',key='fg_customer_guard_recheck_'+item['plan_id']):
                        application.scan(session,site_id,start_url=item['source_url'],page_limit=1);ui.rerun()
                    if item['kind']=='repair' and item['plan_id'] not in restored and ui.button('Review rollback',key='fg_customer_guard_restore_'+item['plan_id']):
                        review=application.prepare_restore(session,site_id,item['plan_id'])
                        ui.session_state[prefix+'_plan']=review['plan_id'];ui.rerun()
                elif status=='rolled_back':ui.warning('Post-change verification failed; the original content was restored and verified.')
                elif status in ('outcome_unknown','applying','rollback_unverified','rollback_conflict'):
                    ui.warning('The outcome needs reconciliation. Automatic retry is blocked; the backup and journal are preserved.')
                elif state in ('proposed','approved') or status=='conflict':
                    if ui.button('Prepare fresh review',key='fg_customer_guard_renew_'+item['plan_id']):
                        review=application.renew_review(session,site_id,item['plan_id'])
                        ui.session_state[prefix+'_plan']=review['plan_id'];ui.rerun()
        render_monitoring(ui,service=application.monitor)
    except PermissionError:
        ui.warning('Access or authorization expired. Sign in again and review the latest state.')
    except Exception:
        ui.error('This step could not be verified. No success is assumed; saved scans and repair history remain available.')
    return True
