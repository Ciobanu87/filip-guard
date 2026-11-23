import io
import unittest
from unittest.mock import Mock
from external_backup_store import S3ObjectStore,S3BackupConfig,ScopedObjectStore,ObjectStoreError,configured_s3_store


class ExternalStoreTests(unittest.TestCase):
    def test_sdk_adapter_with_controlled_s3_responses(self):
        import boto3
        from botocore.stub import Stubber
        from botocore.response import StreamingBody
        client=boto3.client('s3',region_name='us-east-1',endpoint_url='https://store.invalid',
            aws_access_key_id='fictitious-access',aws_secret_access_key='fictitious-secret')
        stub=Stubber(client);data=b'encrypted-test-data';raw=io.BytesIO(data)
        stub.add_response('put_object',{},dict(Bucket='test-bucket',Key='test',Body=data,ContentType='application/octet-stream'))
        stub.add_response('get_object',dict(Body=StreamingBody(raw,len(data)),ContentLength=len(data)),dict(Bucket='test-bucket',Key='test'))
        with stub:
            store=S3ObjectStore(client,'test-bucket');store.put('test',data)
            self.assertEqual(store.get('test'),data)
        self.assertTrue(raw.closed);stub.assert_no_pending_responses()

    def test_partial_or_oversized_stream_is_closed_and_rejected(self):
        for length,data in [(10,b'short'),(1,b'too long'),(100_000_000,b'x'),(None,b'x')]:
            body=io.BytesIO(data);client=Mock();client.get_object.return_value={'Body':body,'ContentLength':length}
            with self.assertRaises(ObjectStoreError): S3ObjectStore(client,'test-bucket').get('test')
            self.assertTrue(body.closed)

    def test_upload_download_and_close_failures_are_sanitized(self):
        client=Mock();client.put_object.side_effect=OSError('fictitious-secret')
        with self.assertRaises(ObjectStoreError) as caught:S3ObjectStore(client,'test-bucket').put('test',b'data')
        self.assertNotIn('fictitious-secret',str(caught.exception))
        client.get_object.side_effect=OSError('fictitious-secret')
        with self.assertRaises(ObjectStoreError):S3ObjectStore(client,'test-bucket').get('test')

    def test_customer_site_namespaces_cannot_cross(self):
        store=Mock();one=ScopedObjectStore(store,'a'*32,'b'*32);two=ScopedObjectStore(store,'c'*32,'d'*32)
        leaf='filip-guard-content-'+'e'*32+'.aesgcm'
        one.put(leaf,b'one');two.put(leaf,b'two')
        self.assertNotEqual(store.put.call_args_list[0].args[0],store.put.call_args_list[1].args[0])
        for leaf in ('../object','customers/other/object','/absolute'):
            with self.assertRaises(ValueError):one.get(leaf)

    def test_configuration_requires_https_and_explicit_credentials(self):
        for endpoint in ('http://store.invalid','https://user:pass@store.invalid','https://store.invalid/path','https://store.invalid?secret=value'):
            with self.assertRaises(ValueError):S3BackupConfig(endpoint,'test-bucket').validate()
        with self.assertRaises(ValueError):configured_s3_store(S3BackupConfig('https://store.invalid','test-bucket'),None)
        store=configured_s3_store(S3BackupConfig('https://store.invalid','test-bucket'),lambda:('fictitious-access','fictitious-secret'))
        self.assertEqual(store.client.meta.config.retries['total_max_attempts'],1)

    def test_bad_object_paths_never_reach_sdk(self):
        client=Mock();store=S3ObjectStore(client,'test-bucket')
        for key in ('../escape','/absolute','bad?secret=value'):
            with self.assertRaises(ValueError):store.get(key)
        client.get_object.assert_not_called()
