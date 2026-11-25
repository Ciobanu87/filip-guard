"""Operator-only encrypted recovery of a stopped application's SQLite state.

No account provisioning, key generation, scheduling or automatic service resume.
The operator must stop ALL writers and place every persistent DB under root.
Unknown files are rejected, never silently omitted (secret mounts stay outside).
"""
import base64
from hashlib import sha256
from hmac import compare_digest
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tempfile
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b'FILIP-GUARD-APPLICATION-STATE-v1\0'
REVIEW_MARKER = 'FG-RESTORE-REVIEW-REQUIRED'
MAX_STATE = 32 * 1024 * 1024
MAX_FILES = 1024
MAX_ENVELOPE = 48 * 1024 * 1024


def _identifier(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{32}', value):
        raise ValueError('Trusted deployment identifier required')
    return value


def _key(master_keys, deployment_id, key_id):
    _identifier(deployment_id)
    if type(key_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', key_id):
        raise ValueError('Trusted key version required')
    master = master_keys(key_id)
    if type(master) is not bytes or len(master) != 32:
        raise ValueError('Externally retained 256-bit key required')
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=('FILIP-GUARD/v1/application-state/' + deployment_id).encode()).derive(master)


def _name(name, *, database=False):
    if (type(name) is not str or not 1 <= len(name) <= 512
            or not re.fullmatch('[A-Za-z0-9_./-]+', name)
            or any(p in ('', '.', '..') for p in name.split('/'))
            or PurePosixPath(name).is_absolute()):
        raise ValueError('Unsafe state archive path')
    if database and PurePosixPath(name).suffix not in ('.sqlite', '.sqlite3', '.db'):
        raise ValueError('Only SQLite state files are supported; keep secrets outside state root')
    return name


def _private(info, *, directory=False):
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or info.st_mode & 0o077 or (not directory and info.st_nlink != 1)):
        raise ValueError('Private regular state files/directories required; links are forbidden')


