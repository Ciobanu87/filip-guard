"""Encrypted content-backup export through an injected external object store.

No provider, real key, credentials or scheduler is configured here. Tests use an
in-memory object store and ephemeral keys. A production store must implement
put(object_id, ciphertext) and get(object_id), with private authenticated access.
This protects content snapshots, not a complete WordPress site or its database.
"""
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from backup import BackupManager

_MAGIC = b'FILIP-GUARD-CONTENT-BACKUP-v1\x00'
_MAX_ARCHIVE = 64 * 1024 * 1024


class EncryptedBackupError(ValueError):
    pass


@dataclass(frozen=True)
class EncryptedBackupReceipt:
    object_id: str
    ciphertext_sha256: str
    key_id: str
    backup_count: int
    readback_verified: bool = True
    scope: str = 'resource_content_only'


def _cipher(key):
    if type(key) is not bytes or len(key) != 32:
        raise EncryptedBackupError('A 256-bit externally managed backup key is required')
    return AESGCM(key)


def _verify_database(path):
    # Read-only open: never initialize or silently repair an invalid archive.
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise EncryptedBackupError('Invalid backup database')
        rows = db.execute('SELECT content, content_hash FROM backups').fetchall()
        for content, digest in rows:
            if (type(content) is not str or type(digest) is not str
                    or not compare_digest(sha256(content.encode('utf-8')).hexdigest(), digest)):
                raise EncryptedBackupError('Content integrity check failed')
        return len(rows)
    finally:
        db.close()


def restore_encrypted_copy(ciphertext, key, destination, *, expected_sha256=None):
    """Verify, decrypt and recover into a new private file, independently of Streamlit."""
    cipher = _cipher(key)
    if (type(ciphertext) is not bytes or not ciphertext.startswith(_MAGIC)
            or not len(_MAGIC) + 28 < len(ciphertext) <= _MAX_ARCHIVE + len(_MAGIC) + 28):
        raise EncryptedBackupError('Invalid encrypted content backup')
    if expected_sha256 is not None and (
            type(expected_sha256) is not str or not re.fullmatch('[0-9a-f]{64}', expected_sha256)
            or not compare_digest(sha256(ciphertext).hexdigest(), expected_sha256)):
        raise EncryptedBackupError('Unexpected encrypted backup object')
    offset = len(_MAGIC)
    try:
        plaintext = cipher.decrypt(ciphertext[offset:offset + 12], ciphertext[offset + 12:], _MAGIC)
    except Exception:
        raise EncryptedBackupError('Backup decryption or authentication failed') from None
    destination = os.fspath(destination)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'wb') as recovered:
            recovered.write(plaintext)
            recovered.flush()
            os.fsync(recovered.fileno())
        count = _verify_database(destination)
    except BaseException:
        os.unlink(destination)
        raise
    return {'backup_count': count, 'verified': True, 'scope': 'resource_content_only'}


def export_encrypted_copy(manager, store, key, *, key_id):
    """Upload ciphertext and independently download/decrypt/verify before success.

    The caller must retain the external key separately and persist the nonsecret
    receipt. No key is embedded in the archive, receipt, object ID or logs.
    """
    cipher = _cipher(key)
    if type(key_id) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', key_id):
        raise EncryptedBackupError('Invalid nonsecret key identifier')
    object_id = 'filip-guard-content-' + uuid.uuid4().hex + '.aesgcm'
    with tempfile.TemporaryDirectory(prefix='fg-backup-') as directory:
        path = Path(directory) / 'content.sqlite'
        metadata = manager.export_verified_copy(path)
        if path.stat().st_size > _MAX_ARCHIVE:
            raise EncryptedBackupError('Content backup exceeds archive size limit')
        nonce = os.urandom(12)
        ciphertext = _MAGIC + nonce + cipher.encrypt(nonce, path.read_bytes(), _MAGIC)
        digest = sha256(ciphertext).hexdigest()
        try:
            store.put(object_id, ciphertext)
            readback = store.get(object_id)
        except Exception:
            raise EncryptedBackupError('External content backup upload or readback failed') from None
        result = restore_encrypted_copy(readback, key, Path(directory) / 'recovered.sqlite',
                                        expected_sha256=digest)
        if result['backup_count'] != metadata['backup_count']:
            raise EncryptedBackupError('External backup recovery count mismatch')
    return EncryptedBackupReceipt(object_id, digest, key_id, result['backup_count'])
