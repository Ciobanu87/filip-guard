# Authenticated read-only model analysis in Streamlit Test

The public Scanner intentionally defaults to `rules`. Setting only
`FG_CUSTOMER_AUTH_DB` enables a login form, **not** a model or AutoFix.
The public-scan Advisor bridge now reuses existing customer/site ownership from
read-only monitoring, independently of the isolated WordPress mutation workspace.
It does not need WordPress credentials, S3 credentials or repair authorization.

An operator must supply private existing account/site storage, not enable public
registration as a workaround. Set `FG_CUSTOMER_REGISTRATION=0`. Existing
`FG_CUSTOMER_AUTH_DB`, `FG_CUSTOMER_DATA_ROOT` and `FG_MONITOR_DB` must point to
the shared private persistent state. Existing accounts are provisioned by the
operator; no default account/password, auto-registration or account takeover is
introduced. Sign in, then authorize the domain with the existing monitoring
ownership proof (or use an already authorized WordPress site). A scan of another
origin is not eligible, even when the same person initiated the public scan.

Use the existing operator AI configuration: `FG_AI_AUTHORIZED=1`,
`FG_AI_PROVIDER=groq-free`, `FG_AI_FREE_PLAN_CONFIRMED=1`,
`FG_AI_CLOUD_DATA_CONSENT=1`, `FG_AI_DAILY_CALLS` no more than 20,
`FG_GROQ_API_KEY_FILE` referencing a private mounted key, and
`FG_AI_LEDGER_DB` referencing the **existing shared ledger**. Never put a key
value in GitHub or a public widget. Preserve the Colab ledger/history securely;
do not create a blank allowance on Streamlit to repeat accepted cases or evade
provider cooldowns. The bridge refuses a missing ledger before constructing a
provider. Changing configuration is not proof of accepted live inference.

After scanning the authorized site, the explicit `Analyze context with AI`
button performs bounded, owner/site-scoped analysis. Language changes only
render the stored result. Expired sessions, revoked ownership, foreign contexts
or origins are blocked before inference; ownership is checked again through the
existing inference checkpoints. Stored UI advice uses the existing customer
session namespace and is cleared by existing logout. No repair controls are
introduced; AI cannot approve or apply changes. Anonymous scans keep working.

The application's general public scan must not be confused with the 9 accepted
quality fixtures or with the separate authenticated AppTest live probe. Do not
repeat them. A new live deployment check needs a distinct authorized scan, the
retained ledger, the owner's existing key, and operator configuration access.

Streamlit Community Cloud local SQLite files are not guaranteed persistent.
Do not represent a temporary path as durable storage or as 24/7 monitoring.
If the operator cannot mount the existing state/secret files there, use the
already packaged private persistent test host. The public UI does not expose
server paths, secret editing, account provisioning or a security bypass.

Offline AppTest exercises the actual bridge button, accepted simulated provider
response, Romanian switch and one-call budget reuse. That is **not** live Groq
validation. Live configuration and a real accepted response remain required.
