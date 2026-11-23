# Authorized read-only monitoring

The worker scans only sites already bound to a customer by the verified WordPress
ownership flow. Enabling/disabling and frequency changes require a valid customer
session. Background checks use durable consent, not a stored browser token or a
WordPress password. Account/site authorization is checked before requests and
before committing results. No AutoFix authorization, content edit or email send
is possible through the monitoring scanner/worker.

## Running the worker

On an authorized development host with existing customer/site data, configure:

```sh
export FG_CUSTOMER_AUTH_DB=/srv/filip-guard/accounts.sqlite
export FG_CUSTOMER_DATA_ROOT=/srv/filip-guard/sites
export FG_MONITOR_DB=/srv/filip-guard/monitoring.sqlite
python monitoring_worker.py --once --max-jobs 1
python monitoring_worker.py --poll-seconds 30 --max-jobs 5
```

These are path examples, not a deployment performed by this change. Existing
private data files must be accessible to the service user. The worker needs no
master encryption key, WordPress credential, S3 credential or email credential.
The Streamlit monitoring section uses the same trusted path configuration and
shows only the signed-in customer's authorized sites, history and inbox.
`monitoring-worker.service.example` is an optional reviewed-host template; it is
not installed or enabled automatically. Do not run against unapproved sites.

## Execution and request limits

- Frequency: 15 minutes to seven days; 1–30 pages; at most 60 requests per logical
  run, with lower defaults (five pages/20 requests), ten link checks and 200
  discovered destinations. Duplicate URLs are cached within a run.
- The existing Scanner/Advisor parsing is shared. Monitoring injects only verified,
  DNS-pinned HTTPS GET. All DNS answers must be public. Credentials, external
  origins, unsafe ports, redirects and incomplete responses are rejected.
- Each run has a 60-second reader budget and each request a maximum eight-second
  deadline. Requests are spaced at least one second apart by default and durably
  counted across recovery attempts. HTML and saved result sizes are bounded.
- Atomic claims and opaque lease tokens fence stale workers. A logical due slot
  has one history record and one committed result. Crashed workers can be
  reclaimed after lease expiry, at most three attempts. GET requests may repeat
  after a crash; remote exactly-once reads are not claimed. Request budgets do
  not reset across retries. Late workers cannot overwrite history or alerts.
- Disable/reconfigure cancels the current lease. Re-enabling cannot force an
  immediate repeat of a recent run. Missed intervals are skipped rather than
  replayed as a catch-up burst. The UI reports a stale/missing worker heartbeat.

## History and notifications

History, findings, schedules and notifications are scoped by both customer and
site, with authenticated checks on every customer-facing query. Storage is a
private SQLite database; histories retain the latest 1,000 runs per site. No
WordPress credentials, session tokens or master keys are stored in this database.

Issue keys remain stable across scans. New/resolved findings and material HTTP,
title, description, heading or ALT-count changes are recorded. A failed scan or
an unvisited page is not proof that an old issue is resolved. Removed broken
links resolve only after their known source pages have been checked and the
link is no longer present. Network errors raise a monitoring-error episode;
repeated failures do not spam, and recovery is recorded separately.

In-app updates are grouped by site/category/hour, with bounded detail lists.
Unchanged scans do not create alerts. Customers can mark their own alerts read.
Pending email digests wait for the grouping window to close.

## Email adapter status

`MonitoringEmailDispatcher` defaults to disabled. A trusted operator must provide
an authorized sender and a resolver of verified customer email bindings. No email
verification service, SMTP account, personal credential or real delivery has
been configured in this work. The account UI has no recipient override or SMTP
configuration controls. The monitoring CLI does not send email.

The prepared SMTP adapter requires verified TLS (SSL/465 or STARTTLS/587) and
explicit service credentials. It never reads ambient credentials. Addresses and
account bindings are checked and bodies are plaintext. Delivery attempts are
persisted before sending, throttled per account and bounded. A lost SMTP
acknowledgment or crashed send is quarantined as unknown, without automatic
resend. Known pre-send failures can retry at most three times. Old queued alerts
expire instead of causing a startup email burst. SMTP acceptance is not proof
of mailbox delivery. Blocked/unknown items require operator reconciliation before
any authorized requeue; never retry them blindly.

## Validation scope

Unit tests use controlled clocks, synthetic HTTP/SMTP and two customer/site
fixtures for scheduling, isolation, leases, request limits, failures, recovery
and notification deduplication. Streamlit AppTest covers enable/disable, history
and acknowledgments. GitHub Actions also runs the worker core against a real,
isolated WordPress/MySQL installation with verified fixture TLS and no WordPress
credential access during scans. No customer host scheduler, production hosting,
external mail provider or real mailbox delivery is validated by those tests.
