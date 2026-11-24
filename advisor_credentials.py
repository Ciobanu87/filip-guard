"""Session-only credential custody and safe readiness classification.

A Colab secret is fetched once by its setup cell, not through UI RPC per case.
Nothing writes the value to a file, environment variable, report or notebook.
Python memory erasure cannot be guaranteed; close() invalidates this holder.
"""
import re
from advisor_diagnostics import AdvisorFailure

KEY_ERROR_CODES={'key_unavailable','key_access_timeout','key_access_denied','key_not_found','key_invalid','key_closed'}


def credential_failure(error):
    if type(error) is AdvisorFailure and is_credential_failure(error.diagnostic):return error
    kind=type(error).__name__
    code=('key_access_timeout' if isinstance(error,TimeoutError) or kind=='TimeoutException' else
          'key_access_denied' if isinstance(error,PermissionError) or kind=='NotebookAccessError' else
          'key_not_found' if isinstance(error,KeyError) or kind=='SecretNotFoundError' else 'key_unavailable')
    return AdvisorFailure(code,'input')


def is_credential_failure(diagnostic):
    return type(diagnostic) is dict and diagnostic.get('stage')=='input' and diagnostic.get('code') in KEY_ERROR_CODES


def valid_groq_key(value):
    if type(value) is not str or not re.fullmatch(r'gsk_[A-Za-z0-9_-]{16,200}',value):
        raise AdvisorFailure('key_invalid','input')
    return value


class SessionCredential:
    __slots__=('_value',)
    def __init__(self,value):self._value=bytearray(valid_groq_key(value).encode('ascii'))
    @classmethod
    def load(cls,secret_reader):
        try:return cls(secret_reader())
        except Exception as error:raise credential_failure(error) from None
    def __call__(self):
        if not self._value:raise AdvisorFailure('key_closed','input')
        return self._value.decode('ascii')
    def close(self):
        self._value[:]=b'\x00'*len(self._value);self._value.clear()
    def __repr__(self):return '<SessionCredential redacted>'
    __str__=__repr__
