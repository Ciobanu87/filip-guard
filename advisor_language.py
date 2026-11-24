"""Reviewed English/Romanian rendering of observed facts, not model translation."""
from copy import deepcopy
RO={
'Missing SEO title':('Lipsește titlul SEO','Scannerul nu a găsit un titlu în pagina HTML verificată.','Un titlu clar ajută vizitatorii să înțeleagă subiectul paginii.','Adaugă un titlu descriptiv, fidel conținutului paginii.'),
'Missing meta description':('Lipsește meta descrierea','Scannerul nu a găsit meta descrierea în pagina HTML verificată.','O descriere relevantă poate ajuta utilizatorii să înțeleagă pagina în rezultatele căutării.','Redactează o descriere fidelă subiectului paginii.'),
'H1 structure needs review':('Structura H1 necesită verificare','Numărul titlurilor H1 observate diferă de unu.','O structură clară poate facilita înțelegerea ierarhiei conținutului.','Verifică titlul principal și ierarhia paginii, fără a modifica inutil aspectul.'),
'Images missing ALT text':('Imagini fără text ALT','Scannerul a identificat imagini fără text ALT nevid; rolul lor nu este cunoscut.','Textul alternativ relevant poate îmbunătăți accesibilitatea imaginilor informative.','Verifică rolul imaginilor; imaginile decorative pot necesita ALT gol.'),
'Page unavailable or scan failed':('Pagina nu este disponibilă sau scanarea a eșuat','Scannerul a observat un răspuns indisponibil sau o eroare de acces.','Pagina poate fi inaccesibilă vizitatorilor și motoarelor de căutare.','Verifică URL-ul și răspunsul serverului înainte de a propune modificări SEO.')}

def render_language(result,language='en'):
    if language not in ('en','ro'):raise ValueError('Supported advice language required')
    output=deepcopy(result);output['language']=language
    for item in output['recommendations']:
        label,cause,impact,solution=RO[item['problem']]
        item['language']=language;item['language_source']='reviewed-templates'
        item['root_cause_verified']=False
        if language=='ro':
            item['problem_label']=label;item['cause']=cause+' Cauza tehnică de fond nu este stabilită.'
            item['impact']=impact;item['reason']=impact;item['solution']=solution
            if item['source']=='model-assisted' and item['evidence']:
                quote=item['evidence'][0]['text'];item['reason']+=' Dovadă observată: „'+quote+'”'
                item['solution']+=' Verifică relevanța pentru subiectul observat: „'+quote+'”.'
            item['priority_reason']='Prioritatea ține cont de problema detectată și de dovezi; impactul asupra afacerii nu este cunoscut.'
            item['risk']='Necesită verificare umană. Textul paginii este o sursă neconfirmată; nu sunt garantate rezultate SEO.'
            item['approval']='Recomandare informativă; reparațiile suportate necesită aprobare explicită separată.'
        else:
            item['problem_label']=item['problem']
            item['cause']='Scanner observed this condition: '+item['problem']+'. The underlying technical cause is not established.'
            item['impact']=item['reason'].split(' Observed page evidence:')[0]
    return output
