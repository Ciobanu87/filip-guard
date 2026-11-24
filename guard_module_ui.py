"""Owner-only public resource proof and read-only guard settings. No repairs."""
from urllib.parse import urlsplit


def render_asset_authorization(ui,service,session):
    directory=service.directory
    if not hasattr(directory,'begin_proof'):return
    principal=service.auth.resolve(session)
    key='fg_customer_guard_pending_proof'
    with ui.container():
        ui.write('Authorize a website, store, API or app')
        ui.caption('For public read-only monitoring. Prove domain control with a verification file; no WordPress password is needed.')
        with ui.form('fg_guard_asset_proof'):
            origin=ui.text_input('Resource HTTPS origin',placeholder='https://api.example.com',key='fg_customer_guard_origin')
            names={'website':'Website Guard','commerce':'Commerce Guard','api':'API & App Guard','infrastructure':'Infrastructure Guard'}
            kind=ui.selectbox('Resource type',list(names),format_func=lambda value:names[value],key='fg_customer_guard_kind')
            begin=ui.form_submit_button('Prepare domain verification')
        if begin:
            try:
                proof=directory.begin_proof(session,origin,kind)
                ui.session_state[key]={**proof,'customer_id':principal.customer_id}
            except (ValueError,PermissionError):ui.error('Domain verification could not be prepared. Check the public HTTPS origin, ownership and pending limits.')
        proof=ui.session_state.get(key)
        if proof and proof.get('customer_id')==principal.customer_id:
            ui.write('Publish this exact text at '+proof['origin']+proof['path'])
            ui.code(proof['token'],language=None)
            ui.caption('The challenge expires after 15 minutes. The file must be plain text, public over verified HTTPS, without redirects.')
            if ui.button('Verify domain control',key='fg_customer_guard_confirm_proof'):
                try:
                    asset=directory.confirm_proof(session,proof['origin'],proof['token'])
                    ui.session_state['fg_customer_monitor_site']=asset['site_id'];ui.session_state.pop(key,None)
                    ui.success('Domain control verified for read-only monitoring.');ui.rerun()
                except (ValueError,PermissionError):ui.error('Domain control could not be verified. Check the file, TLS, expiry and rate limit; no monitoring permission was granted.')


def render_guard_settings(ui,service,session,site_id,origin):
    selected=service.module_settings(session,site_id);prefix='fg_customer_guards_'+site_id
    commerce=selected.get('commerce',{});api=selected.get('api',{});infra=selected.get('infrastructure',{})
    with ui.container():
        ui.write('Additional guards — read-only')
        ui.caption('Checks share the existing frequency, request budget, history and notifications. Public GET only; no purchases, credentials or automatic repairs.')
        with ui.form(prefix+'_settings'):
            website=ui.checkbox('Include Website Guard',value=selected.get('website',True),key=prefix+'_website')
            commerce_tab,api_tab,infrastructure_tab=ui.tabs(['Commerce Guard','API & App Guard','Infrastructure Guard'])
            with commerce_tab:
                use_commerce=ui.checkbox('Enable Commerce Guard',value='commerce' in selected,key=prefix+'_commerce')
                commerce_paths=ui.text_area('Catalog/product paths — one per line',value='\n'.join(commerce.get('paths',['/'])),key=prefix+'_commerce_paths')
                product=ui.checkbox('Expect Product structured data',value=commerce.get('require_product',False),key=prefix+'_product')
                currency=ui.text_input('Expected product currency — optional',value=commerce.get('expected_currency') or '',key=prefix+'_currency')
            with api_tab:
                use_api=ui.checkbox('Enable API & App Guard',value='api' in selected,key=prefix+'_api')
                api_paths=ui.text_area('Public endpoint paths — one per line',value='\n'.join(api.get('paths',['/health'])),key=prefix+'_api_paths')
                statuses=ui.text_input('Expected endpoint HTTP statuses',value=','.join(str(v) for v in api.get('statuses',[200])),key=prefix+'_statuses')
                require_json=ui.checkbox('Require a JSON object',value=api.get('require_json',True),key=prefix+'_json')
                keys=ui.text_input('Required public JSON keys — optional',value=','.join(api.get('required_keys',[])),key=prefix+'_keys')
                existing=api.get('json_equals',{})
                health_key=ui.text_input('Health status field — optional',value=next(iter(existing),''),key=prefix+'_health_key')
                prior_value=next(iter(existing.values()),'')
                types=['Text','Boolean','Integer'];prior_type='Boolean' if type(prior_value) is bool else 'Integer' if type(prior_value) is int else 'Text'
                health_type=ui.selectbox('Expected health value type',types,index=types.index(prior_type),key=prefix+'_health_type')
                health_value=ui.text_input('Expected health status value — optional',value=str(prior_value).lower() if type(prior_value) is bool else str(prior_value),key=prefix+'_health_value')
            with infrastructure_tab:
                use_infra=ui.checkbox('Enable Infrastructure Guard',value='infrastructure' in selected,key=prefix+'_infrastructure')
                expected_ips=ui.text_input('Expected public DNS addresses — optional',value=','.join(infra.get('expected_ips',[])),key=prefix+'_ips')
                days=ui.number_input('Expiry warning days',min_value=1,max_value=90,value=infra.get('warn_days',30),key=prefix+'_days')
                domain=ui.text_input('Registered apex domain for RDAP — optional',value=infra.get('registered_domain') or '',key=prefix+'_domain')
            save=ui.form_submit_button('Save guard modules')
        if save:
            try:
                settings={'website':bool(website)}
                if use_commerce:settings['commerce']={'paths':[value.strip() for value in commerce_paths.splitlines() if value.strip()],'require_product':bool(product),'expected_currency':currency.strip() or None}
                if use_api:
                    expected_value=health_value
                    if health_key.strip() and health_type=='Boolean':
                        if health_value.lower() not in ('true','false'):raise ValueError('Boolean health value required')
                        expected_value=health_value.lower()=='true'
                    elif health_key.strip() and health_type=='Integer':expected_value=int(health_value)
                    settings['api']={'paths':[value.strip() for value in api_paths.splitlines() if value.strip()],'statuses':[int(value.strip()) for value in statuses.split(',')],
                        'require_json':bool(require_json),'required_keys':[key.strip() for key in keys.split(',') if key.strip()],
                        'json_equals':{health_key.strip():expected_value} if health_key.strip() else {}}
                if use_infra:settings['infrastructure']={'expected_ips':[value.strip() for value in expected_ips.split(',') if value.strip()],
                    'warn_days':int(days),'registered_domain':domain.strip() or None}
                service.configure_modules(session,site_id,settings)
                ui.success('Read-only guard settings saved. The worker is still required for periodic checks.')
            except (ValueError,PermissionError):ui.error('Guard settings are invalid or ownership expired. Use bounded public paths without credentials, queries or mutation routes.')
        ui.caption('Disabling a check does not prove its old issues resolved. Domain-file ownership proofs expire after 30 days and must be renewed.')


def observation_rows(checks):
    from datetime import datetime,timezone
    rows=[]
    allowed={'http_status','condition','address','registered_domain','expires_at'}
    for check in checks:
        evidence=[]
        for name,value in check.get('evidence',[]):
            if name not in allowed:continue
            if name=='expires_at':
                try:value=datetime.fromtimestamp(value,timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
                except (TypeError,ValueError,OverflowError):value='unavailable'
            evidence.append(name+': '+str(value))
        rows.append({**{key:check[key] for key in ('module','page','status','problem','solution')},'evidence':'; '.join(evidence)})
    return rows
