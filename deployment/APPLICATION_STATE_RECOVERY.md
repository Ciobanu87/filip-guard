# Offline encrypted application-state recovery

This supplements existing WordPress **content** backups. It does not provision a
host/bucket, retain keys for the operator, or create a full WordPress backup.
Real independent cloud-provider recovery and host reboot remain launch gates.

`operations_state_backup.py` reuses the existing explicitly configured S3 adapter
and versioned private master-key mounts. HKDF separates deployment-state keys
from customer credentials and content-backup keys. AES-GCM authenticates the
deployment ID and key version; a trusted private receipt pins the ciphertext hash
and object namespace. No production keys are generated or included in archives.

The state root must contain **all** configured SQLite databases: accounts,
customer/site registry, per-site application/proposal/repair journals, local
content-backup databases and receipts, monitoring schedules/history/outbox/quota,
and the existing AI usage/cache ledger. Check every configured path is under that
root before a drill. Files outside it are not included. Only private regular
SQLite files and private directories are accepted; unknown files, key mounts,
links, WAL/SHM/journal sidecars, corrupt databases, concurrent observed changes,
over 1,024 entries or over 32 MiB total state fail closed. Larger deployments
require an independently validated host snapshot procedure, not a raised limit
without review. No compression or unsafe archive extraction is used.

Before export, stop **all** UI/worker/CLI writers on the authorized host. The
`--writers-stopped` option is the operator's assertion, not an automatic proof of
quiescence. Individual database checks or file timestamps do not establish a
cross-database transaction snapshot while services are running. SQLite WAL must
be closed/checkpointed by its owning process before export; this tool never
deletes a journal to force a backup. Export once during the isolated recovery
drill; no paid service or production data is needed for synthetic validation.

With an existing private state root, separate private receipt directory, trusted
32-hex deployment identifier and authorized S3/key mounts:

```
python operations_state_backup.py export --authorized-external-access --writers-stopped --root /private/state --deployment-id DEPLOYMENT_ID --manifest /private/recovery/state-receipt.json
```

This validates every SQLite file locally, encrypts/uploads the snapshot and
downloads/decrypts/restores it independently before completing the receipt. A
failure retains an incomplete receipt and possibly an encrypted remote object;
no deletion or overwrite is attempted. A repeated export needs a **new** receipt
path. Keep the completed receipt and every required key version independently
of the application host; keys must also stay separate from the object bucket.
An uploaded object alone is not recovery proof and a receipt alone cannot
recover without the retained key and provider access.

On an isolated replacement host, without any old Streamlit session or account DB:

```
python operations_state_backup.py recover --authorized-external-access --manifest /private/recovery/state-receipt.json --destination /private/new-state
```

The destination must not exist. All decrypted database digests and SQLite
integrity checks pass **before** destination creation. Partial restores retain
`FG-RESTORE-REVIEW-REQUIRED`. Successful restores retain the same marker too:
application database entry points refuse to open restored state until operator
reconciliation. Recovery never contacts WordPress, sends mail or starts workers.

Do not remove the marker simply to make a health check pass. Review uncertain
repair outcomes against the authorized test WordPress, reconcile potentially
accepted email deliveries (a historical outbox snapshot can predate delivery),
check monitoring leases/next-due times, invalidate old sessions/approvals as
appropriate and preserve/reconcile the latest usage reservations. Restoring an
old AI ledger is **not** permission to reset provider budgets or repeat accepted
calls. Remain stopped until all discrepancies are resolved. Only the operator
then removes the marker and points a private isolated runtime to the restored
paths. No automated approval/resume command is provided.

Offline tests use synthetic databases/keys and simulated object storage. The CI
real-infrastructure job additionally exercises actual TLS/S3 upload/readback and
restoration with a fresh MinIO SDK client, synthetic accounts and blocked resume.
This proves an isolated real-service path, not a live cloud account, offsite key
custody, external mailbox, permanent host, power failure or 24/7 uptime.
