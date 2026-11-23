"""Fetch pinned official test dependencies, checking their recorded SHA-256."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
import sys
from urllib.request import urlopen
import zipfile

DEPENDENCIES = (
    ('wordpress.zip', 'https://wordpress.org/wordpress-7.1.5.zip',
     'cd44160a3fcce179fe170331132fcfc05e84e2f9284e2aad38df2aea6edaeab1'),
    ('wp-cli.phar', 'https://github.com/wp-cli/wp-cli/releases/download/v2.12.0/wp-cli-2.12.0.phar',
     'ce34ddd838f7351d6759068d09793f26755463b4a4610a5a5c0a97b68220d85c'),
)


def main(destination):
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    def fetch(dependency):
        name, url, checksum = dependency
        with urlopen(url, timeout=45) as response:
            content = response.read(80 * 1024 * 1024)
        if sha256(content).hexdigest() != checksum:
            raise RuntimeError('Official test dependency checksum mismatch: ' + name)
        (root / name).write_bytes(content)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(fetch, DEPENDENCIES))
    with zipfile.ZipFile(root / 'wordpress.zip') as archive:
        for name in archive.namelist():
            if not name.startswith('wordpress/') or '..' in Path(name).parts:
                raise RuntimeError('Unexpected archive path')
        archive.extractall(root)
    print('Verified WordPress 7.1.5 and WP-CLI 2.12.0 test dependencies.')


if __name__ == '__main__':
    main(sys.argv[1])
