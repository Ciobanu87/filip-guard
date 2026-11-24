# Authenticated application + live Groq: one new integration probe

The nine owner-accepted quality cases remain complete and are not rerun. Their
separate Colab evidence does not prove live inference through the authenticated
Streamlit application. `validate_app_ai.py` closes that test gap using the actual
`app.py`, account login, Scanner path, owner-scoped Advisor invocation, visible
model provenance/evidence, Romanian language switch and login/reload of saved
advice. It rejects cross-customer inference before any model invocation and checks
that no WordPress change, repair history or apply control was activated.

This probe uses one distinct synthetic maintenance-guide context. WordPress and
object storage are explicit local simulators; the application/account/Scanner/UI
code is real. A real Groq provider may be used only with `live=True`; other
providers are rejected before fixtures or network work. A one-invocation wrapper
prevents accidental UI reruns from initiating another inference. The existing
shared Groq ledger, 20/day bound, provider cooldowns and pacing remain unchanged.
No production secret, public site, deployment or email is involved.

Offline unit tests drive the full UI with a simulated model, verify only one
inference across language change and re-login, and verify private success receipts
cannot be confused with new inference. They do not claim real Groq integration.
The owner-key live probe must run in the existing Colab runtime because the key
is available there, not in this development worker. A pinned one-cell loader
prepares this without editing multiple notebook cells or replacing the key.
It requires all nine prior fixture successes before a new provider call.

A private accepted live receipt is reusable with zero new requests. Replaying a
receipt is labelled historical and `real_inference_executed=false` for that run.
Corrupt/incomplete receipts fail closed instead of silently repeating a call.
The receipt is evidence of this small test, never customer/site authorization,
backup proof or commercial-release approval. No new quality scores are inferred.


## Owner continuation

The one-cell loader is `colab_validate_app_ai.py`. It pins the validated test
implementation, installs existing app dependencies into the current free CPU
runtime without restarting it, requires the existing ledger and all nine prior
successes, and reuses the existing in-memory key before considering one Secrets
RPC. The copied session-only holder is invalidated after the probe without
changing the owner's existing holder/key. No credential is saved to disk/env.

This is at most one new, distinct app-integration call, not another quality-suite
run. A daily/provider limit blocks it normally; no ledger, cooldown, allowance or
old reservation is reset. The result is automatically downloaded as
`app-ai-validation-*.json`. An accepted real receipt is saved privately beside the
ledger so another execution costs zero new calls. The nine prior successes remain
unchanged. This live step cannot be executed in the development worker because
it has no authorized access to the owner's Colab-only key.
