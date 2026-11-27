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
higher current local counter. Counters never decrease. The original CSV and
nine-case evidence remain private on the host as well as independently retained
owner uploads. Prior cooldowns are retained; the historical 429 receives the
existing conservative unknown-expiry policy anchored to its actual timestamp.
No fresh reset time or organization-wide remaining-token number is inferred.

Only public recovery code and authenticated encrypted evidence are committed.
A dedicated RSA-3072 transfer key stays root-only 0600 on Oracle; it is neither
an SSH identity nor an application master key. Only its public key is returned.
The CSV/evidence travel AES-256-GCM encrypted, with the data key RSA-OAEP-SHA256
wrapped to that server. Neither the Groq key nor a decrypting key enters GitHub.
The existing pinned SSH transports the ciphertext; no public endpoint/resource
is created. The Groq key is read only inside the existing unprivileged app user.

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
