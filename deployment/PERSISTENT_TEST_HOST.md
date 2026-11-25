# Reproducible persistent isolated-test runtime

This configuration packages the existing application; it provisions no cloud
host, subscription, secret, public deployment or customer repair permission.
CI runs the container proof automatically, so the owner needs no local computer.
The production/main app is untouched. A permanent authorized host still requires
separate access and validation; ephemeral Colab/Work/Actions machines are not
presented as permanent infrastructure.

`Dockerfile` runs as UID/GID 10001, with private state under
`/var/lib/filip-guard`. The same named volume holds account/site databases,
monitoring history/outbox, repair journals/receipts and the AI usage ledger.
`compose.yml` shares that volume between UI and the separate optional worker.
No key is generated on startup and no network service is enabled by a commit.
The worker profile is opt-in; a schedule alone is not a running worker.

On an existing authorized host, the operator supplies:

- `FG_OPERATOR_ENV_FILE`: a private file containing existing nonsecret configuration
  names/paths. Keep the test/UI/AI/email authorization flags disabled until each
  corresponding test is authorized. Use the existing `.env.example` configuration
  templates; never put passwords or API keys in environment templates.
- `FG_OPERATOR_SECRETS_DIRECTORY`: an existing private directory mounted read-only
  at `/run/filip-guard-secrets`. Mount only necessary files, mode 0600 and readable
  by UID 10001. Existing operator keyring, S3/SMTP credentials and Groq key-file
  adapters remain unchanged. No personal/ambient credentials are discovered.

`docker compose -f deployment/compose.yml up --build -d ui` starts only the UI,
bound to host loopback port 8501. Operator-managed verified HTTPS ingress is
required before remote account use. After complete authorized configuration,
`docker compose -f deployment/compose.yml --profile monitoring up -d worker`
starts the separate read-only worker. The default email flag stays off. Restart
policies are bounded to avoid an unconfigured crash loop. Do not expose the app
port publicly or enable production repair flags to make configuration pass.

The CI proof builds the actual image, checks Streamlit health, creates a synthetic
account and a simulated cached AI selection, stops/starts the UI container, then
logs in again and verifies the same cache, call budget, monitoring history and
notification records. The schedule uses synthetic ownership metadata and a local
fixture scanner; it is not proof of a real WordPress authorization. It launches the actual
worker entry point in a fresh container against the same volume, without secrets
or due public scans. This tests container/process restart, not provider uptime,
physical-host reboot, power failure or the real Groq model. Existing account and
monitoring tests cover scoped history, lease recovery and concurrency. No accepted
owner Groq fixture or owner usage ledger is read/reset by the disposable proof.

Normal `stop`, `start` and `down` preserve the named volume. Do not use `down -v`
or remove an operator volume. CI removes only its own randomly named disposable
proof volume. Persist the host volume itself and separately retain encryption keys
and trusted recovery receipts. Verified encrypted WordPress **content** recovery
is not a full WordPress/site or application-state backup. An authorized host-level
quiesced encrypted application-volume recovery drill remains a launch gate.

## Missing state at runtime

The account UI, monitoring configuration and integrated test workspace now require
existing private SQLite state before opening service constructors. A missing
monitor database is a recovery incident, not permission to create an empty history
or outbox. Missing/corrupt account storage disables sign-in and clears customer UI
state while the public Scanner stays available. No registration flag is enabled.

`operations_guard_setup.py --initialize-read-only` is for first provisioning of all
three stores together. A repeat invocation accepts complete valid existing state;
a partial set is rejected before recreating any missing database. Restore that set
using the existing encrypted recovery procedure. The restore-review hold remains
mandatory. These runtime checks do not prove a host volume is durable or provision
a cloud host. The Groq usage ledger is separate and is never changed by this check.
