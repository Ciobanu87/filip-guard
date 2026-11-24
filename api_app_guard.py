"""Public GET health contracts; no auth, request body, commands or mutations."""
from guard_module_contract import Check


def run(context,config):
    for path in config['paths']:
        url=context.origin+path
        seen=False
        try:
            status,kind,body=context.site(path)
            seen=True
            status_ok=status in config['statuses']
            yield Check('api','http-contract',url,'pass' if status_ok else 'fail',
                'Endpoint status matches the configured contract.' if status_ok else 'Endpoint returned an unexpected HTTP status.',
                'Review service logs and the documented public health contract.','High',(('http_status',status),))
            if not status_ok or not config['require_json']:continue
            if kind not in ('application/json','application/health+json') and not (kind.startswith('application/') and kind.endswith('+json')):
                raise ValueError('Expected JSON content type')
            data=context.json(body)
            valid=(type(data) is dict and all(key in data for key in config['required_keys'])
                   and all(key in data and type(data[key]) is type(value) and data[key]==value for key,value in config['json_equals'].items()))
            yield Check('api','json-contract',url,'pass' if valid else 'fail',
                'Public JSON shape matches configured keys.' if valid else 'Public JSON object, required keys or configured health values do not match.',
                'Compare the response shape with the API contract. No response values or tokens are retained.')
        except (ValueError,UnicodeError):
            yield Check('api','json-contract' if seen else 'http-contract',url,'fail' if seen else 'unknown',
                'Endpoint payload could not be validated.' if seen else 'Secure HTTP check was blocked or incomplete.',
                'Review content type, JSON syntax, reachability and request limits; do not disable TLS or framing checks.')
        except Exception:
            yield Check('api','endpoint-unavailable',url,'unknown','Endpoint check could not be completed.',
                'Review reachability, TLS and request limits; a network failure does not prove old issues resolved.')
