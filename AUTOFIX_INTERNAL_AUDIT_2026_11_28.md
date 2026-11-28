# Internal technical audit — 2026-11-28

Scope: development source after `1265e04`, disposable state and isolated CI.
This is an internal review, not an independent security certification or a
production-readiness declaration. No `main`/Oracle change, live provider request,
customer-site intervention, new paid resource or service activation is included.

| Concrete finding | Change | New evidence |
| --- | --- | --- |
| Concurrent apply calls could both create backups before one won the write claim | Atomically reserve `preparing_backup` before any backup upload; retain a durable backup reference as soon as returned | Concurrent blocking-backup test proves one backup; process-death tests prove restart does not upload/write again |
| A process death after approval consumption could leave no explicit execution phase | Preparation is already held before consumption and advances to `applying` only after it | Crash after token consumption keeps the verified backup reference; no repeat consumption/write |
| A malformed write receipt could reach rollback; rollback receipt checked content/revision without complete identity | Validate snapshot structure before considering rollback; require exact site/type/ID/content for restoration | Malformed revision never triggers rollback; foreign resource receipt cannot be reported as restored |
| Unknown outcomes had only a warning, insufficient actionable observations | Owner-only recovery review reads the authorized current resource, preserves journal and reports comparisons without granting mutation | New login can inspect; other customer cannot read; matching proposed/original bytes never proves success/restoration |
| Every numeric failed-link status could produce a link-replacement proposal | Admit only consistent missing-destination observations (404/410), never assume root cause | Access/server/rate-limit/mixed/unknown results stay visible but offer no content repair |
| Old scan evidence and a replacement that failed after preparation could still reach approval | Check fifteen-minute scan age at proposal and approval; recheck replacement before approval; require full nonempty 200 HTML | Stale scans and failed replacement stop before backup/write; JSON/204/206/empty success rejected |
| HTMLParser could treat anchors in textarea/inert markup as real links | Ignore inert/raw-text anchors; reject base/plaintext contexts | Literal embedded anchors unchanged, real anchors still replaced byte-exactly |
| `mkdir(parents=True, mode=0700)` applied the mode only to final tenant directory | Create/check each intermediate tenant directory; refuse existing exposed/symlinked paths | Full-state recovery now passes; legacy permission/link fixtures fail without chmod or following links |
| A session could be revoked between password-change resolution and transaction | Recheck active account/session/revocation/expiry in the credential transaction | Logout race cannot change credentials; original password retained |
| Safety patterns missed fullwidth/format-obfuscated or widely separated text | Normalize only the safety-comparison copy; retain original evidence; bounded wider hazard window | Dangerous extractive drafts withheld in both languages, historical input unchanged; safe international text retained |

## New test scope

- `test_autofix_failure_boundaries.py`: simultaneous preparation, process death
  during backup, after consumption and after write, expiry during backup,
  malformed write receipt and foreign rollback receipt.
- `test_autofix_recovery_review.py`: no mutation/download or outcome rewrite,
  fresh-session access, independent later edits and tenant denial.
- `test_repair_diagnosis_boundaries.py`: failure classification, stale evidence,
  replacement loss, response-type/body admission and inert/base HTML contexts.
- `test_customer_auth_races.py`: revoked-session password-change race.
- `test_recovery_state_integration.py`: pending encrypted account challenge and
  held repair survive encrypted full-state fixture recovery; resume remains held;
  old exposed/symlinked workspace is rejected.
- `test_advisor_obfuscated_safety.py`: comparison normalization and safe display
  without a model call or rewriting historical results.

Existing integration regression is warranted because the shared repair engine,
authorization transaction, tenant storage and UI changed. The original nine live
AI cases are not repeated. Tests do not send real SMTP/Groq/B2 requests or touch
Oracle/customer installations. Local TLS SMTP/S3/WordPress CI fixtures are disposable.

A final preflight check also rejects previous-session or replayed plans before
any replacement URL probe. Explicit confirmation cannot turn a stale proposal
into authority for network work.

## Important limits preserved

A reservation is not proof of external completion. If backup creation dies before
returning an ID, an archive may exist without a returned reference; inspect existing
private receipts/object history. Never auto-upload again. Ordinary caught backup
failure occurs before WordPress admission and keeps the existing explicit caller
retry contract; the engine contains no automatic retry loop.

A known backup reference does not guarantee future external availability. Recovery
review does not download or claim revalidated backups, clear a hold, infer operation
ownership from matching bytes, or authorize overwrite of a concurrent edit. Actual
recovery requires separate authenticated evidence and appropriate approval.

Observed 404/410 is not a proven root cause, and a reachable replacement is not
proof of relevance. Human exact-change approval, compatibility review, independent
backup readback and atomic server condition remain mandatory. The public page's
resolved-link outcome is established by an explicitly requested later scan, not
merely by matching stored WordPress content.

Unicode safety screening is conservative pattern-based abstention, not a guarantee
against all languages/obfuscations. Evidence remains untrusted data and cannot
turn itself into execution authority. No provider, model, budget or ledger history
was replaced/reset.

## Deferred boundaries requiring later approval/evidence

1. Free SMTP account/sender and consenting owner mailbox for a bounded real
   verification/reset/delivery check; no credentials are requested today.
2. Authorized disposable WordPress environment matching actual version/theme/
   plugins for compatibility, permissions, backup, repair and rollback validation.
   The `.test` and nonproduction companion restrictions are unchanged; a general
   production activation path is still unimplemented/unapproved.
3. Permission to inspect/install current source on the existing Oracle host,
   review private existing state, validate full actual-state encrypted recovery
   and eventually activate only separately approved services.

Commercial/payment work remains deferred. No unknown gate is marked complete to
make the release status green.


Subsequent development: the separately gated production candidate is now
implemented in `wordpress_production.py`; see `PRODUCTION_AUTOFIX.md` for the
current contract and unperformed live-validation/activation gates. The findings
and restrictions above record the earlier audit batch; its statement that no
production path existed is historical, not the current implementation status.
