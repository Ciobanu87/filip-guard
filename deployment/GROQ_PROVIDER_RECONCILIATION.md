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

Reconciliation preserves any existing ledger (with a prior snapshot), exact
request rows in a separate recovery table and any higher existing budgets.
An empty/new ledger is published atomically only after a verified import.
Every elapsed UTC day touched by this export is held at the existing local cap
of 20 calls, or a higher existing count. These labeled conservative **holds are
not claims of actual calls**; they prevent refunding unknown historical local
reservations. The current day imports the exported request count, retaining any
higher current local counter. Counters never decrease. The original CSV remains private on the host and in the owner upload;
the complete nine-case evidence remains in the independently retained owner
summary, with only a hash reference retained on Oracle. Prior cooldowns are retained; the historical 429 receives the
existing conservative unknown-expiry policy anchored to its actual timestamp.
No fresh reset time or organization-wide remaining-token number is inferred.

The owner-history ciphertext was NOT published. Automatic approval rejected a
durable repository destination in place of the previously authorized one-day
artifact. The selected safer route contains no provider-history data in GitHub:
the owner sends the original CSV privately from Cloud Shell through existing,
previously host-verified SSH to `/home/opc/groq-provider-usage.csv` (mode 0600).
Actions supplies public recovery code only. On Oracle the root controller reads
that private local file with no-follow/owner/mode/link/size checks and validates
its exact SHA-256 before any import or call. Missing input returns
`awaiting-owner-private-csv-upload` with zero API calls. The original full
nine-case summary remains independently retained by the owner; Oracle stores
only its SHA-256 reference and preservation status, not a fabricated cache.
A temporary private RSA transport key from preparation remains root-only on
Oracle and is not used by this direct-upload route. It is not an application
master key, API key or SSH identity. No custody or authentication operation on
those keys is performed by the upload route. Neither the Groq credential nor
provider history is supplied to GitHub; no public endpoint/resource is created.

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
