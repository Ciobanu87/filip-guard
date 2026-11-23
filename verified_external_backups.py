"""BackupManager-compatible fail-closed external content-backup prerequisite.

An archive must be uploaded, downloaded, decrypted and matched to the exact
resource before the repair engine can consume approval or attempt a write.
No real provider or keys are provisioned here. Scope: saved resource content.
"""
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
import sqlite3
import tempfile

from backup import BackupManager
from customer_auth import private_database
from wordpress_encrypted_backup import export_encrypted_copy, restore_encrypted_copy, EncryptedBackupError
from wordpress_execution_gate import _origin


class VerifiedExternalBackups:
    def __init__(self, database_path, receipt_path, site_url, store, key_provider, *, key_id):
        self.inner=BackupManager(private_database(database_path))
        self.receipt_path=private_database(receipt_path)
        self.site_url='https://'+_origin(site_url)
        self.store,self.keys,self.key_id=store,key_provider,key_id
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS external_backups (
                backup_id TEXT PRIMARY KEY, site TEXT NOT NULL, resource_id INTEGER NOT NULL,
                content_hash TEXT NOT NULL, object_id TEXT NOT NULL,
                ciphertext_sha256 TEXT NOT NULL, key_id TEXT NOT NULL)''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.receipt_path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()

    def create_backup(self,site_url,resource_id,content):
        if self.store is None or not callable(self.keys):
            raise EncryptedBackupError('Verified external backup storage is not configured')
        if 'https://'+_origin(site_url)!=self.site_url:
            raise PermissionError('Backup belongs to a different site')
        key=self.keys(self.key_id)
        backup_id=self.inner.create_backup(self.site_url,resource_id,content)
        snapshot=self.inner.get_backup(backup_id)
        receipt=export_encrypted_copy(self.inner,self.store,key,key_id=self.key_id)
        with self.db() as db:
            db.execute('INSERT INTO external_backups VALUES (?, ?, ?, ?, ?, ?, ?)',
                (backup_id,self.site_url,resource_id,snapshot['content_hash'],receipt.object_id,
                 receipt.ciphertext_sha256,receipt.key_id))
        return backup_id

    def get_backup(self,backup_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM external_backups WHERE backup_id=?',(backup_id,)).fetchone()
        if row is None or row['site']!=self.site_url:
            raise PermissionError('Verified external content backup unavailable')
        if self.store is None or not callable(self.keys):
            raise EncryptedBackupError('Verified external backup storage is not configured')
        key=self.keys(row['key_id'])
        try:
            ciphertext=self.store.get(row['object_id'])
        except Exception:
            raise EncryptedBackupError('External content backup readback failed') from None
        with tempfile.TemporaryDirectory(prefix='fg-external-restore-') as directory:
            path=Path(directory)/'recovered.sqlite'
            restore_encrypted_copy(ciphertext,key,path,expected_sha256=row['ciphertext_sha256'])
            restored=BackupManager(path).get_backup(backup_id)
        if (restored is None or restored['site_url']!=self.site_url
                or restored['resource_id']!=row['resource_id']
                or restored['content_hash']!=row['content_hash']):
            raise EncryptedBackupError('External backup does not match the required resource')
        return restored
