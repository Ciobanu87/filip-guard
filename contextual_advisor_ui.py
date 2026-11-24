"""Plain escaped evidence and provenance; no execution or approval controls."""
def render_advice(ui,result):
    from advisor_language import review_steps
    ui.caption('Analysis status: '+result['status']+'. All recommendations require human review; ranking outcomes are not guaranteed.')
    if result['status'] not in ('rules','model-assisted'):
        ui.info('Model analysis was unavailable, blocked or invalid. Existing deterministic recommendations remain available.')
    if result.get('diagnostic'):ui.caption('Diagnostic: '+str(result['diagnostic']))
    if result.get('cooldown'):
        from datetime import datetime,timezone
        waiting=result['cooldown']
        until=datetime.fromtimestamp(waiting['eligible_at'],timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        ui.info('Provider calls paused until '+until+'. Expiry source: '+waiting['expiry_source']+'. No quota or call budget was reset.')
    items=result['recommendations']
    if any(item['source']=='model-assisted' for item in items):
        ui.caption('AI selects observed evidence. Explanations and review steps use reviewed templates; they are not model-generated technical diagnoses.')
    ui.dataframe([{k:v for k,v in item.items() if k in ('page','problem','solution','reason','priority','priority_reason','risk','source','model','seo_draft','repair_supported','approval','problem_label','cause','impact','language')} for item in items],hide_index=True)
    for index,item in enumerate(items):
        with ui.expander(item['problem']+' · '+item['page']):
            ui.write('Source: '+item['source']+(' · '+item['model'] if item['model'] else ''))
            ui.write('Evidence from the sampled public page (untrusted content):')
            if item['evidence']:
                for evidence in item['evidence']:ui.text(evidence['id']+' · '+evidence['kind']+': '+evidence['text'])
            else:ui.info('No usable page-text evidence. The recommendation relies on observed Scanner metrics only.')
            ui.write('Missing information: '+', '.join(item['missing_information']))
            if item['seo_draft']:ui.text('Extractive SEO draft for review: '+item['seo_draft'])
            steps=review_steps(item,item.get('language',result.get('language','en')))
            if steps:
                ui.write('Pași de verificare — ghidaj revizuit, fără execuție:' if item.get('language',result.get('language','en'))=='ro' else 'Review steps — reviewed guidance, no execution:')
                for number,step in enumerate(steps,1):ui.text(str(number)+'. '+step)
            ui.caption(item['approval'])
