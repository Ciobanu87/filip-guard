# filip-guard
FILIP GUARD – Professional website scanner for broken links, SEO issues, and website health monitoring.

## Development status

Current development and launch-gate status is maintained in
[the release readiness matrix](RELEASE_READINESS.md) and
[the controlled Oracle test/install plan](deployment/CONTROLLED_RELEASE_PLAN.md).
The four approved read-only guards, authenticated account/site isolation,
monitoring and optional evidence-constrained AI Advisor are implemented.
Groq is the current provider; its accepted historical live cases are preserved.
WordPress content repair/restore is integrated only for explicitly authorized
isolated `.test` environments. Production customer repairs remain blocked.
New development is not automatically installed on Oracle; services stay held.

The public development Scanner uses verified DNS-pinned HTTPS, bounded reads
and no redirects. Plain HTTP is intentionally rejected. Deterministic rules and
reviewed templates remain available when model access is disabled or invalid.
These statements do not claim complete model reasoning, broad WordPress plugin
compatibility, a whole-site backup or production launch readiness.

Offline approvals require a high-entropy `session_id` supplied by the trusted
server session at issuance and preparation. Never accept that identifier or the
`trusted_authorization` flag as proof of authorization from a client. Existing
approval databases are migrated automatically; unbound old approvals are rejected
and must be reissued. This low-level session binding alone does not implement login or expiry; the
authenticated customer flow uses the separate CustomerAuth integration.

## Independent backup recovery

`BackupManager(database_path).export_verified_copy(new_path)` creates a new
SQLite copy through SQLite's backup API, including committed WAL data. It checks
database integrity and every stored content hash before returning. Existing
files are never overwritten. Connections are closed after each operation.

Store the resulting file securely outside the app's temporary filesystem. This
API does not upload, schedule, or encrypt backups. Content hashes detect accidental
corruption; they do not authenticate records against malicious modification.

To recover locally, open the exported file with `BackupManager(new_path)` and
retrieve the required `backup_id` with `get_backup`. Automated tests recover
content after deleting the original database. This is database recovery only;
remote WordPress rollback is implemented and tested only in isolated fixtures;
production activation remains blocked.

Before commercial launch, the remaining live/operational, WordPress compatibility,
account recovery and commercial gates in RELEASE_READINESS.md must be closed.
No production launch has been performed. The sections below retain the scope
and limitations of individual components; older fixture descriptions are not
a claim that the later provider/custody milestones were undone.

## AutoFix development integration (isolated fixture)

The Streamlit app now includes an opt-in **AutoFix — isolated local test**.
It accepts synthetic content only, displays the exact diff, requires a new
explicit approval for each repair, creates and verifies a content backup, runs
a conditional update, and checks the result. It never accepts real credentials
or connects to a real WordPress installation. Its synthetic test files are
intentionally temporary and are not production storage.

`AutoFixEngine` persists proposals, session binding, approval metadata and
operation outcomes in SQLite. Supported operation: reviewed content replacement
for posts/pages only. The trusted server must supply authenticated user/session
identity; this engine does not implement login. Tokens cannot cross proposal or
resource-type boundaries. Stale content/revisions and consumed approvals fail
closed. A later edit cannot be overwritten by conditional rollback. An uncertain
write result is journaled and cannot be retried blindly; manual reconciliation
is required. A process crash during application remains marked `applying` with
the backup ID and an explicit recovery requirement.

The default gateway always rejects live execution. `LocalWordPressFixture` is
an isolated SQLite model of permission checks, idempotency and atomic
compare-and-swap, not a WordPress implementation. A production gateway still
needs an authenticated, authorized WordPress server endpoint that enforces the
revision condition atomically. Do not substitute REST GET followed by a normal
POST: that permits concurrent changes to be overwritten.

The candidate Application Password identity exchange reuses the DNS-pinned,
verified TLS transport and strict HTTP parser. Tests use only fictitious secrets
and mocked connections; the public authentication entry and live repair UI remain
disabled. A disposable WordPress installation is now exercised by the separate real
integration suite described below; client activation remains disabled. Python cannot guarantee in-memory secret zeroization.

## Encrypted external content-backup adapter

`export_encrypted_copy(manager, store, key, key_id=...)` exports the content
snapshot database, encrypts it with AES-256-GCM using a fresh nonce, uploads only
ciphertext through an injected object store, then downloads, authenticates,
decrypts and verifies an independent recovery copy before reporting success.
`restore_encrypted_copy` can recover without Streamlit or the original database.
It rejects wrong keys, modified data, unexpected object digests and existing
output paths. Recovery files are created with private permissions.

