"""Plain escaped evidence and provenance; no execution or approval controls."""
def render_advice(ui,result):
    ui.caption('Analysis status: '+result['status']+'. All recommendations require human review; ranking outcomes are not guaranteed.')
    if result['status'] not in ('rules','model-assisted'):
        ui.info('Model analysis was unavailable, blocked or invalid. Existing deterministic recommendations remain available.')
    items=result['recommendations']
    ui.dataframe([{k:v for k,v in item.items() if k in ('page','problem','solution','reason','priority','priority_reason','risk','source','model','seo_draft','repair_supported','approval')} for item in items],hide_index=True)
    for index,item in enumerate(items):
        with ui.expander(item['problem']+' · '+item['page']):
            ui.write('Source: '+item['source']+(' · '+item['model'] if item['model'] else ''))
            ui.write('Evidence from the sampled public page (untrusted content):')
            if item['evidence']:
                for evidence in item['evidence']:ui.text(evidence['id']+' · '+evidence['kind']+': '+evidence['text'])
            else:ui.info('No usable page-text evidence. The recommendation relies on observed Scanner metrics only.')
            ui.write('Missing information: '+', '.join(item['missing_information']))
            if item['seo_draft']:ui.text('Extractive SEO draft for review: '+item['seo_draft'])
            ui.caption(item['approval'])
