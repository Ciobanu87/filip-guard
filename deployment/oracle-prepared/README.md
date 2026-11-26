# Existing Oracle host: prepared, NOT installed or activated

Scope: `Ciobanu87/filip-guard`, `filip-guard-development` only. No resource
provisioning, new VM/volume, public listener, subscription, paid service, production
merge, AI call or production-key generation is performed by these files.

## Evidence already obtained

- Pinned ED25519 SSH identity/authentication succeeded in Actions run
  https://github.com/Ciobanu87/filip-guard/actions/runs/45822492031
- Read-only host inventory succeeded in Actions run
  https://github.com/Ciobanu87/filip-guard/actions/runs/45824514553
- Oracle Linux 9 / ARM64, one logical CPU, 5,642 MiB visible memory, systemd.
- `/srv` currently uses XFS: 29 GiB filesystem total / 19 GiB available.
  These are guest filesystem figures, NOT the OCI boot-volume size, storage pool,
  allocation/performance tier or account bill. No resize/repartition is proposed.
- SELinux enforcing and firewalld active. Password SSH authentication disabled;
  public-key authentication enabled; root policy `without-password` permits keys.
  Do not describe this as root login completely disabled.
- Python 3.11, Docker and Podman are absent. The guard state directory is absent;
  neither named guard service is active. Their existence/loading was not proved.
- Existing B2 synthetic encrypt/upload/download/recovery and Groq 9/9 acceptance
  remain prior completed evidence. They were not repeated by these workflows.

## Prepared file layout

| Path on existing host | Purpose / owner |
| --- | --- |
| `/opt/filip-guard` | Pinned development source and `.venv`, root-controlled, app cannot modify code |
| `/etc/filip-guard` | Root-controlled config, approval and backup reservation journal |
| `/etc/filip-guard/secrets` | Existing operator-owned key/credential mounts; no new keys |
| `/srv/filip-guard/state` | Shared UI/worker SQLite root, `filipguard`, directory 0700 / files 0600 |
| `/srv/filip-guard/state/accounts.sqlite` | Existing accounts/sessions |
| `/srv/filip-guard/state/sites` | Existing site registry and per-site journals |
| `/srv/filip-guard/state/monitor.sqlite` | Schedules/history/outbox/email quota |
| `/srv/filip-guard/state/advisor.sqlite` | Original AI cache/usage/cooldown ledger; never reset/reconstruct |
| `/srv/filip-guard/recovery` | Private trusted recovery receipts, outside state, `filipguard`, 0700 |

Use the existing local filesystem after account verification. No separate volume,
network filesystem, database service or storage subscription is necessary for
this prepared layout. Recheck its backing device/mount on activation and after
reboot; an XFS label alone is not provider durability/billing evidence.

## Zero-cost activation gate

`operations_host_gate.py` checks a root-controlled regular approval file. The
example is deliberately invalid: it contains `false`/`null`, not assumed zeroes.
It is not copied onto the host or auto-filled. The retained evidence hash must
reference actual resource/usage evidence; it cannot be invented from this report.
Review all relevant regions/compartments, home region, image eligibility, allocated
boot/block volumes (including detached volumes), performance settings, volume
backups and cumulative/projected full-month A1 usage, plus other billable services.
The prepared ceilings are conservative: 1,500 OCPU hours / 9,000 GiB hours,
200 GiB combined boot/block storage and five volume backups; stop on conflicting
account-specific terms. Confirm current and projected billable cost is zero.

Approval also requires verified B2 zero-spend limits and free account headroom,
including existing versions/objects and usage from other applications. At least
384 MiB headroom is reserved for this short approval window. Approval expires in
at most seven days and is never renewed automatically. This is a deliberate
fail-closed pilot: without fresh evidence, backups stop and service restart is
blocked; this does not claim unattended perpetual zero-cost hosting.

No shell flag can bypass the gate. Fixed host/state paths and existing private
SQLite schema are checked. A missing original AI ledger or partial deployment
must be recovered/reconciled; the gate never initializes them. All global
AI/email/registration/test/backup flags in `runtime.env.example` remain off.
There is no deployment/installation workflow and no scheduled SSH workflow.

## Later execution sequence — blocked until real zero-cost verification

These are implementation instructions for the agent, not commands the owner
needs to type on a phone. None have been executed on the Oracle host.

1. Retain account-level evidence and record its hash, time and expiry in the
   approval; distinguish infrastructure installation permission from later
   customer repairs, external email, public access and AI usage consent.
2. With the existing pinned SSH identity, inventory installed official package
   candidates and reviewed updates. Use Oracle's official Python 3.11 packages
   and an isolated venv matching the existing CI runtime. Do not replace the
   system `python3`/Oracle 3.9 or add EPEL/container repositories just for this.
   Install application requirements only into `/opt/filip-guard/.venv` from the
   reviewed development snapshot. Root owns code; app runs as a dedicated
   `filipguard` user with no interactive shell and no sudo rights.
