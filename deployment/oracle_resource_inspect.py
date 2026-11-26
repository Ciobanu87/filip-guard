"""Bounded existing-identity read of current core allocations. No IAM writes.

Prints only aggregate counts; no OCIDs, names, keys, tokens or raw API errors.
An allocation snapshot does not prove historical usage or unrelated service cost.
"""
import json
import math
import os
import signal


def blank():
    return {'schema': 1, 'status': 'blocked', 'blocked_step': 'sdk-or-identity',
            'scope': 'current-compute-boot-block-and-volume-backups',
            'core_allocation_inventory_verified': False, 'compartments_checked': 0,
            'a1_instances': 0, 'other_instances': 0, 'a1_ocpus': 0.0, 'a1_memory_gib': 0.0,
            'boot_volume_gib': 0, 'block_volume_gib': 0, 'volume_backup_count': 0,
            'historical_usage_verified': False, 'all_service_costs_verified': False,
            'server_modified': False, 'iam_permissions_changed': False, 'groq_calls': 0}


def pages(method, **kwargs):
    rows = []; page = None
    for unused in range(4):
        response = method(**kwargs, **({'page': page} if page else {}))
        if not isinstance(response.data, list): raise ValueError('Unexpected response')
        rows.extend(response.data)
        if len(rows) > 1000: raise ValueError('Inventory bound reached')
        if not response.has_next_page: return rows
        page = response.next_page
    raise ValueError('Incomplete pagination')


def allocated(rows):
    return [row for row in rows if row.lifecycle_state != 'TERMINATED']


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10**6:
        raise ValueError('Unknown allocation')
    return value


def collect(identity, compute, block, tenancy):
    report = blank()
    try:
        report['blocked_step'] = 'region-subscriptions'
        regions = pages(identity.list_region_subscriptions, tenancy_id=tenancy)
        if len(regions) != 1 or not regions[0].is_home_region or regions[0].region_name != 'eu-frankfurt-1':
            raise ValueError('Scope is not the single verified home region')
        report['blocked_step'] = 'compartment-list'
        compartments = pages(identity.list_compartments, compartment_id=tenancy,
                             compartment_id_in_subtree=True, access_level='ANY')
        identifiers = {tenancy} | {row.id for row in compartments if row.lifecycle_state != 'DELETED'}
        if len(identifiers) > 16: raise ValueError('Compartment bound reached')
        report['blocked_step'] = 'availability-domain-list'
        domains = pages(identity.list_availability_domains, compartment_id=tenancy)
        if not 1 <= len(domains) <= 8: raise ValueError('Availability domains unverified')
        for compartment in sorted(identifiers):
            report['blocked_step'] = 'instance-list'
            instances = allocated(pages(compute.list_instances, compartment_id=compartment))
            for instance in instances:
                if instance.shape == 'VM.Standard.A1.Flex':
                    report['a1_instances'] += 1
                    report['a1_ocpus'] += number(instance.shape_config.ocpus)
                    report['a1_memory_gib'] += number(instance.shape_config.memory_in_gbs)
                else:
                    report['other_instances'] += 1
            report['blocked_step'] = 'boot-volume-list'
            for domain in domains:
                boots = allocated(pages(block.list_boot_volumes, compartment_id=compartment,
                                        availability_domain=domain.name))
                report['boot_volume_gib'] += sum(number(row.size_in_gbs) for row in boots)
            report['blocked_step'] = 'block-volume-list'
            volumes = allocated(pages(block.list_volumes, compartment_id=compartment))
            report['block_volume_gib'] += sum(number(row.size_in_gbs) for row in volumes)
            report['blocked_step'] = 'volume-backup-list'
            report['volume_backup_count'] += len(allocated(pages(block.list_boot_volume_backups, compartment_id=compartment)))
            report['volume_backup_count'] += len(allocated(pages(block.list_volume_backups, compartment_id=compartment)))
            report['compartments_checked'] += 1
        report.update(status='current-core-allocations-read', blocked_step='none',
                      core_allocation_inventory_verified=True)
    except Exception:
        # Partial counters are not evidence of a complete total. Drop them.
        blocked = report['blocked_step']
        report = blank(); report['blocked_step'] = blocked
    return report


def inspect():
    def timeout(*unused): raise TimeoutError('Read-only inventory timeout')
    signal.signal(signal.SIGALRM, timeout); signal.alarm(26)
    try:
        import oci
        os.environ['OCI_METADATA_BASE_URL'] = 'http://169.254.169.254/opc/v2'
        retry = oci.retry.NoneRetryStrategy()
        signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner(federation_client_retry_strategy=retry)
        options = {'signer': signer, 'timeout': (3, 5), 'retry_strategy': retry}
        config = {'region': 'eu-frankfurt-1'}
        return collect(oci.identity.IdentityClient(config, **options), oci.core.ComputeClient(config, **options),
                       oci.core.BlockstorageClient(config, **options), signer.tenancy_id)
    except Exception:
        return blank()
    finally:
        signal.alarm(0)


if __name__ == '__main__': print(json.dumps(inspect(), sort_keys=True))
