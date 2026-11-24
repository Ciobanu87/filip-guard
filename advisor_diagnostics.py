"""Allowlisted diagnostics only: never exceptions, headers, bodies or user text."""
STAGES={'connect','send','read','http','json','provider','selection','deadline','input','unknown'}
CODES={'timeout','connection_failed','tls_failed','dns_failed','network_failed','invalid_http','http_error',
       'invalid_json','response_rejected','key_unavailable','input_bound','schema_shape','finding_count',
       'selection_fields','finding_identity','evidence_binding','focus_priority','priority_downgrade',
       'evidence_missing','draft_unsupported','contract_mismatch','model_identity','completion_incomplete','unsafe_message','usage_rejected','ok','unknown'}
from advisor_provider import ProviderUnavailable

class AdvisorFailure(ValueError,ProviderUnavailable):
    def __init__(self,code,stage='selection',*,http_status=None,retry_after=None,provider_code=None,provider_type=None):
        self.diagnostic={'stage':stage if stage in STAGES else 'unknown','code':code if code in CODES else 'unknown'}
        if type(http_status) is int and 100<=http_status<=599:self.diagnostic['http_status']=http_status
        if type(retry_after) in (int,float) and 0<=retry_after<=3600:self.diagnostic['retry_after_seconds']=retry_after
        provider_codes={'json_validate_failed','invalid_api_key','rate_limit_exceeded','model_not_found','context_length_exceeded','invalid_json_schema','invalid_request_error'}
        provider_types={'invalid_request_error','authentication_error','rate_limit_error','server_error','tokens'}
        if type(provider_code) is str and provider_code in provider_codes:self.diagnostic['provider_code']=provider_code
        if type(provider_type) is str and provider_type in provider_types:self.diagnostic['provider_type']=provider_type
        super().__init__('Advisor request rejected: '+self.diagnostic['code'])

def safe_diagnostic(error):
    return dict(error.diagnostic) if type(error) is AdvisorFailure else {'stage':'unknown','code':'unknown'}
