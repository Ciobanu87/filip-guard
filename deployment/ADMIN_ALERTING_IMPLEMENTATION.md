# Operator monitoring — implementation and activation boundaries

Owner approved 28 November 2026. Healthchecks Hobbyist official pricing verified:
$0/month, 20 checks, 100 retained log entries/check. This implementation needs
only two checks, email delivery only. No card, upgrade, SMS, paid channel or paid
Oracle resource is required. https://healthchecks.io/pricing/

## Implemented

- Durable private incident latch outside customer state; category/digests only.
- Read-only evidence from existing repair plans, AI ledger, worker heartbeat,
  backup receipts, systemd service outcomes and allowlisted private journal events.
- Detection of uncertain writes, unverified/conflicting rollback, stalled repair
  reservations, AI failures/stalls, stale worker, stale backup, missing/failed
  expected services and private UI health failures.
- Structured fail/success events cover AI readiness failures which occur before a
  provider reservation and backup failures which occur before a WordPress write.
  New hooks are prepared in the development release; the currently installed
  application is not updated or started by the independent observer installer.
- Planned inactive components are excluded with explicit expected-state flags.
  UI/worker pause during an active quiesced backup is not treated as a hang.
- Only the exact official hc-ping.com ingestion host is accepted; no redirects,
  proxy inheritance, query strings, payload, traces or customer identifiers.
- At most two tries per safe ingestion ping. No retries of inference, B2 uploads,
  account email, WordPress writes or uncertain mutations.
- Existing UI/worker crash recovery remains bounded by systemd: Restart=on-failure,
  RestartSec=30, StartLimitBurst=3 per 300 seconds, with activation gates intact.
- Extra hang recovery is restricted to an already ACTIVE read-only worker, with
  a valid existing host gate, at most two reserved attempts/hour, and a shared
  backup interlock. `try-restart` never starts an inactive service. No UI hang
  kill, automatic code repair, application activation or WordPress replay.
- Restart command success does not clear incidents. Worker recovery needs a newer
  heartbeat. AI recovery needs a later actual already-authorized successful
  request, not cooldown expiry. Uncertain AutoFix, rollback and backup incidents
  require explicit independently verified operator recovery evidence. They never
  disappear because another repair succeeds or a timer fires.
- The existing approved AutoFix transaction retains its single conditional,
  verified rollback and concurrent edit protection. No new automatic restore or
  recovery authorization is introduced.

The independent unit runs a bounded tick once per minute (45-second limit).
No completed tick/delivery means no host heartbeat; the external observer can
therefore detect server loss, observer failure, lost journal access or a hung tick.
Recommended external period 120 seconds / grace 120 seconds: roughly four-minute
absence detection plus delivery latency, not a promise to beat every client report.
Operational incident `/fail` is sent at the next tick and remains failed while any
incident is unresolved. Ordinary host pings cannot clear the incident check.

## Private preparation and owner handoff

The separate installer only writes `/opt/filip-guard-operations`, its private
operator journal directory, and its two new INACTIVE units. It does not overwrite
existing files, change the installed application/runtime.env or start production.
There are no credentials in the repository or payload. No external check is pinged
until the owner-controlled account and delivery integration are ready.

Indispensable account step: sign into/create the Healthchecks free Hobbyist
account and verify the desired administrator email. Confirm the account remains
$0; use only email integrations. Create exactly two checks named FILIP GUARD host
and FILIP GUARD incidents, each period 120 / grace 120, POST only, same verified
email integration, down AND recovery notifications enabled. Do not assign `*`
(all integrations), SMS, phone, WhatsApp or paid channels.

Two secret ingestion URLs must be introduced directly on Oracle with the hidden
interactive helper, never in chat, screenshots, repository or GitHub inputs:

`sudo python3 /opt/filip-guard-operations/operations_healthchecks_entry.py`

All expected application flags default FALSE because production stays inactive.
This helper only stores root-owned 0600 config, never pings or activates anything.
The account and final transfer are not silently assumed to exist.

After private handoff, the authorized remaining operations are: inspect redacted
configuration/permissions and current account settings; run a bounded real tick;
enable only the OPERATOR timer; inject an explicitly synthetic incident; verify
external down status and actual down email; confirm synthetic recovery using a
root-controlled reviewed receipt; verify external up status and actual recovery
email; suspend only the operator heartbeat for its grace window to verify dead-man
notification, then restore the operator timer. Never power down Oracle or activate
the application to simulate this. Never send success for the aggregate incident
check while any real incident is unresolved.

HTTP 200/OK ingestion, dashboard flips and email queued are not proof of inbox
receipt. Actual email arrival must be verified in the administrator inbox (or
confirmed by the owner). Until then `live_email_verified=false`.

A reviewed recovery receipt is a private root-owned 0600 JSON file under
`/srv/filip-guard/operations/reviewed-recovery`, with fields `incident` (local
incident digest), `recovery_verified:true`, `verified_at` (recent UTC epoch), and
`evidence_sha256` (independent evidence digest). Root-only confirmation command:
`python3 /opt/filip-guard-operations/operations_confirm_recovery.py --receipt PATH`.
It records the confirmation only, never restarts/restores/replays a repair.

## Tests

New offline tests use synthetic state and transport stubs. They verify durable
latching, delivery failure, safe retry limits, URL/redirect protections, readonly
repair inspection, AI/worker recovery evidence, restart limits, backup interlock,
private health endpoint, event redaction and fail-closed installer behavior.
They are not claimed as real Healthchecks or real email delivery tests. Existing
WordPress and AI real validations are preserved; no new Groq/SMTP/B2 calls.
