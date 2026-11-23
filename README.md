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
