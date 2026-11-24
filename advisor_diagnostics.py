"""Allowlisted diagnostics only: never exceptions, headers, bodies or user text."""
STAGES={'connect','send','read','http','json','provider','selection','deadline','input','unknown'}
CODES={'timeout','connection_failed','tls_failed','dns_failed','network_failed','invalid_http','http_error',
       'invalid_json','response_rejected','key_unavailable','input_bound','schema_shape','finding_count',
       'selection_fields','finding_identity','evidence_binding','focus_priority','priority_downgrade',
       'evidence_missing','draft_unsupported','contract_mismatch','model_identity','completion_incomplete','unsafe_message','usage_rejected','context_contradiction','ok','unknown'}
from advisor_provider import ProviderUnavailable

class AdvisorFailure(ValueError,ProviderUnavailable):
    def __init__(self,code,stage='selection',*,http_status=None,retry_after=None,provider_code=None,provider_type=None,quota=None):
        self.diagnostic={'stage':stage if stage in STAGES else 'unknown','code':code if code in CODES else 'unknown'}
        if type(http_status) is int and 100<=http_status<=599:self.diagnostic['http_status']=http_status
        if type(retry_after) in (int,float) and 0<=retry_after<=31*86400:self.diagnostic['retry_after_seconds']=retry_after
        provider_codes={'json_validate_failed','invalid_api_key','rate_limit_exceeded','model_not_found','context_length_exceeded','invalid_json_schema','invalid_request_error'}
        provider_types={'invalid_request_error','authentication_error','rate_limit_error','server_error','tokens'}
        if type(provider_code) is str and provider_code in provider_codes:self.diagnostic['provider_code']=provider_code
        if type(provider_type) is str and provider_type in provider_types:self.diagnostic['provider_type']=provider_type
        if type(quota) is dict:
            allowed={'quota_kind','retry_after_seconds','tokens_per_minute_limit','tokens_per_minute_remaining','requests_per_day_limit','requests_per_day_remaining','tokens_per_minute_reset_seconds','requests_per_day_reset_seconds'}
            for name,value in quota.items():
                if name not in allowed:continue
                if name=='quota_kind' and value in ('unknown','tokens_per_minute','tokens_per_day','requests_per_minute','requests_per_day'):self.diagnostic[name]=value
                elif type(value) in (int,float) and 0<=value<=10**10:self.diagnostic[name]=value
        super().__init__('Advisor request rejected: '+self.diagnostic['code'])

def safe_diagnostic(error):
    return dict(error.diagnostic) if type(error) is AdvisorFailure else {'stage':'unknown','code':'unknown'}
