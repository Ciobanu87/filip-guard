# Administrator alerting review — 28 November 2026

Status: proposal only. No notification service, account, webhook, SMTP message,
provider request or production activation has been introduced.

## Existing coverage

| Failure | Existing evidence | Automatic administrator notification |
| --- | --- | --- |
| AutoFix failure / uncertain write | Engine persisted outcomes, UI and audit history | No global administrator route |
| Unverified rollback / concurrent-edit conflict | Explicit blocked recovery outcomes | No global administrator route |
| AI unavailable | Advisor safe diagnostic, cooldown and persisted usage protection | No global administrator route |
| Encrypted state backup failure | Backup command nonzero result, JSON status, systemd journal | No administrator sender / OnFailure hook |
| Worker stopped | Local heartbeat freshness and operational readiness checks | Local check only |
| Whole Oracle server stopped | No independent observer | Cannot be detected or delivered by that server itself |

Evidence: `wordpress_autofix_engine.py`, `contextual_advisor.py`,
`monitoring_service.py`, `monitoring_email.py`, `monitoring_worker.py`,
`operations_state_backup.py`, `deployment/oracle_operations_readiness.py`.
Customer monitoring emails are scoped to customer/site ownership. They must not
be repurposed as an unscoped customer-data feed to administrators. SMTP delivery
is still separately gated and not proven live by these tests.

## Minimum free solution to approve before implementation

Use an external dead-man monitor plus a small read-only operational relay over
existing failure outcomes. This remains operational monitoring of the approved
system; it adds no Guard product module or automatic remediation authority.

Healthchecks.io currently publishes a $0 Hobbyist plan with 20 checks. At most
five checks would be needed: host/worker heartbeat, AutoFix incident, AI incident,
backup freshness and rollback/recovery incident. Use email only, no paid delivery
channels. An external observer is necessary for loss of the entire VM. No extra
Oracle resource, public inbound port, real AI health probe or customer-site scan
is needed.

The relay must deduplicate incidents, keep unresolved failures latched until a
verified recovery/administrator acknowledgement, and send only incident class,
time and an opaque operation reference. No keys, prompts, customer content,
backup data or raw logs. AI recovery must come from an already-authorized real
successful request, never periodic billable inference. Planned inactive services
are not failures; freshness checks apply only when their approved services are
actually enabled. AutoFix remains disabled and the relay must never start it.

Required personal step **only after approval**: create/control the external free
monitor account and verify the administrator email recipient. Then configure
restricted heartbeat tokens privately and test synthetic failure/recovery plus
absence of heartbeat. No such account/configuration or external test was made
in this stage. Existing SMTP is an alternative delivery channel only after its
separate validation; it still cannot replace the external host observer.

GitHub scheduled Actions are not proposed as the primary watchdog: official
GitHub documentation limits schedules to the default branch and warns of delays;
`main` must remain untouched.

## Official sources checked

- https://healthchecks.io/pricing/ — Hobbyist $0, 20 checks.
- https://healthchecks.io/docs/configuring_notifications/ — email and escalation.
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

The quoted plan is a current published offer, not a guarantee that an account
has already been created or delivery validated. Administrator alerting remains
an explicit operational gap until the proposal is approved and tested.