3. Prepare the private layout above on the existing persistent filesystem.
   Preserve existing state byte-for-byte, including the AI usage ledger.
   If state is recovered, keep `FG-RESTORE-REVIEW-REQUIRED` and remain stopped
   until recovery reconciliation is complete. Do not initialize empty stores
   over partial data or use 9/9 reports to invent missing AI budget history.
4. Mount existing retained key versions and bucket-scoped B2 credentials at
   private paths readable only by the app/root, outside the SQLite snapshot.
   Verify separately retained key/receipt custody. Never copy GitHub secret
   values into source, command arguments, logs, artifacts or this document.
   Root-owned `runtime.env` contains only explicit nonsecret config/paths.
5. Retain the current SSH session and a recovery route. Save the original SSH
   config, review include/Match precedence, stage `sshd-hardening.conf.example`,
   run `sshd -t` and inspect effective configuration for both `opc` and `root`.
   Reload only if the target settings take effect; test a second pinned `opc`
   connection before closing the first. Roll back the saved config on failure.
   Do not alter keys, firewall exposure or Oracle security lists. Keep SELinux
   and firewalld enabled. An unverified drop-in is not a completed hardening.
6. Review/install the three named services and timer only after the gate passes.
   UI binds only `127.0.0.1:8501`; verify it is not listening publicly. Existing
   verified HTTPS ingress remains a separate gate before remote account use.
   Validate private SQLite ownership/locking; start the UI and read-only worker
   explicitly. Confirm worker heartbeat/history across a controlled restart
   and reboot on the same paths; verify the original ledger is unchanged.
7. Explicitly initialize the root-owned reservation journal from the empty
   example ONLY for this first deployment, after proving there is no previous
   journal to recover. Once used, never replace it with an empty template.
   Review direct/other writers: only the two managed cgroups may write state.
   Exporter rejects other processes running as the dedicated app user; do not
   grant other users write access to the state root or run untracked CLI writers.
8. Authorize one host-level backup drill; turn on only its backup flag. Run the
   prepared backup service, then use its completed trusted receipt with the
   existing offline recovery tool into a NEW isolated destination. Confirm
   accounts, tenant isolation, history/outbox and original AI reservations;
   keep restored state held. This last independently operated recovery/custody
   drill is still NOT completed by prior synthetic B2 evidence.
9. Only after that drill, enable the timer. Confirm next trigger, systemd
   result, completed receipt and journal reservation. No remote deletion or
   automatic retention policy is introduced. Read sanitized service status
   after the first actual scheduled run. Email incident notification remains
   blocked until the existing email validation/authorization roadmap step.

Official Python reference reviewed for preparation:
https://docs.oracle.com/en/operating-systems/oracle-linux/9/python/python-InstallingPython.html
Oracle notes versioned Python streams have their own maintenance lifecycles;
review the supported official package candidate at installation time.

## Automatic backup behavior and failure handling

The timer example proposes daily 03:00 UTC with up to ten minutes jitter and no
missed-run catch-up on reboot. It is NOT installed/enabled. Running
`python operations_scheduled_state_backup.py` without `--execute` is inert.
The explicit execution path requires valid approval and backup authorization.

The root controller holds an exclusive lock, durably reserves a maximum 48 MiB
attempt, permits only one attempt per UTC day and at most seven per approval
window, and never refunds uncertain writes. Missing/corrupt reservation history
blocks the operation. Existing provider cap/headroom confirmation is still
required; local reservations cannot measure another application's provider use.

It records which of the two exact services were active, stops their cgroups,
verifies both are inactive and rejects other app-user processes before export.
The existing exporter runs as `filipguard`; it reuses AES-GCM/HKDF and performs
upload/readback/decrypt/SQLite recovery verification before returning a receipt.
A timeout kills/reaps the dedicated exporter process group before returning.
Previously active services are restarted even after an ordinary backup failure;
previously inactive services remain inactive. Failed resume is reported as a
failure, never a successful backup. Power loss, SIGKILL or systemd/controller
crash is not an ordinary recoverable exception: retain evidence and review
service state before manual resume. No host uptime/reboot success is claimed.

Failure leaves failed systemd status / incomplete receipt evidence. It does not
reset budgets, retry uploads, delete remote objects, replace keys, restore over
live state, remove a restore hold or send mail. Recovery remains an explicit
isolated operator action. The existing state snapshot limits (32 MiB/1,024
entries) remain unchanged; exceeding them blocks backup rather than omitting
state. Stop and resolve failed/expired backup protection before permitting repairs.

Completed receipts, original key versions, latest AI ledger and the root backup
reservation journal require separately retained recovery custody. A daily state
archive alone is insufficient to recover uploads made since that snapshot or
reconcile uncertain reservations. After host loss, do not reset the journal or
re-enable AI without reconciling current provider usage.

## Current remaining external gates

- Actual Oracle account/resource/usage evidence for all zero-cost conditions.
- Existing private state/AI ledger, deployment identifier and independently
  retained keys/receipts transferred safely after infrastructure authorization.
- Real host installation, reboot validation, recovery/custody drill, first timed
  backup and real email delivery validation; none are claimed complete here.

The code and units are prepared and tested locally/CI; they are not installed
on the server. No request for passwords/keys in chat is necessary.