The content-backup tests described here use an in-memory object store and
ephemeral keys. Separately, B2 configuration, owner key custody and a manual
Oracle AI-ledger encrypted recovery have been verified. Scheduled backups and
actual customer WordPress content recovery remain disabled/unvalidated. Deployment needs private durable external storage, an
independently retained encryption key, a saved nonsecret export receipt and an
operator-tested recovery procedure. These archives cover saved resource content,
not themes, plugins, uploads, configuration or the complete WordPress database.

## Candidate real WordPress REST gateway and companion

`WordPressRESTGateway` now connects the existing `AutoFixEngine` contract to the
verified HTTPS transport. It authenticates `/wp-json/wp/v2/users/me`, checks the
expected user and exact resource, and uses only the companion's authorized
snapshot and conditional-update routes. Credentials are obtained transiently
from a trusted server callback and never written to the repair journal. Requests
are bounded; redirects and automatic retries are forbidden. A lost response is
reported as an uncertain result, never as a successful repair or permission to
retry. The legacy adapter, public authentication entry and default engine gateway
remain disabled for customer production sites; the candidate is connected only
to the isolated authenticated test workspace.

`wordpress_companion/filip-guard-companion.php` implements the matching candidate
REST endpoint for posts/pages. It is disabled by default. Its original test
flag refuses production; the separate production candidate requires independent
reviewed app/WordPress policy admission. Nothing in this repository installs or enables it on any site.
It requires HTTPS, Application Password authentication, per-resource edit
permission and an explicit nonproduction test activation constant. It rejects
unsupported payload fields and content that fails WordPress's post HTML filter.
The version covers the complete selected post row; one byte-exact conditional
SQL update checks every original column, so a title/status/author/content change
between read and write also prevents the update. A durable single-use operation
reservation prevents a lost reply or pending operation from causing a repeat
write. Rollback uses the same conditional endpoint with the post-write version.

**Scope limitation:** this test-only endpoint changes `post_content` and modified
timestamps directly. After the atomic update it runs core status/edit/post-updated/save/after-insert
actions and creates native WordPress revisions. It does not emulate all
`wp_update_post` input filters, update builder metadata, or guarantee arbitrary
search/cache/SEO plugin compatibility. A callback that changes the selected post
row invalidates the receipt, preserving an explicit uncertain outcome. It must not be marketed as general WordPress
maintenance or enabled for customers without resolving and validating the required
compatibility behavior. Existing content that fails the HTML filter cannot be
restored through this endpoint; the engine reports restoration failure explicitly.
Saved content backups are not full-site backups.
The conservative `classic-html-link-v1` content restriction is enforced in the
engine, gateway and companion. Blocks, shortcodes and known builder markup are
rejected. [WORDPRESS_COMPATIBILITY_PROFILE.md](WORDPRESS_COMPATIBILITY_PROFILE.md)
defines the isolated environment evidence/review requirements; passing a
diagnostic profile never authorizes production writes.

Tests cover actual Python HTTP serialization/parsing with synthetic sockets and
execute the PHP endpoint against controlled WordPress/wpdb API stubs. A second
integration suite sends the Python engine/gateway requests through the actual PHP
companion handlers over a local subprocess bridge, exercising application,
concurrent title changes, permission revocation, lost replies and conditional
rollback. No socket listener or real WordPress database is used. PHP lint
and these endpoint tests run in GitHub Actions. Those simulated tests are supplemented by the separate disposable real
WordPress/MySQL/MariaDB suite described below. Hosting-specific behavior and
arbitrary third-party plugins still require separate compatibility validation.

Protocol development references:
- https://developer.wordpress.org/reference/hooks/application_password_did_authenticate/
- https://developer.wordpress.org/rest-api/extending-the-rest-api/adding-custom-endpoints/
- https://developer.wordpress.org/reference/functions/wp_update_post/


## Real WordPress integration validation

`tests/real_wordpress/run.py` provisions a clean disposable WordPress 7.1.5
installation with generated users/Application Passwords, the actual companion,
a real SQL database, and verified local TLS. No third-party website is used.
Local runs use PHP 8.4/MariaDB 11.8.9; the separate GitHub Actions job uses
PHP 8.3/MySQL 8.0.36. See `tests/real_wordpress/README.md` for reproduction.

