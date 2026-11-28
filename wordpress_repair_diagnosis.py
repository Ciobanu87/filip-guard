"""Conservative admission from observed HTTP evidence; no inferred root causes."""

def diagnose_link(report,url):
    observations=[item.get('status') for item in report.get('broken',())
                  if type(item) is dict and item.get('link')==url]
    known=bool(observations) and all(type(status) is int for status in observations)
    eligible=known and all(status in (404,410) for status in observations)
    if eligible:category='destination-reported-missing'
    elif known and any(status in (401,403) for status in observations):category='access-or-policy-failure'
    elif known and any(status==429 or 500<=status<=599 for status in observations):category='temporary-or-server-failure'
    else:category='insufficient-or-conflicting-evidence'
    return {'category':category,'observed_statuses':sorted(set(observations)) if known else [],
            'link_replacement_eligible':eligible,'root_cause_confirmed':False,
            'requires_human_review':True}
