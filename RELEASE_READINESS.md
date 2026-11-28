# FILIP GUARD development and release readiness — 2026-11-28

This is an evidence/scope matrix, not a declaration that the product is finished.
Development is confined to `filip-guard-development`; `main` is unchanged. No new
host/provider call, service activation or paid resource is authorized by this file.
The companion, repair origin restrictions and production guards remain intact.

| Component | Implemented and exercised offline/isolated | Mandatory remaining boundary |
| --- | --- | --- |
| Website Guard / public Scanner | Bounded verified HTTPS, SEO/link observations, sanitized evidence, public read-only WordPress suggestions; incomplete results visible | Authorized real-site validation of current source; HTTP without TLS is intentionally unsupported |
| Commerce Guard | Public catalog/Product/Offer checks; shared budgets, scopes/history and alerts | Real authorized shop/schema coverage; no checkout/order/payment tests or automated commerce repairs |
| API & App Guard | Public GET/status/JSON contracts, no secrets/raw responses retained; tenant-owned resources | Real authorized endpoint contracts; authenticated APIs/browser journeys are outside current implemented scope |
| Infrastructure Guard | Public DNS, verified TLS expiration, optional authoritative RDAP with unknowns preserved | Real authorized DNS/TLS/registrar coverage; no DNS/certificate/domain mutations |
| AI Advisor | Provider interface, Groq adapter, evidence guard, scoped cache, global retained budget, per-provider backoff; historical nine live cases accepted | New complex semantic holdouts are simulated so far; prepared live runner defaults to approval-required; model quality/general safety are not established by contract tests |
| Customer identity/isolation | Local accounts, salted password hashing, private durable sessions/site ownership and domain-control proofs | Opt-in verified-contact/password recovery implemented offline: expiring single-use codes, encrypted delivery queue, shared SMTP attempt cap and session revocation. Real TLS/mail delivery, signup/recipient policies and deletion/privacy workflow remain unvalidated/incomplete; no customer address was verified by this batch |
| WordPress AutoFix | Exact broken-anchor replacement in post/page content: explicit session-bound approval, verified encrypted backup, conditional apply/verify/rollback and separate reviewed restore | Companion is nonproduction/test-only. Conservative classic-HTML profile now enforced before proposal and conditional writes; owner-only read-only environment inventory and evidence criteria are implemented. The separately gated production path now integrates operator admission, exact diagnosis, backup/CAS and independent rendered verification/rollback. It is disabled; actual live compatibility, validation artifacts and activation remain unperformed. General metadata/plugin/builder repair and full-site restore are not implemented |
| Monitoring | Four-module scheduling, durable reservations/leases, verified resolution scopes, failure isolation, history/inbox and email outbox; no automatic model/repair execution | Oracle worker activation and sustained real operation require approval; live email delivery remains unvalidated |
| External recovery | B2 mounted; owner-confirmed zero-dollar caps; notification API reported not enabled; owner independently recovered master fixture; real Oracle AI-ledger encrypted backup/fresh restore verified | This was one SQLite database, not full future customer state or WordPress/VM recovery. Keep private manifest/key custody, review current headroom before future writes, then validate newly provisioned full state |
| Oracle runtime | Existing Always Free host installed/hardened/reboot-tested previously; private storage and inactive units | Installed application snapshot predates recent development. Current source install, explicit fresh account/site/monitor bootstrap, current root activation approval and controlled startup remain unperformed |
| Billing/commercial launch | Deferred by the owner's instruction until technical validation | Payment/Merchant-of-Record integration, customer terms/privacy/retention and launch review are not implemented/approved by this technical batch |

## New development closing identifiable pre-live gaps

The old public UI/Scanner `requests` path is replaced by the existing verified
HTTPS transport/Scanner. No DNS precheck followed by an ambient reconnect remains
in that default public workflow. Redirects/partial framing, oversized bodies,
private targets and write methods fail closed. WordPress candidates use existing
published-resource validators and a single bounded suggestion-stage budget;
reachability never grants repair permission. Explicit injected fixture readers
remain available for tests; they are not deployment bypasses.

`test_prelaunch_system_flow.py` combines identification, simulated evidence advice,
owner-only review/approval, verified encrypted fixture backup, conditional repair,
four-module monitoring with a temporary API fault, later resolution, fresh-login
manual restore and rediscovery. Another customer stays isolated. It is a new
cross-component scenario, not another external Groq/B2 or customer-site test.

`validate_complex_advisor.py` prepares at most five new synthetic admissions using
the existing configured advisor/ledger only after explicit opt-in. Private durable
attempt/result receipts prevent blind repeat of a lost result. Contract/relevance,
coverage or safety failure stops the run. Completed original fixtures are not in
this suite. Human semantic validation stays false even when observable gates pass.

## Account recovery and WordPress profile development

`ACCOUNT_RECOVERY.md` describes optional account verification/recovery, disabled
by default, with the retained master only. Recovery does not create a session,
change the customer ID, grant repairs, recover an unverified mailbox, replace a
verified address or reset any budget. Tests exercise simultaneous consumption,
uncertain delivery, tampered encrypted payloads, UI confirmation and a reset
invalidating the previous repair session. Account and monitoring mail share the
same durable SMTP cap; a failed account dispatcher does not skip monitoring mail.

`WORDPRESS_COMPATIBILITY_PROFILE.md` defines the conservative classic content
profile and bound, short-lived environment evidence. The Python engine/gateway
and PHP companion reject unsupported editors/builders before mutation. This is
a restriction, not a plugin-compatibility guarantee. The readiness report now
explicitly requires compatibility evidence and still cannot authorize writes.

## Internal hardening audit — 2026-11-28

See `AUTOFIX_INTERNAL_AUDIT_2026_11_28.md` for the concrete findings, fixes and
new regression scenarios. Backup admission is now claimed before external I/O;
crashes during preparation/consumption stay held. Write and rollback receipts
require validated resource identities. The recovery review observes current
content without rewriting an outcome or granting retries. AutoFix suggestions
require unambiguous 404/410 observations and bounded evidence age; temporary or
authorization errors remain read-only findings.

The new full-state fixture recovery includes pending encrypted account delivery
and a held repair journal, with automatic resume still blocked. This also exposed
and corrected intermediate tenant-directory permissions; existing nonprivate or
symlinked directories require operator review, never silent chmod/following.
Password-change transactions recheck session revocation. Safety screening now
checks Unicode-normalized draft text without changing retained source evidence.
None of these tests validates actual Oracle state, real SMTP delivery, a customer
WordPress environment or new provider semantics.

## Disabled production route

`PRODUCTION_AUTOFIX.md` specifies the implemented separate production admission
and complete execution/recovery integration. The `.test` path remains unchanged.
Private reviewed policy/receipt, matching WordPress-side policy and explicit
independent flags are mandatory. No active policy or validation evidence for the
actual customer environment is provisioned by this development.

## Readiness conclusion

Offline implementation/test evidence supports the explicitly bounded capabilities
above. It does not remove any production gate. The product cannot be declared
finished or commercially ready while account/commercial workflows, production
WordPress compatibility, mandatory live validations and controlled deployment
remain incomplete. The controlled plan lists those decisions without silently
adding capabilities or weakening security to turn them green.
