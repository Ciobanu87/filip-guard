"""Configurable S3-compatible object adapter; no external account is configured.

SDK credentials must be supplied explicitly by trusted server code. Never use
client-controlled endpoint/bucket/keys or the SDK's ambient credential chain.
"""
from dataclasses import dataclass
import re
from urllib.parse import urlsplit

MAX_OBJECT_BYTES = 65 * 1024 * 1024


class ObjectStoreError(ConnectionError):
    pass


@dataclass(frozen=True)
class S3BackupConfig:
    endpoint_url: str
    bucket: str
    region: str = 'us-east-1'

    def validate(self):
        try:
            endpoint = urlsplit(self.endpoint_url)
            valid = (endpoint.scheme == 'https' and bool(endpoint.hostname)
                     and endpoint.username is None and endpoint.password is None
                     and endpoint.path in ('', '/') and not endpoint.query and not endpoint.fragment
                     and endpoint.port in (None,443))
        except (TypeError,ValueError):
            valid = False
        if (not valid or type(self.bucket) is not str or not re.fullmatch('[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',self.bucket)
                or '..' in self.bucket or type(self.region) is not str
                or not re.fullmatch('[a-z0-9-]{1,64}',self.region)):
            raise ValueError('Invalid trusted object-store configuration')
        return self


class S3ObjectStore:
    def __init__(self, client, bucket):
        self.client, self.bucket = client, bucket

    @staticmethod
    def _key(key):
        if type(key) is not str or len(key)>512 or not re.fullmatch('[A-Za-z0-9_./-]+',key) or '..' in key or key.startswith('/'):
            raise ValueError('Invalid backup object identifier')
        return key

    def put(self, object_id, ciphertext):
        key=self._key(object_id)
        if type(ciphertext) is not bytes or not 0<len(ciphertext)<=MAX_OBJECT_BYTES:
            raise ValueError('Invalid encrypted backup object')
        try:
            self.client.put_object(Bucket=self.bucket,Key=key,Body=ciphertext,ContentType='application/octet-stream')
        except Exception:
            raise ObjectStoreError('Encrypted backup upload failed') from None

    def get(self, object_id):
        key=self._key(object_id); body=None
        try:
            response=self.client.get_object(Bucket=self.bucket,Key=key)
            body=response.get('Body')
            length=response.get('ContentLength')
            if type(length) is not int or not 0<length<=MAX_OBJECT_BYTES:
                raise ValueError()
            if body is None: raise ValueError()
            chunks=[]; total=0
            while total<length:
                chunk=body.read(min(65536,length-total))
                if type(chunk) is not bytes or not chunk: raise ValueError()
                total+=len(chunk)
                if total>length: raise ValueError()
                chunks.append(chunk)
            if body.read(1): raise ValueError()
            return b''.join(chunks)
        except Exception:
            raise ObjectStoreError('Encrypted backup download or framing verification failed') from None
        finally:
            if body is not None:
                try:
                    body.close()
                except Exception:
                    raise ObjectStoreError('Encrypted backup stream close failed') from None


def configured_s3_store(config, credential_provider):
    """Construct only after an operator authorizes a real provider. No network yet."""
    if type(config) is not S3BackupConfig or not callable(credential_provider):
        raise ValueError('Explicit trusted configuration and credentials required')
    config.validate()
    credentials=credential_provider()
    if (type(credentials) is not tuple or len(credentials) not in (2,3)
            or any(type(value) is not str or not value for value in credentials)):
        raise ValueError('Explicit object-store credentials required')
    import boto3
    from botocore.config import Config
    client=boto3.client('s3',endpoint_url=config.endpoint_url,region_name=config.region,
        aws_access_key_id=credentials[0],aws_secret_access_key=credentials[1],
        aws_session_token=credentials[2] if len(credentials)==3 else None,
        config=Config(connect_timeout=5,read_timeout=10,retries={'total_max_attempts':1},
                      signature_version='s3v4',s3={'addressing_style':'path'}))
    return S3ObjectStore(client,config.bucket)


class ScopedObjectStore:
    """A separate namespace for each customer/site; IDs come from trusted storage."""
    def __init__(self, store, customer_id, site_id):
        if any(type(value) is not str or not re.fullmatch('[0-9a-f]{32}',value) for value in (customer_id,site_id)):
            raise ValueError('Invalid customer/site namespace')
        self.store=store
        self.prefix=f'customers/{customer_id}/sites/{site_id}/'

    def _key(self, object_id):
        if type(object_id) is not str or not re.fullmatch('filip-guard-content-[0-9a-f]{32}\\.aesgcm',object_id):
            raise ValueError('Invalid encrypted archive identifier')
        return self.prefix+object_id

    def put(self,object_id,ciphertext): self.store.put(self._key(object_id),ciphertext)
    def get(self,object_id): return self.store.get(self._key(object_id))
