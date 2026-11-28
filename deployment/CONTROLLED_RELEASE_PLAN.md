# Controlled validation and Oracle installation plan

Prepared only. Do not execute these stages merely because this file exists.
Budget ceiling remains zero; existing VM/47 GB volume only; no `main` change,
new provider, upgrade, extra resource, new SSH key or AI budget reset.

## 0. Freeze and review the development candidate

Record the exact development commit and its successful five CI jobs. Preserve
historical nine-case Groq results, provider reconciliation and all daily counters.
New code must not be mixed with an unreviewed branch head. Review the scope matrix
in `../RELEASE_READINESS.md`; unresolved functional gaps are release blockers.

Offline regression is the existing `.github/workflows/tests.yml`: core/Streamlit
contracts; real disposable WordPress/PHP/database fixtures; local S3/TLS SMTP;
container persistence; isolated worker/process recovery. New targeted commands:

```sh
python -m unittest test_public_scan_workflow test_prelaunch_system_flow test_complex_validation_readiness -v
python advisor_complex_evaluation.py
python validate_complex_advisor.py
```

The last command must report `approval-required` without constructing a provider,
reading its key, creating receipts, calling an API or touching the production DB.
No original live validation or Oracle reboot needs repetition for this step.

## 1. Prepared installation stage: current source with services still held

Use the existing pinned SSH route, `opc`, the verified Environment and development
branch only. Verify—not print—private mounts and owner custody. Confirm all four
units remain inactive and disabled/static and no application writer runs. Abort
on unexpected state, approvals, symlinks, active units or changed host identity.

The last confirmed installed application snapshot was
`4c729591d831188c7b6cfa4119c929ba0bfe4e20`; later operational helpers were installed
separately. Do not mistake the repository's current head for installed code.

Retain a root-private rollback copy of installed source only, excluding the venv,
secret mounts, credentials and customer data. Prepare a clean tracked development
source archive with an independently checked SHA-256; never package the whole
host or untracked private files. Copy only reviewed source paths while all writers
are held, preserving root ownership and permissions. Keep the existing venv and
review any dependency differences before installation. Never run arbitrary setup
scripts. Compile/import/smoke-test only against disposable fixtures first. Do not
write a host approval, flip provider/backup/email authorization, open a port,
reload changed units or enable/start/reboot a service as part of this source step.
Failure restores the retained source; it does not delete/reset persistent state.

## 2. Prepared explicit first account/site/monitor state provisioning

At the last real recovery validation, the state root contained the AI ledger only.
Reinspect actual state at the installation stage; do not infer loss from missing expected
files or initialize over an existing/partial account/site/monitor deployment.
The existing `operations_guard_setup.py --initialize-read-only` supports explicit
first provisioning of those three components. It creates no customer, key or
network call and refuses partial existing component sets. Preserve the separate
reconciled AI ledger byte-for-byte; never create a replacement AI budget.

Run the existing read-only state/schema/AI-history checks and verify permissions,
restore-review markers and distinct DB paths. Review every intermediate tenant
directory as well: new code creates each at 0700 and refuses existing nonprivate
or symlinked workspace directories. Do not silently chmod, follow links or reset
state to get past this check. Prepare account policy/registration
and owner test identity explicitly. Optional verification/recovery is implemented
but remains off (`FG_ACCOUNT_RECOVERY_AUTHORIZED=0`); do not claim that offline
tests verified a real mailbox or completed customer onboarding. Follow
`../ACCOUNT_RECOVERY.md`; its additive tables belong to the existing auth DB and
must be included in a later full-state recovery proof. After real state changes, obtain a bounded
fresh encrypted recovery proof using current saved zero caps/headroom and retained
master custody. The earlier one-DB drill is not proof for databases created later.

## 3. Separate approval: authorized live read-only validation

Use owner-controlled explicit origins and public idempotent endpoints only.
Confirm domain/site ownership first. Initial combined guard drill: one origin,
maximum 20 shared request admissions and 60 seconds; no checkout/authenticated API,
DNS changes, repair, mail or inference. Keep failed/unknown checks unverified.
Compare actual observations, tenant isolation, history and resolution scopes with
the operator's expected fixture conditions. Stop at the first security/permission
failure. No automatic retry loop or scans of uninvolved customer sites.

## 4. Separate approval: at most five NEW synthetic Groq cases

