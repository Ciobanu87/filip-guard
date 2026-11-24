"""Bounded public-page evidence; never credentials, cookies, forms or raw HTML."""
import hashlib
import re
from urllib.parse import urlsplit,urlunsplit
from bs4 import BeautifulSoup

VERSION='grounded-advisor-v1'
INJECTION=re.compile(r'ignore.{0,30}(instructions|rules)|system\s*prompt|developer\s*message|<\|(?:im_start|system)|exfiltrat|(?:api|secret)[ _-]?key|application[ _-]?password|bearer\s+\S+|BEGIN .*PRIVATE KEY',re.I)
SENSITIVE=re.compile(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b(?:\d[ -]?){9,}\b|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+|\b(?:password|token|secret)\s*[:=]\s*\S+',re.I)

def clean(value,limit=400):
    if not isinstance(value,str):return ''
    text=' '.join(value[:4096].split())
    text=''.join(c for c in text if c.isprintable())
    if INJECTION.search(text):return ''
    return SENSITIVE.sub('[redacted]',text)[:limit]

def public_url(value):
    try:
        p=urlsplit(value)
        if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:return ''
        # Paths/query values may themselves contain account IDs/access tokens.
        return urlunsplit((p.scheme,p.hostname,'/','',''))
    except (ValueError,TypeError):return ''

def extract_context(html):
    soup=BeautifulSoup(html,'html.parser')
    for tag in list(soup.select('script,style,noscript,template,form,input,textarea,select,nav,footer,header,[hidden],[aria-hidden="true"]')):
        if tag.parent is not None:tag.decompose()
    for tag in list(soup.select('[style]')):
        if tag.parent is not None and re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',str(tag.get('style','')),re.I):tag.decompose()
    fragments=[]
    for tag in soup.select('h1,h2,p')[:30]:
        if re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',str(tag.get('style','')),re.I):continue
        text=clean(tag.get_text(' ',strip=True),240)
        if text and text not in fragments:fragments.append(text)
        if len(fragments)>=5:break
    return fragments

def evidence_bundle(rows,contexts=None,broken=()):
    """Provider gets opaque page/finding IDs, not tenant names, URLs or HTML."""
    from ai_advisor import analyze_pages
    pages=[];findings=[];facts={};base=[];contexts=contexts or {}
    for index,row in enumerate(rows[:30]):
        page_id='p'+str(index)
        status=row.get('http_status')
        metrics={'http_status':status if type(status) is int and 100<=status<=599 else 'unavailable'}
        for key in ('h1_count','images_missing_alt'):
            value=row.get(key)
            metrics[key]=value if type(value) is int and 0<=value<=100000 else 'unknown'
        snippets=[]
        for kind,value in [('title',row.get('title','')),('meta_description',row.get('meta_description',''))]+[('content',x) for x in contexts.get(row.get('page'),[])[:5]]:
            value=clean(value,240)
            if value:
                key=page_id+'e'+str(len(snippets));fact={'id':key,'kind':kind,'text':value}
                snippets.append(fact);facts[key]=fact
        pages.append({'id':page_id,'metrics':metrics,'evidence':snippets})
        recommendations=analyze_pages([row])
        for item in recommendations:
            if len(findings)>=8:break
            identifier='f'+str(len(findings))
            findings.append({'id':identifier,'page_id':page_id,'problem':item['problem'],'minimum_priority':item['priority']})
            base.append({**item,'finding_id':identifier,'page_id':page_id})
    return {'version':VERSION,'pages':pages[:30],'findings':findings},facts,base