The 17 real integration tests cover identity, resource permissions and revocation,
approved backup/write/verification, conditional restoration/idempotency, concurrent
title changes and an injected edit immediately before the actual SQL CAS,
native revisions and core save hooks, a mutating fixture plugin, draft pages,
disabled/production guards, untrusted TLS, lost/truncated replies, rollback after
verification failure and explicit rollback failure/conflict. Network faults are
injected around actual WordPress requests; they are not claimed as a hosting outage.
Production execution stays disabled by default; the original test flag cannot
enable it. The separately gated candidate requires its own reviewed admission.


## Customer identity, site isolation and required external backup

`CustomerAuth` provides salted scrypt password hashes, opaque server-held sessions
stored as digests, absolute/idle expiry, logout, account login throttling and
password-change revocation. Local usernames are account identifiers, not verified
email addresses. Public signup is off by default. The existing scanner/Advisor
remain accessible without enabling customer repair access.

The account UI is configured only when the operator supplies `FG_CUSTOMER_AUTH_DB`.
`FG_CUSTOMER_REGISTRATION=1` explicitly enables local signup for an authorized
development deployment. No such deployment or personal account was configured in
this work. Login credentials are not placed in URLs, browser local storage, logs
or the repair journal. Logout clears customer UI state. Real deployment still
needs TLS/session operational review, authorized live delivery and signup-abuse controls.
Optional verification/recovery is implemented behind explicit disabled flags; see
[ACCOUNT_RECOVERY.md](ACCOUNT_RECOVERY.md). This does not gate legacy usernames
on email or claim that any deployed customer address has been verified.

`CustomerSites` is the trusted service boundary. It resolves the customer from
the session for every operation; callers never choose a customer ID. A site can
be bound only after the companion verifies Application Password authentication
and `manage_options`. Another customer's site binding cannot be overwritten.
WordPress numeric user/resource IDs are scoped to the verified site; customer IDs
are independent opaque UUIDs. Default site connection/execution remains disabled
unless trusted server code injects the REST gateway. No customer repair UI is enabled.

Credentials use AES-GCM with owner/site/origin/WordPress-user associated data.
Credential and content-backup keys are derived separately for each customer/site
from an externally supplied versioned master key. No master key is generated or
saved for deployment. Keep old key versions independently recoverable. Private
workspaces and database files isolate plans, approvals, snapshots and receipts.
A new login cannot inherit approvals from an earlier session.

`VerifiedExternalBackups` integrates the encrypted archive adapter into the
existing repair engine. It verifies upload readback and re-downloads/decrypts the
exact resource archive before approval consumption or a write. Approval expiry
is checked again after external readback, using the current time. Missing storage,
lost connections, corrupt archives and unavailable keys block execution. Receipts
survive Streamlit sessions; recovery works without the original snapshot database.
Namespaces and keys prevent swapping archives across customers/sites.

`S3ObjectStore` supports operator-configured HTTPS S3-compatible storage with
explicit credentials, bounded streams, one request attempt and sanitized failures.
It does not use ambient AWS credentials. Tests use botocore response stubs and an
in-memory object store. **No real external backup provider, bucket, service
credentials, production key custody, schedule or retention was configured or
validated.** Saved resource content is still not a full WordPress site backup.

Two real isolated WordPress installations with the same numeric administrator ID
are now exercised through customer sessions and ownership verification. The real
suite proves denied cross-customer access and that a corrupt simulated external
archive prevents an actual WordPress write. The external storage in that scenario
is explicitly simulated; WordPress/TLS/SQL are real.

## Periodic monitoring and account notifications

Read-only scheduling, durable leases/recovery, scoped history and grouped in-app
notifications are implemented in `monitoring_service.py`. The existing scanner
is shared through `website_scanner.py`; the monitor uses a separate verified
HTTPS reader and cannot authorize or execute AutoFix. Streamlit exposes per-site
monitoring controls only to the authenticated owner. The separate worker must
be explicitly configured and run; no live customer schedule has been activated.

See [MONITORING.md](MONITORING.md) for frequency/request limits, recovery semantics,
private deployment paths and the prepared opt-in SMTP adapter. Email delivery
remains unconfigured and disabled. Synthetic SMTP tests do not validate a real
mail service. The public app/main branch and client AutoFix activation are unchanged.


## Separately gated production AutoFix candidate

The exact-link production route is now implemented but disabled. It reuses the
existing engine and adds private reviewed admission, WordPress-side matching
policy/profile/resource enforcement, independently rendered public verification
and verified conditional rollback. The original `.test` workspace remains
restricted; its flag cannot authorize production. See
[PRODUCTION_AUTOFIX.md](PRODUCTION_AUTOFIX.md). Actual owner-environment validation
and activation remain unperformed; no production policy/receipt is provisioned.
