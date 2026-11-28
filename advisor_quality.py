"""Observable evidence-quality checks; not an automatic judge of model reasoning."""

def has_page_content(item,facts):
    return any(key.startswith(item['page_id']+'e') and fact['kind']=='content' and bool(fact['text'].strip())
               for key,fact in facts.items())


def substantive(fact):
    text=fact['text']
    return len(text)>=20 and len(text.split())>=3 and '[redacted]' not in text


def eligible_evidence(item,facts):
    keys=[key for key in facts if key.startswith(item['page_id']+'e')]
    # Do not confuse a short crawl label with the real body context when present.
    if any(facts[key]['kind']=='content' and substantive(facts[key]) for key in keys):
        return [key for key in keys if substantive(facts[key])]
    return keys


def safe_seo_excerpt(text):
    """Narrow defensive abstention; quoted page text is never trusted instructions.

    This does not prove arbitrary text safe or replace human relevance review.
    Evidence may remain visible as untrusted data even when no draft is offered.
    """
    import re
    import unicodedata
    if not isinstance(text,str):return False
    # Compare normalized text only; never rewrite the retained source evidence.
    text=unicodedata.normalize('NFKC',text)
    text=''.join(c for c in text if unicodedata.category(c)!='Cf')
    text=' '.join(text.split())
    dangerous=(r'\b(?:disable|bypass|turn off)\b.{0,160}\b(?:tls|ssl|certificates?|authentication|firewalls?|backups?|security)\b',
               r'\b(?:sudo\s+|rm\s+-[a-z]*[rf]|chmod\s+(?:-R\s+)?777|drop\s+table|truncate\s+table)\b',
               r'\b(?:guaranteed|guarantee)\b.{0,160}\b(?:ranking|rankings|first.page|seo|cure|returns)\b',
               r'\b(?:dezactiveaz[aă]|ocol[eie]ște)\b.{0,160}\b(?:tls|ssl|certificat|autentific|firewall|backup|securitat)')
    return not any(re.search(pattern,text,re.IGNORECASE) for pattern in dangerous)
