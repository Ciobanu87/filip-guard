# Phone-friendly B2 verification using GitHub Actions Secrets

This is an alternative to editing Streamlit TOML. Existing Streamlit settings stay
untouched. Repository Secrets are available to authorized Actions jobs; they are
not automatically available to the running Streamlit application.

In GitHub repository Settings > Secrets and variables > Actions > Secrets, add
four separate **repository secrets**, each with a single-line value:

| Name | Value |
| --- | --- |
| `FG_B2_KEY_ID` | Existing bucket-scoped B2 `keyID` |
| `FG_B2_APPLICATION_KEY` | Existing B2 `applicationKey` |
| `FG_B2_BUCKET` | Existing private bucket name |
| `FG_B2_ENDPOINT` | Existing HTTPS S3 B2 endpoint, including `https://` |

Do not put values in issues, source files, workflow YAML, screenshots or chat.
Do not replace unrelated secrets. No new production key is generated. Use the
existing bucket-scoped read/write key; this job needs no delete/list privilege.
Do not add a card or activate billing. Confirm remaining free capacity in the B2
account before requesting a real probe; no paid capacity is authorized.

## Explicit development-only request

After secrets are configured, an authorized developer changes the nonsecret
`deployment/b2-validation-request.json` marker **on filip-guard-development**.
That triggers `.github/workflows/b2-recovery.yml` through a push path filter;
there is no cron, pull-request secret exposure or default-branch edit. A
new development-only workflow's manual-dispatch button is not assumed to exist
on the default branch. The marker is intentionally absent until a real test is
requested; creating the workflow does not itself access B2.

The workflow uses a read-only GitHub token, disables persisted checkout
credentials, limits runtime to five minutes and serializes probe jobs. Provider
credentials are only supplied to the final test step. No artifacts contain keys,
receipts, private bucket identifiers or source SQLite files. Failure output is
sanitized. No actual secret values are interpolated into shell commands.

## What the probe validates

`operations_b2_probe.py` uses the existing HTTPS S3 adapter and AES-GCM application
state backup/recovery functions. It creates one tiny synthetic SQLite database,
closes its writer, uploads at most one encrypted object (maximum 64 KiB) and
verifies read-back. A fresh Python process receives only the recovery receipt,
test-only key and expected digest through a private pipe, creates its own SDK
client, downloads and recovers into a new destination, and verifies both the
restored bytes and the mandatory recovery hold. The original source path is
not passed to that process. No application or WordPress state is read.

One encrypted synthetic test object remains in the bucket. It is never deleted
or overwritten by this job. Its disposable test-only encryption key is not
retained; it is not an operator production recovery key. No key is logged or
published as an artifact. This tests a fresh recovery process, not independent
long-term production key custody or disaster recovery after loss of the host.

A verified result establishes connectivity and encrypted synthetic recovery on
the selected provider. It does not establish automatic production backup,
Streamlit persistence, scheduling, 24/7 hosting, actual-account recovery, mail
sending or Groq inference. Those existing launch gates remain blocked.
