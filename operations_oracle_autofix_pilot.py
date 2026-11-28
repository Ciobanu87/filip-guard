"""Authorized read-only dependency admission before the approved private pilot."""
import json
import os
from pathlib import Path
from operations_oracle_ssh_probe import run_pinned_command


FIELDS={'schema','arm64','logical_cpus','shape_a1','imds_ocpus','imds_memory_gib','frankfurt_home_instance',
    'total_memory_mib','available_memory_mib','private_scratch_free_bytes','visible_block_devices_gib',
    'php_available','php_version','php_mysqli','sql_server_available','sql_initializer_available',
    'docker_available','podman_available','existing_python_available','all_guard_units_inactive',
    'server_modified','global_installations','public_listeners_created','groq_calls','smtp_messages','b2_calls'}

def assess(report):
    if type(report) is not dict or set(report)!=FIELDS or report.get('schema')!=1:raise ValueError('Invalid pilot readiness report')
    for field in ('server_modified',):
        if report.get(field) is not False:raise ValueError('Read-only boundary violated')
    for field in ('global_installations','public_listeners_created','groq_calls','smtp_messages','b2_calls'):
        if type(report.get(field)) is not int or report[field]!=0:raise ValueError('Read-only boundary violated')
    allocation=(report.get('arm64') is True and report.get('shape_a1') is True
        and type(report.get('imds_ocpus')) in (int,float) and report['imds_ocpus']==1
        and type(report.get('imds_memory_gib')) in (int,float) and report['imds_memory_gib']==6
        and report.get('frankfurt_home_instance') is True and type(report.get('visible_block_devices_gib')) is int
        and 0<report['visible_block_devices_gib']<=47)
    missing=[]
    if report.get('php_available') is not True:missing.append('PHP 8.3')
    elif not str(report.get('php_version','')).startswith('8.3.'):missing.append('PHP 8.3 runtime')
    if report.get('php_mysqli') is not True:missing.append('PHP mysqli')
    if report.get('sql_server_available') is not True:missing.append('isolated SQL server binary')
    if report.get('sql_initializer_available') is not True:missing.append('private SQL data-directory initializer')
    if report.get('existing_python_available') is not True:missing.append('existing Python application runtime')
    capacity=(type(report.get('private_scratch_free_bytes')) is int and report['private_scratch_free_bytes']>=7*1024**3
        and type(report.get('available_memory_mib')) is int and report['available_memory_mib']>=2048)
    eligible=allocation and capacity and report.get('all_guard_units_inactive') is True and not missing
    return dict(status='dependencies-ready-for-private-pilot' if eligible else 'pilot-held',
        allocation_within_current_free_limits=allocation,account_billing_polled=False,
        owner_account_evidence_reused=True,max_monthly_ocpu_hours=744,max_monthly_memory_gib_hours=4464,
        free_allowances_used={'ocpu_hours':1500,'memory_gib_hours':9000,'boot_block_gib':200},
        capacity_sufficient=capacity,missing_dependencies=missing,pilot_executed=False,
        evidence_scope='read-only-host-admission-only',checks=report)


def main():
    try:
        source=Path(__file__).with_name('deployment').joinpath('oracle_autofix_pilot_inspect.py').read_text()
        report=json.loads(run_pinned_command("python3 - <<'FG_PILOT_READONLY'\n"+source+"\nFG_PILOT_READONLY"))
        result=assess(report)
    except Exception:
        print(json.dumps({'status':'read-only-admission-unverified','pilot_executed':False,'server_modified':False}));return 1
    print(json.dumps(result,sort_keys=True))
    native=(result['allocation_within_current_free_limits'] and result['capacity_sufficient'] and report.get('all_guard_units_inactive') is True and report.get('existing_python_available') is True)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as output:output.write('native_eligible='+str(native).lower()+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
