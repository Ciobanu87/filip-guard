# filip-guard
FILIP GUARD – Professional website scanner for broken links, SEO issues, and website health monitoring.

## Development status

The scanner and Advisor are beta features. Advisor recommendations are fixed
SEO rules and text templates; no AI model is connected. AutoFix and authenticated
WordPress requests remain disabled. Offline preparation does not authorize a
remote edit or prove that WordPress permissions have been verified.

Offline approvals require a high-entropy `session_id` supplied by the trusted
server session at issuance and preparation. Never accept that identifier or the
`trusted_authorization` flag as proof of authorization from a client. Existing
approval databases are migrated automatically; unbound old approvals are rejected
and must be reissued. Session binding does not implement login or session expiry.

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
remote WordPress rollback is not yet implemented or validated.

Before commercial launch, the project still needs scanner transport hardening,
end-to-end authenticated WordPress integration, resource permissions, trusted user
sessions and per-operation approval UI, atomic server-side conditional edits,
post-edit verification, remote rollback tests on an authorized WordPress fixture,
and durable encrypted external backups. Monitoring follows validation of those
components. No production launch has been performed.

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
disabled. No authorized WordPress installation has been used for integration
validation in this session. Python cannot guarantee in-memory secret zeroization.

## Encrypted external content-backup adapter

`export_encrypted_copy(manager, store, key, key_id=...)` exports the content
snapshot database, encrypts it with AES-256-GCM using a fresh nonce, uploads only
ciphertext through an injected object store, then downloads, authenticates,
decrypts and verifies an independent recovery copy before reporting success.
`restore_encrypted_copy` can recover without Streamlit or the original database.
It rejects wrong keys, modified data, unexpected object digests and existing
output paths. Recovery files are created with private permissions.

No actual external provider, credentials, backup schedule, retention policy or
production key custody has been configured. Tests use an in-memory object store
and ephemeral random keys. Deployment needs private durable external storage, an
independently retained encryption key, a saved nonsecret export receipt and an
operator-tested recovery procedure. These archives cover saved resource content,
not themes, plugins, uploads, configuration or the complete WordPress database.
