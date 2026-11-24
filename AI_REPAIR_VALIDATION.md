# AI response repair — evidence and remaining validation

## What the owner's real report proves

The report for revision `799ed65a2196cf5de2fec4b9e5e44a9e14bb7b7e`
records seven attempted cases, three new successful provider responses and zero
accepted model recommendations. The first three took 1.035–1.55 seconds; the last
four took about 10 seconds with no newly accepted provider response. All visible
recommendations were deterministic fallbacks. Successful API responses establish
that this model/key path worked for those three calls, not that AI quality passed.

In that revision `successful_exchanges` incremented only after HTTP success,
model identity/completion/usage checks and JSON parsing. The first three failures
therefore occurred **after** those checks, in the selection-validation pipeline.
The exact rejected field cannot be reconstructed: the prior broad exception
handler discarded the reason and did not retain model selections. The final four
could not be classified as HTTP quota, authentication, framing or network timeout
from this report. Their duration alone does not prove any one cause. No replacement
model or paid tier is justified by this evidence.

## Demonstrated implementation defects and corrections

1. The requested generic schema admitted arbitrary finding/evidence IDs, focus
   labels inconsistent with a particular finding, priority downgrades and free-form
   drafts that the downstream guard rejected. Reproduced examples show valid JSON
   failing with `draft_unsupported`, `evidence_binding`, etc. This proves a schema/
   guard mismatch; it does not prove which field the owner's model selected.
   The cloud request now indexes required objects by actual finding ID, enumerates
   same-page evidence IDs and allowed priorities, derives the known focus on the
   server, and copies an optional draft only from the selected observed excerpt.
   The original guard still validates normalized selections; it is not bypassed.
2. All failures were collapsed into one status. Allowlisted diagnostics now report
   stage/code, HTTP status and bounded numeric Retry-After, without request headers,
   provider bodies, exception messages or secrets. Cached failures retain the safe
   reason. Separate stages cover connection, send/read, HTTP/JSON, provider envelope
   and semantic selection. Fresh provider responses and accepted advice are counted
   independently in the report.
3. The cloud reader waited for peer EOF even after a complete Content-Length or
   chunked response. A regression test reproduces a complete response followed by
   peer idle timeout; the new reader validates the framed boundary and returns
   immediately. Truncated/ambiguous/oversized bodies remain rejected. This is a
   demonstrated transport defect, **not proof** it caused the four old delays.
4. Reopening the old Colab notebook reused an existing checkout and already imported
   modules. It could keep executing old code after a development push. Setup now
   resolves the remote development SHA, uses a revision-specific checkout, verifies
   that SHA and clears imports from the prior checkout before loading new code.
   The printed revision and report must match the intended new code. Existing
   secret custody and quota reservations are preserved, not erased.

The prompt/cache version is incremented, so incompatible old results are not
mistaken for the new contract. The existing API key, selected Free model, provider
consent gates, global pacing/call budget, no-retry policy and AutoFix approvals
remain unchanged. No secrets or original private report were committed.

## Recommendations and language

Advice now includes observed condition/cause, impact, solution, priority rationale,
risk, evidence, explicit missing information and EN/RO rendering. The underlying
root cause is marked unverified when only Scanner evidence exists. English and
Romanian wording comes from reviewed templates around model-selected evidence;
this is **not free-form model translation**. Extractive drafts stay in the original
page language. Changing display language reuses the checked selection and does not
spend another inference. No automatic execution is introduced.

## Next real run and interpretation

Reopen the updated development notebook from GitHub (not an old saved copy), reuse
`GROQ_API_KEY` in Colab Secrets, confirm the Free/synthetic-test checkboxes and run
all cells. Do not paste or regenerate the key for this repair. The setup preserves
an existing legacy ledger when moving to the shared test-state directory. The
seven-case batch is still bounded; the session daily cap remains at most 20.
If prior trials have exhausted it, stop and wait rather than reset limits or pay.

The report now includes `accepted_ai_cases`, `attempted_cases`, `fallback_cases`,
rejection stage/codes, provider usage where available, contract version, language,
latency and separate new-provider/selection-valid flags. HTTP 400/401/403/404/422/429
stops further calls; two consecutive network-stage failures also stop the batch.
Unrun cases are explicitly `not-run`, not failures or successes. No retries or
upgrade are performed. The owner should return this sanitized JSON, not a key.

A semantic failure now names its predicate; an HTTP failure identifies its status;
a connection/read timeout identifies the stage. These are the missing observations
needed to resolve any remaining actual-provider incompatibility. Newly accepted
responses can then be human-scored for relevance, factuality and language; the
report leaves those scores unset and `quality_validated=false`. Rule-derived
correctness or fallback abstention is not counted as demonstrated AI reasoning.

Automated tests cover indexed-schema binding, retained rejection guards, complete
HTTP framing, safe diagnostics/redaction, quota and network-stop behavior,
EN/RO/cache reuse, notebook refresh, account isolation and existing WordPress
approval/backup/rollback. These tests use simulated model responses. No new live
inference was executed in Work: the owner's key remains in their Colab Secrets.
