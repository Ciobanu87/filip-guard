"""Fixed read-only admission: no file writes, packages, services or provider APIs."""
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import urllib.request


def command(args):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=4)
        return p.stdout[:4096].strip() if p.returncode==0 else ''
    except (OSError,subprocess.TimeoutExpired):return ''


def locate(names,paths=(),packages=()):
    for name in names:
        found=shutil.which(name)
        if found:return found
    for path in paths:
        if Path(path).is_file() and os.access(path,os.X_OK):return path
    # RPM database lookup is read-only; never install/enable repositories.
    for package in packages:
        for path in command(['rpm','-ql',package]).splitlines():
            if path.startswith('/') and Path(path).name in names and Path(path).is_file() and os.access(path,os.X_OK):return path
    return None


def inspect():
    instance={}
    try:
        request=urllib.request.Request('http://169.254.169.254/opc/v2/instance/',headers={'Authorization':'Bearer Oracle'})
        with urllib.request.urlopen(request,timeout=2) as response:instance=json.loads(response.read(65536))
    except Exception:pass
    shape=instance.get('shapeConfig',{})
    if type(shape) is not dict:shape={}
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    fs=shutil.disk_usage(str(Path.home()))
    php=locate(('php','php8.3','php83'),('/usr/bin/php','/usr/local/bin/php','/opt/remi/php83/root/usr/bin/php'),('php-cli','php83-php-cli'))
    php_data={}
    if php:
        try:php_data=json.loads(command([php,'-r','echo json_encode(array("version"=>PHP_VERSION,"mysqli"=>extension_loaded("mysqli")));']))
        except Exception:pass
    version=php_data.get('version','')
    version=version if type(version) is str and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+.a-zA-Z0-9]*)',version) else None
    server=locate(('mariadbd','mysqld'),('/usr/libexec/mariadbd','/usr/libexec/mysqld','/usr/sbin/mariadbd','/usr/sbin/mysqld','/usr/local/mysql/bin/mysqld','/usr/local/mariadb/bin/mariadbd'),('mariadb-server','mysql-server','mysql-community-server'))
    sql_server=bool(server)
    sql_version=command([server,'--no-defaults','--version']) if server else ''
    builtin_init=bool(server and re.search(r'\bVer 8\.',sql_version) and 'MariaDB' not in sql_version)
    sql_init=bool(locate(('mariadb-install-db','mysql_install_db'),('/usr/bin/mariadb-install-db','/usr/bin/mysql_install_db','/usr/local/mysql/scripts/mysql_install_db'),('mariadb-server','mysql-server')))
    units=('filip-guard-ui.service','filip-guard-worker.service','filip-guard-state-backup.service','filip-guard-state-backup.timer')
    # systemctl exits nonzero for inactive units; explicitly read its stdout here.
    states=[]
    for name in units:
        try:states.append(subprocess.run(['systemctl','is-active',name],capture_output=True,text=True,timeout=3).stdout.strip())
        except Exception:states.append('unknown')
    block_gib=None
    try:
        devices=json.loads(command(['lsblk','-b','-J','-o','TYPE,SIZE']))['blockdevices']
        sizes=[int(d['size']) for d in devices if d['type']=='disk']
        if sizes:block_gib=math.ceil(sum(sizes)/(1024**3))
    except Exception:pass
    return dict(schema=1,arm64=platform.machine()=='aarch64',logical_cpus=os.cpu_count(),
        shape_a1=instance.get('shape')=='VM.Standard.A1.Flex',
        imds_ocpus=shape.get('ocpus') if type(shape.get('ocpus')) in (int,float) and math.isfinite(shape['ocpus']) else None,
        imds_memory_gib=shape.get('memoryInGBs') if type(shape.get('memoryInGBs')) in (int,float) and math.isfinite(shape['memoryInGBs']) else None,
        frankfurt_home_instance=any(instance.get(key)=='eu-frankfurt-1' for key in ('region','canonicalRegionName')),
        total_memory_mib=int(memory['MemTotal'].split()[0])//1024,
        available_memory_mib=int(memory['MemAvailable'].split()[0])//1024,
        private_scratch_free_bytes=fs.free,visible_block_devices_gib=block_gib,
        php_available=bool(php),php_version=version,php_mysqli=php_data.get('mysqli') is True,
        sql_server_available=sql_server,sql_initializer_available=sql_init or builtin_init,
        docker_available=bool(shutil.which('docker')),podman_available=bool(shutil.which('podman')),
        existing_python_available=Path('/opt/filip-guard/.venv/bin/python').is_file(),
        all_guard_units_inactive=all(state in ('inactive','failed','unknown') for state in states) and 'unknown' not in states,
        server_modified=False,global_installations=0,public_listeners_created=0,groq_calls=0,smtp_messages=0,b2_calls=0)


if __name__=='__main__':print(json.dumps(inspect(),sort_keys=True))