def _root(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('State paths cannot contain symlinks')
    _private(path.stat(), directory=True)
    return path


def _inventory(root):
    directories, files, identities = [], [], {}
    # dir_fd + O_NOFOLLOW protects each file open; a second inventory fences
    # ordinary writers. This is NOT a substitute for stopping every writer.
    for directory, dirs, names, fd in os.fwalk(root, follow_symlinks=False):
        for name in sorted(dirs):
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            _private(info, directory=True)
            relative = _name((Path(directory) / name).relative_to(root).as_posix())
            directories.append(relative)
            identities[relative] = (info.st_ino, info.st_mtime_ns, info.st_ctime_ns)
        for name in sorted(names):
            relative = _name((Path(directory) / name).relative_to(root).as_posix(), database=True)
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            _private(info)
            files.append(relative)
            identities[relative] = (info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        if len(files) + len(directories) > MAX_FILES:
            raise ValueError('Application state entry limit exceeded')
    return sorted(directories), sorted(files), identities


def _verify_sqlite(path):
    db = sqlite3.connect(Path(path).absolute().as_uri() + '?mode=ro&immutable=1', uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('Application database integrity check failed')
    finally:
        db.close()


def _decode(plaintext):
    if len(plaintext) > MAX_ENVELOPE:
        raise ValueError('Application archive size limit exceeded')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('Duplicate archive property')
            result[key] = value
        return result
    archive = json.loads(plaintext, object_pairs_hook=unique)
    if (type(archive) is not dict or set(archive) != {'version', 'directories', 'files'}
            or type(archive['version']) is not int or archive['version'] != 1):
        raise ValueError('Invalid application archive')
    dirs, files = archive['directories'], archive['files']
    if type(dirs) is not list or type(files) is not list or not files or len(dirs) + len(files) > MAX_FILES:
        raise ValueError('Invalid application archive entries')
    known = set()
    for directory in dirs:
        _name(directory)
        if directory in known: raise ValueError('Duplicate archive path')
        known.add(directory)
    directory_set = set(known)
    recovered, total = [], 0
    for item in files:
        if type(item) is not dict or set(item) != {'path', 'data', 'sha256'}:
            raise ValueError('Invalid application archive file')
        name = _name(item['path'], database=True)
        if name in known: raise ValueError('Duplicate archive path')
        known.add(name)
        data = base64.b64decode(item['data'], validate=True)
        total += len(data)
        if total > MAX_STATE or not data.startswith(b'SQLite format 3\0'):
            raise ValueError('Invalid or oversized application database')
        if type(item['sha256']) is not str or not compare_digest(sha256(data).hexdigest(), item['sha256']):
            raise ValueError('Application file digest mismatch')
        recovered.append((name, data))
    for name in known:
        for parent in PurePosixPath(name).parents:
            if str(parent) != '.' and str(parent) not in directory_set:
                raise ValueError('Missing archive parent directory')
    return dirs, recovered


def _materialize(plaintext, destination):
    dirs, files = _decode(plaintext)
    # Validate every SQLite file privately before creating the recovery destination.
    with tempfile.TemporaryDirectory(prefix='fg-state-verify-') as directory:
        for index, (_, data) in enumerate(files):
            path = Path(directory) / str(index)
            path.write_bytes(data); path.chmod(0o600); _verify_sqlite(path)
    destination = Path(destination).absolute()
    _root(destination.parent)
    destination.mkdir(mode=0o700)  # exclusive; never overwrite an existing directory
    marker = destination / REVIEW_MARKER
    with marker.open('x') as output:
        marker.chmod(0o600)
        output.write('Offline recovery only. Reconcile uncertain repairs, email and schedules before resuming.\n')
        output.flush(); os.fsync(output.fileno())
    for name in sorted(dirs, key=lambda p: (p.count('/'), p)):
        (destination / name).mkdir(mode=0o700)
    for name, data in files:
        fd = os.open(destination / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
    # Persist directory entries too. Failed/partial restores retain the blocking marker.
    for path in [*(destination / d for d in sorted(dirs, key=lambda p: -p.count('/'))), destination, destination.parent]:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    return {'scope': 'application_sqlite_state', 'verified': True, 'database_count': len(files),
            'resume_blocked': True, 'full_wordpress_backup': False}


def _manifest(manifest):
    if type(manifest) is not dict or set(manifest) != {'scope', 'deployment_id', 'key_id', 'object_id', 'ciphertext_sha256'}:
        raise ValueError('Trusted application recovery receipt required')
    deployment_id = _identifier(manifest['deployment_id'])
    if (manifest['scope'] != 'application_sqlite_state'
            or type(manifest['object_id']) is not str
            or not re.fullmatch('deployments/' + deployment_id + '/application-state-[0-9a-f]{32}\\.aesgcm', manifest['object_id'])
            or type(manifest['ciphertext_sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', manifest['ciphertext_sha256'])):
        raise ValueError('Invalid application recovery receipt')
    return (MAGIC + deployment_id.encode() + b'/' + manifest['key_id'].encode())


def recover_application_state(store, master_keys, manifest, destination):
    """Needs only trusted receipt, retained key and store, never the old host DB."""
    aad = _manifest(manifest)
    key = _key(master_keys, manifest['deployment_id'], manifest['key_id'])
    if Path(destination).exists() or Path(destination).is_symlink():
        raise ValueError('New recovery destination required')
    ciphertext = store.get(manifest['object_id'])
    if (type(ciphertext) is not bytes or not len(MAGIC) + 28 < len(ciphertext) <= MAX_ENVELOPE
            or not ciphertext.startswith(MAGIC)
            or not compare_digest(sha256(ciphertext).hexdigest(), manifest['ciphertext_sha256'])):
        raise ValueError('Application ciphertext integrity check failed')
    offset = len(MAGIC)
    try: plaintext = AESGCM(key).decrypt(ciphertext[offset:offset+12], ciphertext[offset+12:], aad)
    except Exception: raise ValueError('Application backup authentication failed') from None
    return _materialize(plaintext, destination)


def export_application_state(root, store, master_keys, *, deployment_id, key_id, quiesced=False):
    """ALL writers must be stopped; caller assertion is never proof of host quiescence."""
    if quiesced is not True: raise ValueError('Stop all writers before application backup')
    root = _root(root)
    key = _key(master_keys, deployment_id, key_id)
    dirs, names, identities = _inventory(root)
    if not names: raise ValueError('Application state is empty')
    records, total = [], 0
    for name in names:
        # Every ancestor was checked by inventory; repeat it before opening.
        path = root / name
        _root(path.parent)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd); _private(info)
            total += info.st_size
            if total > MAX_STATE: raise ValueError('Application state size limit exceeded')
            with os.fdopen(fd, 'rb', closefd=False) as source: data = source.read(MAX_STATE + 1)
            if len(data) != info.st_size: raise ValueError('Application state changed during backup')
        finally: os.close(fd)
        records.append({'path': name, 'data': base64.b64encode(data).decode(), 'sha256': sha256(data).hexdigest()})
    if _inventory(root) != (dirs, names, identities):
        raise ValueError('Application state changed during backup')
    plaintext = json.dumps({'version': 1, 'directories': dirs, 'files': records}, separators=(',', ':')).encode()
    # Upload only after a complete local independent validation.
    with tempfile.TemporaryDirectory(prefix='fg-state-probe-') as directory:
        _materialize(plaintext, Path(directory) / 'local')
        nonce = os.urandom(12)
        manifest = {'scope': 'application_sqlite_state', 'deployment_id': deployment_id, 'key_id': key_id,
                    'object_id': 'deployments/' + deployment_id + '/application-state-' + uuid.uuid4().hex + '.aesgcm',
                    'ciphertext_sha256': '0' * 64}
        ciphertext = MAGIC + nonce + AESGCM(key).encrypt(nonce, plaintext, _manifest(manifest))
        if len(ciphertext) > MAX_ENVELOPE: raise ValueError('Application archive size limit exceeded')
        manifest['ciphertext_sha256'] = sha256(ciphertext).hexdigest()
        store.put(manifest['object_id'], ciphertext)
        recover_application_state(store, master_keys, manifest, Path(directory) / 'readback')
    return manifest
