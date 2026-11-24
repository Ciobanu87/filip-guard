"""Allowlisted diagnostics only: never exceptions, headers, bodies or user text."""
STAGES={'connect','send','read','http','json','provider','selection','deadline','input','unknown'}
CODES={'timeout','connection_failed','tls_failed','dns_failed','network_failed','invalid_http','http_error',
       'invalid_json','response_rejected','key_unavailable','input_bound','schema_shape','finding_count',
       'selection_fields','finding_identity','evidence_binding','focus_priority','priority_downgrade',
       'evidence_missing','draft_unsupported','contract_mismatch','ok','unknown'}
from advisor_provider import ProviderUnavailable

class AdvisorFailure(ValueError,ProviderUnavailable):
    def __init__(self,code,stage='selection',*,http_status=None,retry_after=None):
        self.diagnostic={'stage':stage if stage in STAGES else 'unknown','code':code if code in CODES else 'unknown'}
        if type(http_status) is int and 100<=http_status<=599:self.diagnostic['http_status']=http_status
        if type(retry_after) in (int,float) and 0<=retry_after<=3600:self.diagnostic['retry_after_seconds']=retry_after
        super().__init__('Advisor request rejected: '+self.diagnostic['code'])

def safe_diagnostic(error):
    return dict(error.diagnostic) if type(error) is AdvisorFailure else {'stage':'unknown','code':'unknown'}
