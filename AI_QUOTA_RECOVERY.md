# Groq 429 recovery and one-call validation

Latest status: the owner obtained one accepted real response (232 tokens, 1.258s).
Its context selection was weak and its missing-content claim contradictory.
See [AI_QUALITY_CONTINUATION.md](AI_QUALITY_CONTINUATION.md) for the corrected
quality gates and current nine-case continuation. The completed connection probe
is not repeated; quota controls below remain in force.

## Demonstrated cause

The owner's report for `2b30a3fa35664de55930b20ff6649363cba646b1` contains a
`cached-failure` with HTTP 429 / `rate_limit_exceeded` / `tokens`, no new provider
responses, and six unrun cases. That run did **not** send a new inference request.
The old `attempted_cases: 1` counted a cache lookup, not an API attempt.

The implementation stored every failure against the request fingerprint for ten
minutes. It did not retain a provider-wide quota deadline. Consequently a known
429 appeared to be a persistent invalid-response cache result, an eligible retry
could remain hidden behind the generic TTL, and changing request scope could
cause another quota-blocked call. These are cache/admission-policy defects, not
proof that the model is unavailable or that recommendations are invalid.

The report has neither a retained Retry-After nor a quota-period marker or
remaining/limit numbers. `tokens` does not distinguish TPM from TPD. The applicable
account reset time and exact available token balance cannot be inferred from it.

## Correction without bypassing budgets

- 429 now creates a **persistent provider/model-wide cooldown**, separate from
  semantic/auth/schema failure caching. Other customers/sites cannot evade it.
- The report distinguishes `provider-cooldown`, request-specific `cached-failure`,
  fresh provider limits, cached valid advice and local minute/daily admission.
  Cached valid advice stays available without an API request.
- Legacy 429 rows are migrated without deleting their records or refunding their
  call reservations. Existing daily-budget counters are not lowered/reset. A
  retry after expiry is a new paid-in-quota reservation, not a reused free attempt.
- Numeric/date Retry-After, safe duration hints and allowlisted rate-limit headers
  are retained without raw messages, headers, model payloads or credentials.
  Delays longer than one hour are no longer silently dropped.
- A minute-token reset is used only when the provider identifies TPM. It cannot
  be used to shorten a daily/unknown token limit. Longer active cooldowns are never
  replaced by shorter ones.
- An old 429 with unknown expiry receives a **conservative local 24-hour backoff
  from its original reservation timestamp, plus a 20-second request-duration margin**. This is explicitly NOT a confirmed
  provider reset. Nothing retries automatically at that time. A manually requested
  single probe may still receive 429, in which case a new provider deadline is
  recorded. The provider remains authoritative. No key/account rotation, database
  deletion, runtime restart, budget reset, billing upgrade or limit circumvention.

## Verified public limits and honest token estimates

Groq's official Free-plan table checked on 2026-11-24 lists, for
`qwen/qwen3.8-27b`: 30 RPM, 1,000 RPD, 8,000 TPM and 200,000 TPD.
Limits apply to the organization; exact account exceptions are visible only in
its Limits settings. We have not accessed the owner's settings or key.

Source: https://console.groq.com/docs/rate-limits

The revised `craft` probe keeps all observed evidence, indexed schema, priority
floor, normalizer and safety validator. Redundant prompt wording and JSON spaces
are removed. Prompt-plus-schema UTF-8 bytes fall from **1,778 to 1,367 (~23%)** on
this fixture. The request is 1,752 bytes. The heuristic estimate is **342 input
tokens**, not a tokenizer measurement or billing guarantee. Actual provider usage
and limit headers are reported when a response is available. The output reservation
is reduced from 1,200 to **256 tokens for the one-finding probe only** (~79% lower).
Full multi-finding analysis retains its existing output limit. The one-finding
indexed JSON contract passes simulated tests under that limit; real quality and
actual token use still require a real accepted response.

Lowering request size does not restore exhausted organization quota. Other apps
can consume the same allowance. No claim is made that this request must fit the
owner's remaining balance merely because it is smaller than the public TPM cap.

## Phone-only next step

Reopen the updated GitHub Colab notebook; reuse the existing `GROQ_API_KEY` Secret
and default free CPU. Do not change the account, buy a plan, erase the ledger or
restart a runtime to get around quota.

The notebook now runs **only one `craft` case**, with at most one provider attempt
and no retry or sleep loop. If cooldown/daily/minute admission is active it makes
zero API calls, records `attempted_cases: 0` separately from `evaluated_cases: 1`,
and reports the next eligible UTC time and whether it is provider-confirmed or a
local conservative estimate. If it is blocked, wait until the displayed time;
do not repeatedly click run. The key is never changed or printed.

After expiry, request one probe manually. Download the sanitized JSON. A fresh
real provider response plus accepted selection is required before considering
full evaluation. Cached advice alone does not qualify. Even an accepted probe
keeps `quality_validated=false`; it is not a quality benchmark.

The server validation command now also defaults to one probe:
`python validate_cloud_advisor.py --authorized-live-test --output /private/new.json`.
Full evaluation requires explicit `--full-evaluation`; it is not automatically
triggered by the notebook or probe. Existing source refresh, Python-import refresh,
legacy-ledger preservation, same API key and no-overwrite reporting remain intact.

## Tests and remaining limits

Tests cover legacy 429 migration, fresh/expired quota state, cross-scope and
restart protection, retained daily usage, valid-cache reuse, persistent semantic
failures, safe header metadata, TPM/TPD separation, long Retry-After, compact input
semantics and at-most-one-call probing. Model responses remain simulated in Work.
No new real inference or actual owner-account quota query has been performed.
All WordPress authorization, explicit approval, backup and rollback protections
are unchanged. Work remains exclusively on `filip-guard-development`.
