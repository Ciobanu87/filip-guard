# Integrated customer test workspace

`app.py` now selects one authenticated workspace when the isolated-test configuration is complete. The existing public Scanner/Advisor and synthetic sandbox remain available with the default configuration. Nothing deploys or enables customer production repairs.

The workspace connects an account to a WordPress site using Application Password ownership proof, lists a bounded sample of published posts/pages, scans the selected permalink with the shared Scanner and rule-based Advisor, and maps a broken internal link back to its editable WordPress resource. Only exact anchor destination replacements are supported. SEO recommendations remain read-only. The Advisor and monitoring cannot approve changes.

Every repair shows the exact diff and requires a checked approval. Existing session, expiry, persistent encrypted backup, external readback, atomic companion CAS, verification and conditional rollback protections run before success is shown. A user-requested rollback is another diff with a fresh explicit approval. Its expected version is the actual verified post-repair snapshot: later edits, even identical-content revisions, cannot be overwritten. This is content recovery, **not a full-site backup**.

Scans, site ownership, encrypted credentials, repair journals, history and monitoring are durable and scoped to customer/site. Logging in again restores history, never old approvals. Unknown write outcomes require reconciliation and cannot be blindly replayed. Provider exceptions are sanitized in the UI.

## Reproduce the verified journey

Run ordinary tests with `python -m unittest discover -v` (PHP is required for the companion contract tests). The separate GitHub Actions `real-wordpress` job provisions disposable WordPress, TLS and MySQL, then drives **app.py through Streamlit AppTest**: account creation, site authorization, source scan, rule recommendations, diff, explicit approval, encrypted verified backup, real REST mutation, public recheck, explicitly approved restoration, monitoring settings, background worker tick, notification inbox and a new login. Test-environment seed posts and credentials are created before the customer journey; no manual application database changes are used to complete it.

A successful job uploads `filip-guard-integrated-ui-proof`, a sanitized JSON record of the completed stages. A failed journey does not produce a success record. The external object store in this demonstration is **simulated**; the encrypted archives, integrity checks and WordPress/MySQL operations are real. Email is not sent. Existing real tests separately cover two customer/site installations, native revisions/save hooks, write races, lost/truncated responses and rollback failures. This does not prove compatibility with arbitrary marketplace plugins or hosting.

## Operator configuration (disabled by default)

All of these must be configured on an authorized test host, without committing secrets:

- `FG_GUARD_TEST_UI=1`, `FG_GUARD_TEST_ORIGINS` as a JSON list of explicit HTTPS `.test` origins; public customer origins are rejected.
- `FG_CUSTOMER_AUTH_DB`, `FG_CUSTOMER_DATA_ROOT`, `FG_MONITOR_DB` on persistent private storage.
- `FG_GUARD_MASTER_KEY_FILE`: private regular file, mode 0600, exactly 32 binary bytes; retain its version outside this app for independent recovery. `FG_GUARD_KEY_ID` defaults to `test-v1`.
- `FG_GUARD_S3_ENDPOINT`, `FG_GUARD_S3_BUCKET`, `FG_GUARD_S3_CREDENTIALS_FILE`: explicitly authorized S3-compatible provider and private JSON credentials file containing `access_key_id`, `secret_access_key`, optional `session_token`. No ambient credential chain is used.
- Optional `FG_CUSTOMER_REGISTRATION=1` for test-account creation.

Install the existing companion only on the isolated WordPress installation, with its test repair flag and nonproduction environment gates. Verified HTTPS and production SSRF checks remain mandatory. The disposable CI runner supplies only its own hostname-bound TLS connector for loopback fixtures; this exception is never enabled by deployment configuration.

Run `streamlit run app.py` for the UI. Run `python monitoring_worker.py` separately, with the same account/site/monitor paths, under an operator-configured process supervisor for periodic execution. The UI warns when no recent worker has run; enabling a schedule alone does not start infrastructure. `python monitoring_worker.py --once` is a bounded operator test. Monitoring uses ownership metadata without credential decryption and cannot invoke AutoFix. Email remains off until separately authorized/configured.

No external storage service, SMTP service, persistent hosting, key custody or process supervisor has been provisioned by this change. Production remains blocked pending real provider recovery, operational configuration and separate authorization/validation.