Keep Groq; reconfirm the current free account/budget/consent without a key probe.
Use the existing mounted key and strictly existing reconciled ledger. Do not
change the service's disabled flags just to run a CLI. An operator may supply a
reviewed isolated CLI environment only after approval. The prepared command is:

```sh
python validate_complex_advisor.py --allow-live --receipt-directory OWNER_PRIVATE_NEW_DIRECTORY
```

The current-provider factory must succeed with all existing free-plan, cloud-data
consent and AI authorization prerequisites, within the existing 20/day ceiling.
Maximum five new case admissions, 1,200 output tokens each, existing request
timeout and provider pacing; no other provider/fallback API, automatic retry,
credential rotation or daily reset. A receipt is reserved/fsynced before analysis.
An uncertain previous attempt holds; an accepted contract with irrelevant evidence
also stops. Retain every partial result and its private review excerpts/solutions. CLI output
contains summaries only; key values and raw provider errors are never printed. Do not rerun the original nine cases.
Observable fixture gates are not independent human semantic approval; review the
actual new evidence selections and language/safety outcomes separately.

## 5. Separate approvals: isolated WordPress and real email

WordPress: an explicitly authorized disposable nonproduction site, verified HTTPS,
current companion, scoped Application Password and isolated owner account. Test
one supported link replacement, verified external content backup, concurrent-edit
conflict, post-write verification, separate restore approval and monitor outcome.
Do not enable the companion for production or expand `.test` mutation scope.
Actual hosting/plugin compatibility is not established by the prior CI fixture.
The current mutation UI accepts only `.test` origins and has no approved general
external-staging activation path. Resolve/review that functional boundary and the
compatibility profile in `../WORDPRESS_COMPATIBILITY_PROFILE.md` before proposing a real external staging trial; an approval
alone must not be treated as code support for an otherwise rejected origin.

Email: owner-confirmed free SMTP account, authenticated sender and consenting owner
recipient; approve one bounded real delivery using existing TLS transport and
retained outbox reservation. Account verification/recovery must separately opt in
with the existing retained master, private account state and shared SMTP cap.
Verify the mailbox, expiry/single use, password reset and revoked sessions using
an owner-controlled test account; do not use a real customer or bypass mailbox
loss. No customer mailing, subscription upgrade or secret
in chat/repository/logs. Check real delivery, error reporting and no blind retry.

## 6. Final explicit approval: controlled service activation

Only after the applicable functional/privacy/account/compatibility and validation
gates have passed. Prepare a concrete root-private, short-lived host approval
using current Oracle/B2 evidence; never mark an unknown gate true. The existing
`operations_host_gate.py` must pass without modification. Keep production WordPress
mutations disabled until their separate unresolved compatibility review is closed.

Keep the UI on loopback until an approved verified HTTPS ingress or private
encrypted access method is available; no domain purchase/new paid resource is
allowed. Approve individually the UI listener/access/TLS mode, monitoring worker, optional
AI use with data consent, optional email, and backup service/timer. Start only the
approved subset and verify health, nonroot execution, authorization, leases,
private persistence and recovery. Do not use service activation as a prerequisite
to preparing these decisions. Paid services/resources remain forbidden.

Rollback criteria: identity/permission failures, missing ledger/state, failed
backup authentication, unverified scope resolution, exposed secret, unexpected
provider/cost signal, uncertain write or failed health/persistence check. Stop the
affected approved units; retain the journal and consumed reservations, keep the
restore hold and reconcile manually. Never blindly retry writes, overwrite newer
WordPress content, rotate/delete retained keys or reset a budget to get green.

Commercial billing, legal/privacy/retention and production customer AutoFix remain
separate incomplete release work. This plan does not authorize them or claim that
approval alone resolves missing functionality.


## Interrupted AutoFix: held, read-only reconciliation

`preparing_backup` is a durable claim before external backup I/O. A process death
must not trigger another upload or write. `applying` and unknown/rollback outcomes
likewise remain held; matching current content is not proof of operation ownership.
The owner-only recovery review can read the current authorized resource and return
content/version comparisons, retained backup ID and unchanged hold. It cannot
clear the journal, authorize a retry, auto-restore or claim external backup
availability. For a held preparation with no returned backup ID, inspect the
existing private backup receipts/object history; never infer that no archive exists.
Ordinary caught backup failures remain prewrite and permit the existing explicit
caller retry; no automatic retry is introduced. Actual backup/recovery writes,
service starts and any WordPress intervention still need separate approval.
