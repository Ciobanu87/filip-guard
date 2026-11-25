# Groq evaluation recovery after loss of the Colab ledger

The recovery tool inspects owner-supplied JSON reports offline and produces a
private summary of accepted immutable fixtures, source hashes and recomputed
observable checks. Keep this derived summary private together with the original
reports; do not commit either. Reports are unsigned historical evidence, not a
cryptographic provider attestation. Human semantic scores remain unestablished.
No report text, keys or account data should be published.

## What cannot be recovered

These JSON exports do not contain the full request/reservation ledger, original
request times, all provider attempts or all raw model selections. Cached successes
are repeated across exports. Summing usages or `new_provider_responses` would not
establish complete lifetime/day consumption. Old 429 headers are historical
snapshots, not current quota or a known absolute reset time.

Recovery therefore creates no SQLite database, budget allowance, API key, cache
entry, cooldown expiration or live-app validation receipt. Historical acceptance
is not replayed as fresh live-site advice. No model call is made.

## Reproducible recovery

From an existing checkout (the same Colab session is sufficient):

```python
from advisor_report_recovery import recover_reports, write_recovery
# paths are the existing seven downloaded report paths; no key is accessed.
recovered = recover_reports(paths)
write_recovery(recovered, 'quality-recovery.json')  # refuses overwriting
```

Or `python advisor_report_recovery.py --output quality-recovery.json REPORT ...`.
The generated receipt is a private historical summary, not `ledger.sqlite`.
Retain original JSON exports for independent review. Duplicate files are deduplicated
by canonical content, not filename. Failure/error cache entries are never restored.

## Safe continuation and Streamlit

Runtime `configured_advisor()` now refuses a missing, symlinked or invalid existing
ledger instead of creating a fresh usage budget. The public-scan bridge and Colab
UI probe already refuse a missing ledger. Direct `ContextualAdvisor` construction
remains an explicit development provisioning API, not a history recovery method.
Do not change the ledger path, recreate it or remove counters to bypass this hold.

First recover the original SQLite ledger, if it survives in a mounted Drive,
existing runtime object path or a private state backup. If it is irretrievably
lost, actual provider usage must be reconciled by the owner/operator before any
new inference budget is provisioned. These reports alone cannot authorize that.
Do not infer an expiry from an undated 429 export. Keep using deterministic rules
while new calls are blocked. The nine accepted cases need no further inference.

Use the existing private provisioning and encrypted state recovery procedure in
`STREAMLIT_TEST_AI.md` and `APPLICATION_STATE_RECOVERY.md`. Keep public registration
disabled. Streamlit secrets must be entered privately in the owner dashboard;
never put the Groq key, encryption key or account password in chat/GitHub. A
Streamlit secret is configuration, not a durable SQLite volume. Enable the single
new authenticated UI probe only after actual usage/state reconciliation; it must
not regenerate the nine fixture cases or label historical evidence as a new call.
