# Healthchecks external configuration and synthetic validation

28 November 2026. The owner signed into the cloud browser. This report deliberately
contains no account email, project identifier, ingestion UUID/URL or credential.
Those values were not copied to GitHub, source files, workflow inputs or logs.

## Account and configuration observed

The authenticated Billing page showed **Hobbyist**, initially 1 of 20 checks,
zero SMS/call quota and no billing transactions. The existing unused default check
was renamed `FILIP GUARD host`; a copy became `FILIP GUARD incidents`. There are
exactly two checks; no paid plan, extra integration or payment method was selected.

Both use period **120 seconds**, grace **120 seconds**, **POST only**, and the
existing confirmed email integration, named `FILIP GUARD administrator email`.
The integration page showed **2 of 2** checks assigned and **Ready to deliver**.
The email settings had BOTH down and up notifications enabled; they were preserved.
A paused check is configured to ignore pings until explicit resume.

## Actual external test — limited scope

The controls in the authenticated Healthchecks UI sent one synthetic success POST
to each check. The event logs showed `new → up` at about **15:06 Europe/Bucharest**.
No more pings were sent until the period plus grace elapsed. Both checks then
showed `up → down` at about **15:10**, proving external absence detection.
The email integration changed from Never to **Delivered** during the down stage.

A second synthetic UI POST to each check produced `down → up` at about **15:11**.
Reported synthetic downtime: host **62 seconds**, incidents **45 seconds**. The
email integration again showed **Delivered** after recovery. No extra test-email
button or new email channel was needed.

This is **Healthchecks-provider delivery confirmation**, not independent inbox
inspection. Actual inbox receipt remains unconfirmed until the owner confirms it.
The pings originated from the browser, **not Oracle**. These results therefore do
not establish the Oracle-to-Healthchecks connection or test the actual `/fail`
transport from the server, nor do they prove a real VM outage/reboot recovery.
The production VM and application were never stopped/restarted for this test.

After the cycle, BOTH checks were explicitly **paused**, preserving the event
history and configuration. This prevents recurring synthetic false outages before
the real observer is connected. They must be resumed deliberately before the
first live Oracle heartbeat. A successful HTTP response to a paused endpoint does
not prove monitoring is active.

## Direct Oracle evidence

Read-only inspection via pinned SSH:
https://github.com/Ciobanu87/filip-guard/actions/runs/46148139741

Returned `operator-inspected`, `config_present=false`, `operator_timer_active=false`,
`guard_unit_states_unchanged=true`, `production_active=false`, zero Groq/B2.
The observer code remains the separately prepared release. No application source,
AI budget, customer state or key was changed. No secret URL was inferred or inserted
through GitHub. The connection is held for the private owner handoff.

The added operator controller verifies installed observer file hashes, the four
inactive app/backup units, separate URLs and all production expected-state flags
FALSE before any non-inspection action. It can start only the operator unit/timer,
create one explicitly synthetic operator incident, and confirm ONLY that synthetic
incident after an external failure observation. It cannot clear real incidents,
start the app, repeat WordPress writes or invoke AI/B2.

## Checks and commits

Controller: `b0faec9904af19928f51ee69ecd56ce2a55331ed`.
https://github.com/Ciobanu87/filip-guard/actions/runs/46148139705
All five CI jobs passed: **979 + 24 + 8 = 1,011 tests**. Three new controller guards
refuse non-root control, unknown activation actions and active application units.
The existing Oracle WordPress pilot and real AI evaluations were not rerun.

## Indispensable private step

In the existing Oracle SSH terminal, the owner runs:

```
sudo python3 /opt/filip-guard-operations/operations_healthchecks_entry.py
```

At the first hidden prompt, paste the ping URL for `FILIP GUARD host`; at the
second, paste the ping URL for `FILIP GUARD incidents`, copied from Healthchecks.
Input is not echoed and is not a shell-history argument. The helper stores only
a root-owned 0600 server configuration, refuses overwrite and starts nothing.
Only its final redacted status should be shared. No URL/key/password belongs in
chat, screenshots, repository or GitHub inputs.

After this step, the already-approved continuation is: inspect the private file
and permissions without values; resume the two external checks; start and verify
only the operator observer/timer; test a synthetic latched incident, actual `/fail`
delivery and evidence-based synthetic recovery while preserving any real incident;
confirm Oracle-origin pings and real inbox delivery. No new approval is required
for these already-authorized operations. Production remains held throughout.
