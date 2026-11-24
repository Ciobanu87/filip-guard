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
        # Irrelevant uncertainty is not useful page context. This rendering also
        # applies to existing accepted results without calling a model again.
        if item['problem']!='Images missing ALT text':
            item['missing_information']=[value for value in item['missing_information'] if value!='image_purpose_unknown']
        if language=='ro':
            item['problem_label']=label;item['cause']=cause+' Cauza tehnică de fond nu este stabilită.'
            item['impact']=impact;item['reason']=impact;item['solution']=solution
            if item['source']=='model-assisted' and item['evidence']:
                quote=item['evidence'][0]['text'];item['reason']+=' Dovadă observată: „'+quote+'”'
                item['solution']+=' Verifică relevanța pentru subiectul observat: „'+quote+'”'
            item['priority_reason']='Prioritatea ține cont de problema detectată și de dovezi; impactul asupra afacerii nu este cunoscut.'
            item['risk']='Necesită verificare umană. Textul paginii este o sursă neconfirmată; nu sunt garantate rezultate SEO.'
            item['approval']='Recomandare informativă; reparațiile suportate necesită aprobare explicită separată.'
        else:
            item['problem_label']=item['problem']
            item['cause']='Scanner observed this condition: '+item['problem']+'. The underlying technical cause is not established.'
            item['impact']=item['reason'].split(' Observed page evidence:')[0]

        if item['source']=='model-assisted' and 'content_unavailable' in item['missing_information']:
            if item['problem'] in ('Missing SEO title','Missing meta description'):
                item['seo_draft']=None
                if language=='ro':
                    item['reason']='Conținutul paginii este insuficient pentru o recomandare SEO specifică; eticheta sau titlul singur nu stabilesc subiectul.'
                    item['solution']='Obține conținutul paginii și confirmă subiectul înainte de redactarea unui titlu sau a unei meta descrieri.'
                else:
                    item['reason']='Page content is insufficient for page-specific SEO advice; a label or title alone does not establish the topic.'
                    item['solution']='Obtain page content and confirm its subject before drafting a title or meta description.'
            elif not item['evidence']:
                item['reason']=('Nu a fost observat conținut utilizabil al paginii. '+item['impact'] if language=='ro' else
                                'No usable page content was observed. '+item['impact'])
        item['review_steps']=review_steps(item,language)
        item['review_guidance_source']='reviewed-templates'
    return output


def review_steps(item, language='en'):
    """Read-only verification guidance from known issue types and observed text.

    These are reviewed instructions, not model reasoning, executable operations,
    confirmed root causes or permission to change a site. Never infer an image's
    contents from a caption or a page's business from a title alone.
    """
    if language not in ('en','ro'):
        raise ValueError('Supported advice language required')
    quote=next((fact.get('text','') for fact in item.get('evidence',[])
                if fact.get('kind')=='content' and len(fact.get('text',''))>=20
                and '[redacted]' not in fact.get('text','')),None)
    problem=item['problem']
    ro=language=='ro'
    if problem in ('Missing SEO title','Missing meta description'):
        field=('titlul SEO' if problem=='Missing SEO title' else 'meta descrierea') if ro else ('SEO title' if problem=='Missing SEO title' else 'meta description')
        return [
            ('Verifică în HTML-ul public că lipsește '+field+'; nu presupune că valoarea din editor este publicată.' if ro else
             'Verify the missing '+field+' in the public HTML; do not assume the editor value is published.'),
            (('Confirmă subiectul folosind fragmentul observat: „'+quote+'”. Redactează '+field+' fără a inventa servicii, beneficii sau rezultate.' if ro else
              'Confirm the topic using the observed excerpt: “'+quote+'”. Draft the '+field+' without inventing services, benefits or outcomes.') if quote else
             ('Obține conținutul paginii și confirmă subiectul înainte de redactare; titlul singur nu este suficient.' if ro else
              'Obtain page content and confirm its subject before drafting; a title alone is insufficient.')),
            ('După o modificare autorizată separat, verifică HTML-ul public și concordanța cu pagina; această recomandare nu aplică modificări.' if ro else
             'After a separately authorized change, verify the public HTML and consistency with the page; this recommendation applies no changes.')]
    if problem=='H1 structure needs review':
        return [
            ('Inspectează elementele H1 și ordinea titlurilor în HTML-ul public; numărul singur nu demonstrează o eroare.' if ro else
             'Inspect the H1 elements and heading order in public HTML; the count alone does not establish a defect.'),
            (('Compară ierarhia cu fragmentul observat: „'+quote+'”; confirmă titlul principal și secțiunile înainte de orice propunere.' if ro else
              'Compare the hierarchy with the observed excerpt: “'+quote+'”; confirm the main heading and sections before proposing a change.') if quote else
             ('Obține titlurile și structura paginii înainte de a propune schimbarea nivelurilor.' if ro else
              'Obtain the actual headings and page structure before proposing heading-level changes.')),
            ('Verifică accesibilitatea și aspectul înainte și după o modificare aprobată separat; nu șterge titluri doar pentru a schimba numărul.' if ro else
             'Check accessibility and layout before and after any separately approved change; do not delete headings merely to change the count.')]
    if problem=='Images missing ALT text':
        return [
            ('Identifică imaginile fără ALT și stabilește dacă sunt informative, funcționale sau decorative.' if ro else
             'Locate images with missing ALT and determine whether each is informative, functional or decorative.'),
            (('Verifică imaginea efectivă în raport cu fragmentul: „'+quote+'”; legenda nu dovedește singură conținutul sau rolul imaginii.' if ro else
              'Inspect the actual image against the excerpt: “'+quote+'”; a caption alone does not prove image contents or purpose.') if quote else
             ('Inspectează imaginile efective înainte de a propune text; nu ghici conținutul vizual.' if ro else
              'Inspect the actual images before proposing text; do not guess visual contents.')),
            ('Pentru imagini informative descrie rolul relevant; pentru cele decorative verifică dacă ALT gol este potrivit. Confirmă accesibilitatea după o modificare aprobată separat.' if ro else
             'For informative images describe their relevant purpose; for decorative images check whether empty ALT is appropriate. Verify accessibility after a separately approved change.')]
    if problem=='Page unavailable or scan failed':
        return [
            ('Reverifică URL-ul și răspunsul HTTP; separă eroarea serverului de o problemă de acces sau scanare.' if ro else
             'Recheck the URL and HTTP response; distinguish a server error from an access or scan failure.'),
            ('Consultă jurnalele autorizate ale serverului și disponibilitatea serviciului; nu atribui o cauză tehnică fără dovezi.' if ro else
             'Review authorized server logs and service availability; do not assign a technical root cause without evidence.'),
            ('Confirmă recuperarea printr-o verificare publică reușită înainte de recomandări SEO sau reparații de conținut.' if ro else
             'Confirm recovery with a successful public check before proposing SEO or content repairs.')]
    return []
