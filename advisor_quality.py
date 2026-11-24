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
