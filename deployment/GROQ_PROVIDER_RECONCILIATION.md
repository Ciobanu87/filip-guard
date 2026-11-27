# Owner-authorized provider-history reconciliation and single synthetic key check

Owner supplied `groq-logs-Default_Project-7d-2026-11-27-08-19-03.csv` on
2026-11-27 and authorized one synthetic call only after verified reconciliation.
The exact original CSV SHA-256 is pinned in `groq_usage_reconciliation.py`.
The reviewed scope is this project/key and the seven-day export window ending
08:19:03 UTC. It is not an assertion about other organizations/projects or
unexported dates. The 15 rows are 14 HTTP 200 and one HTTP 429, all 2026-11-24;
reported tokens are 3,062 input + 836 output = 3,898. The 429 row reports zero
tokens; that is retained as provider reporting, not invented request success.

The lost Colab SQLite cache, request hashes, pre-network failed reservations and
local timestamps cannot be recovered from this CSV. The nine prior accepted
results are separately retained as historical evidence, not rerun or fabricated
into cache rows. No claim of original-SQLite reconstruction is made.

Reconciliation preserves any existing ledger (with a prior snapshot), its
request rows and any higher existing budgets. The selected minimized route
imports a daily observation, with original request rows retained independently.
An empty/new ledger is published atomically only after a verified import.
Every elapsed UTC day touched by this export is held at the existing local cap
of 20 calls, or a higher existing count. These labeled conservative **holds are
not claims of actual calls**; they prevent refunding unknown historical local
reservations. The current day imports the exported request count, retaining any
higher current local counter. Counters never decrease. The complete original CSV and nine-case evidence remain in the independently
retained owner uploads; only the verified daily observation and hash references
are retained on Oracle. Prior cooldowns are retained; the historical 429 receives the
existing conservative unknown-expiry policy anchored to its actual timestamp.
No fresh reset time or organization-wide remaining-token number is inferred.

The owner-history ciphertext was NOT published. Automatic approval rejected a
durable repository artifact instead of the previously authorized one-day
artifact. No workaround publishes that history or its encrypted form.

A data-minimized alternative needs no history transfer: the operator verifies
the owner's original CSV locally against the pinned SHA-256 and derives only
the aggregate counts already documented above, its UTC day, scope/window and
source hash. The original per-request CSV remains independently retained in the
owner's original uploaded file. No actual request IDs, API-key identifiers,
project identifiers, individual request timestamps or encrypted dataset enter
GitHub. The server imports a clearly labeled operator-verified daily observation,
not original request rows. Original full historical evidence remains with the
owner; only its hash reference and preservation status are retained on Oracle.

`import_verified_observation` validates the exact reviewed observation, prevents
counter decreases and enforces the same conservative closed-day holds. A
historical unknown cooldown is anchored conservatively at the END of its observed
UTC day before applying the existing 24-hour policy. Longer retained cooldowns
are never shortened. The complete source can be rechecked against its SHA-256;
no claim of a complete original SQLite/cache, pre-network reservations, other
projects or organization-wide usage is introduced by this minimized baseline.

The direct owner-SSH upload route remains a fallback prepared in the previous
commit, not a prerequisite for the data-minimized observation. A temporary RSA
transfer key created in preparation remains root-only and unused by this route;
it is not an application master key, API key or SSH identity. Neither the Groq
credential nor original provider history is supplied to GitHub. No public
endpoint, paid service, resource or credential access is created.

After import integrity and totals pass, the one-shot probe:

- requires the export to cover the current UTC day and be at most six hours old;
- honors the existing 20-call ceiling, minute admission, pending requests and
  cooldowns, reserving one call durably before network I/O;
- creates an exclusive persistent attempt marker before the call; a rerun reuses
  its receipt or holds an uncertain attempt, and never issues another call;
- uses only synthetic `{"status":"ok"}` content, reviewed fixed model/verified
  HTTPS transport, timeout 15 seconds, output ceiling 64 tokens, and no retries;
- retains actual usage and sanitized diagnostics. 401/429/timeouts/invalid
  responses stop with the reservation spent; they do not trigger another model,
  key, account, request or automatic refund.

AI/UI/worker/backup flags and systemd units remain held throughout. Success
validates the installed candidate for this bounded synthetic request, not full
live UI operation, email, repairs, independent key custody or automatic backups.
Provider observations are exact within their export scope; they do not recreate
unknown original local history. No new features or main-branch changes occur.

After an accepted synthetic receipt, root adds only the reviewed nonsecret
provider/model/free-plan settings, retaining `FG_AI_AUTHORIZED=0` and explicitly
leaving customer cloud-data consent at zero. An isolated unprivileged process
then constructs the actual installed advisor against the reconciled persistent
ledger. Networking is audit-blocked; private key readiness is checked only in
memory; missing customer cloud consent must block construction; budget/request
counters must be byte-for-value unchanged. This is offline integration, not a
second provider call or application-service activation.

On 2026-11-27 the owner explicitly authorized publication of totals, dates and
the CSV SHA-256 on filip-guard-development. This approval excludes the original
CSV, request/key/project identifiers and API-key material. The operator manifest
records this specific publication scope separately from the one-call permission.
