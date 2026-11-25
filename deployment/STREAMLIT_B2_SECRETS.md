# Private B2 credentials on Streamlit Test

Use Streamlit Community Cloud workspace > the **development test app** menu >
Settings > Secrets. Confirm its branch is `filip-guard-development`. Do not edit
the main/public app. Merge this TOML into existing secrets, never replace unrelated
settings. Place root entries above all `[sections]`.

```toml
FG_GUARD_S3_SECRET_SOURCE = "streamlit"

[filip_guard_backup]
endpoint_url = "https://s3.REGION.backblazeb2.com"
region = "REGION"
bucket = "YOUR_PRIVATE_BUCKET"
access_key_id = "YOUR_BUCKET_SCOPED_KEY_ID"
secret_access_key = "YOUR_APPLICATION_KEY"
```

In B2, `keyID` maps to `access_key_id`; `applicationKey` maps to
`secret_access_key`. Use the S3 endpoint's region string (e.g. `eu-central-003`),
not the display name "EU Central". Keep the bucket private. Do not add a card or
upgrade a plan. Do not commit actual secrets, screenshots of them or private
bucket identifiers. Credentials are read directly from managed secrets in memory;
no local credentials JSON file or SDK ambient credential chain is used.

Mounted private JSON configuration remains the default for a persistent host and
independent offline recovery. `operations_state_backup.py` can continue using
that route. The same S3 transport/timeout/bounded read-back adapter is reused.
Saving credentials does not upload anything, enable signup, grant repair approval
or start a scheduler. No public credential-entry widget is added.

SSE-B2 protects the stored objects with provider-managed keys. Existing FILIP GUARD
AES-GCM client encryption additionally requires the externally retained application
encryption key and trusted recovery manifest. The B2 application key is not that
encryption key. Do not fabricate or rotate a production key to make configuration
pass. Keep independent custody of the encryption key before any real backup.

A real recovery drill must upload an AES-GCM archive, download and verify it,
then recover into a separate empty destination with the externally retained key.
Application-state export requires all writers stopped; do not run it automatically
inside a Streamlit rerun. Persistent host scheduling, private state, key custody
and a real B2 drill remain separate gates. A named bucket or successful SDK
construction alone does not validate those gates or establish 24/7 backup.
