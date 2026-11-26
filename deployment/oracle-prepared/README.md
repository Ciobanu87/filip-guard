# Existing Oracle host: runtime installed; application services held inactive

Scope: `Ciobanu87/filip-guard`, `filip-guard-development` only. No resource
provisioning, new VM/volume, public listener, subscription, paid service, production
merge, AI call or production-key generation is performed by these files.

## Current completed host work — 2026-11-26

The owner explicitly confirmed only this VM, its 47 GB boot volume and required
networking were created, with no other instances, volumes, volume backups or
additional cloud services. Combined with the accepted screenshots and existing
identity home-region read, this closes the Oracle inventory clarification.
The full 31-day projection is at most 744 OCPU-hours / 4,464 GiB-hours for this
unchanged 1 OCPU / 6 GB allocation; this is a conservative allocation projection,
not a fabricated populated billing report. No cloud resource/shape/storage size
was changed.

Actual installation snapshot:
`4c729591d831188c7b6cfa4119c929ba0bfe4e20` on the development branch.
Actions https://github.com/Ciobanu87/filip-guard/actions/runs/45833280508 verified:
Python 3.11, isolated venv/dependencies, dedicated nonroot account, private
persistent directories, installed but disabled UI/worker/backup units, actual
public Scanner UI rendering and temporary loopback health. Existing application
state remained unchanged; accounts/AI ledger were not initialized. System Python
was not replaced. No external backup or inference call occurred.

Security orchestration snapshot:
`e1533e7c9ac555cac00c73bfebbbad5385769550`.
Actions https://github.com/Ciobanu87/filip-guard/actions/runs/45834496272 verified:
root SSH login disabled, password/interactive authentication disabled, a new
independent pinned `opc` connection, cancelled timed rollback, actual controlled
host reboot, durable proof survival, unchanged state, SELinux enforcing and
firewalld active. No additional reboot is needed to repeat this completed proof.

`operations_oracle_b2_mount.py` now configures only existing repository-secret
B2 values via pinned encrypted SSH stdin, root-controlled private storage and a
0400 application-readable credential file. It constructs the existing adapter
as the app user without a network request, new key or upload. It refuses to
replace different existing credentials/settings. The backup authorization flag
and timer remain off; configuration is not a fresh B2 recovery test.

The deployed full UI/worker gate is still held. Original AI usage SQLite state,
application master-key custody, independent host-level recovery and current B2
zero-spend/headroom evidence are not fabricated by this infrastructure setup.
The earlier Colab ledger-loss limitation in `../GROQ_REPORT_RECOVERY.md` remains
in force: reports/9 accepted cases are not a replacement ledger. No local original
SQLite ledger was found in the existing FILIP GUARD workspaces during this step.

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
- Before installation, Python 3.11, Docker and Podman were absent and the guard
  state directory was absent. The completed host work above supersedes that snapshot.
- Existing B2 synthetic encrypt/upload/download/recovery and Groq 9/9 acceptance
  remain prior completed evidence. They were not repeated by these workflows.

## Additional owner evidence accepted on 2026-11-26

`owner-evidence-20261126.json` records the six supplied screenshots by SHA-256
and stores only nonsecret reviewed facts. Original screenshots, subscription IDs
and OCIDs are not committed. The owner confirms no paid upgrade; the screenshots
show a Free Tier account with the trial active, the same Frankfurt A1 allocation,
an explicitly Always Free 47 GB boot volume, Balanced 10 VPU/GB, no performance
auto-tuning, no cross-region replication and no scheduled boot backup policy.
Do not ask the owner to provide those same detail pages again.

The usage view displays zero RON consumption/overage AND no usage data, zero SKUs
and zero regions for the selected current-day range. Preserve that distinction:
it is not a populated account-wide zero-cost audit. Oracle documents delayed
reporting; do not replace unknown aggregate usage with zero. Conversely, do not
require a later billing screenshot if a complete resource/usage inventory and
conservative full-month projection independently establish free eligibility.

The Always Free volume label in Frankfurt also supports home-region eligibility
for that volume under Oracle's documented rule; the separate explicit home-region
field has not been seen. The outstanding scope is account-wide A1 allocation/use,
all allocated boot/block volumes (including detached ones), and backup counts
across relevant compartments/regions. Do not silently substitute this single
volume's 47 GB for an aggregate total.

`operations_oracle_account_access.py` adds a fixed pinned read-only check using
only an ALREADY installed OCI SDK/CLI and the instance's EXISTING identity. It
never installs tooling, reads user API-key config, creates a dynamic group or
changes IAM. Missing tooling, failed existing authorization or an incomplete
region response remains an explicit blocker. A successful region read alone
still does not claim cumulative usage or full resource visibility.

Official references checked for this evidence review:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costanalysisoverview.htm
- https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/costusagereportsoverview.htm
- https://docs.oracle.com/en-us/iaas/tools/python/latest/api/signing.html

Separate live API evidence (Actions run
https://github.com/Ciobanu87/filip-guard/actions/runs/45829300370) now confirms
Frankfurt is the home region and the account has exactly one region subscription.
The SDK is already installed and existing instance-identity region reads work;
the CLI is absent. No new IAM permission was granted. Do NOT request a duplicate
home-region screenshot. `operations_oracle_resources.py` subsequently attempts
only bounded current compute/boot/block/volume-backup reads across compartments.
It stops on denied/incomplete access and discards partial counters; it does not
fall back to a root-only view and call it account-wide. Even a complete current
core allocation is separate from historical usage and unrelated service costs.

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

## Operational sequence — completed host steps above; remaining activation gates below

These are implementation instructions for the agent, not commands the owner
needs to type on a phone. The host installation, SSH hardening and reboot portions
are now completed as recorded above; do not repeat them. State recovery, production
key custody, full runtime activation and automatic backup remain held.

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

- Oracle eligibility for the unchanged existing host is now accepted from the
  combined screenshots, owner inventory confirmation and home-region API evidence;
  do not request the same clarification or repeat the denied account API reads.
- Existing private state/AI ledger, deployment identifier and independently
  retained keys/receipts transferred safely after infrastructure authorization.
- Host installation/reboot validation are complete. The recovery/custody drill,
  first timed backup and real email delivery validation remain incomplete.

The runtime source/units are installed on the existing server, but application
services/timer remain disabled pending the remaining state/custody gates. Never
request passwords, provider keys or master-key values in chat.
