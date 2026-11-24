"""Read explicitly mounted secrets; no generation, logging or ambient lookup."""
import os
import re
import stat
from pathlib import Path


def private_file(path,limit):
    flags=os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
    try:
        fd=os.open(os.fspath(path),flags)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_size>limit:
                raise ValueError('Private operator configuration required')
            with os.fdopen(fd,'rb',closefd=False) as source:data=source.read(limit+1)
            if len(data)>limit:raise ValueError('Private operator configuration required')
            return data
        finally:os.close(fd)
    except OSError:
        raise ValueError('Private operator configuration unavailable') from None


class MountedKeyring:
    """Versioned raw 256-bit files in an externally retained private directory.

    Old versions stay readable for existing credentials/archives. Changing active
    version never deletes, rewrites or generates any key.
    """
    def __init__(self,directory,active_key_id):
        self.directory=Path(directory);self.active_key_id=active_key_id
        self._identifier(active_key_id)
        if self.directory.is_symlink() or not self.directory.is_dir() or self.directory.stat().st_mode & 0o077:
            raise ValueError('Private mounted key directory required')
        self(active_key_id)
    @staticmethod
    def _identifier(value):
        if type(value) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',value):raise ValueError('Invalid key version')
    def __call__(self,key_id):
        self._identifier(key_id)
        key=private_file(self.directory/(key_id+'.key'),32)
        if len(key)!=32:raise ValueError('Externally retained 256-bit key required')
        return key


def configured_master_keys(environ=None):
    env=os.environ if environ is None else environ
    key_id=env.get('FG_GUARD_KEY_ID','test-v1')
    if env.get('FG_GUARD_KEY_DIRECTORY'):
        return MountedKeyring(env['FG_GUARD_KEY_DIRECTORY'],key_id)
    path=env.get('FG_GUARD_MASTER_KEY_FILE')
    if not path:raise ValueError('External key custody is not configured')
    MountedKeyring._identifier(key_id)
    def provider(requested):
        if requested!=key_id:raise PermissionError('Requested key version unavailable')
        key=private_file(path,32)
        if len(key)!=32:raise PermissionError('Externally retained 256-bit key required')
        return key
    provider(key_id)
    return provider
