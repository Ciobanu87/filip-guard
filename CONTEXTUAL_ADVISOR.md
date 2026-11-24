# Contextual Advisor — implemented integration, real quality not validated

Current status: the owner obtained three real provider responses but no accepted
advice in the first Colab run. See [AI_REPAIR_VALIDATION.md](AI_REPAIR_VALIDATION.md)
for the diagnosed boundary and prepared retest. Earlier preparation statements
below are historical; they do not supersede this owner-run evidence.

Update: a separate opt-in Groq Free cloud adapter and phone-accessible Colab
validation path are now prepared. See [CLOUD_AI_VALIDATION.md](CLOUD_AI_VALIDATION.md).
The local-provider details below remain applicable; no real inference is claimed.

The existing Scanner, deterministic `analyze_pages`, verified repair coordinator
and monitoring remain the sources of observations and authorization. The optional
model adapter enriches a user's explicit analysis request; it is not an agent
with tools. No cloud subscription, download, API key or inference call is enabled
by default. No real model has been run in this implementation session.

## Where context adds value

Previously the Advisor had status, title, metadata and counts only. Missing
metadata produced the same recommendation for every page, and the old title-only
text template invented “our services, benefits, and solutions.” That claim has
been removed. Scanner now optionally extracts at most five short public text
fragments per page. Scripts, forms, hidden containers, navigation and templates
are excluded; obvious instruction injection and common sensitive patterns are
filtered/redacted. Redaction is defense in depth, not proof all personal data can
be recognized. Only public sampled page text should be analyzed.

The model receives opaque page/finding IDs, sanitized text evidence and numeric
Scanner metrics, not page URLs/query parameters, customer IDs, credentials,
cookies, raw HTML, errors or the repair inventory. It chooses relevant evidence,
review priority and missing information for already detected problems. Evidence
must belong to the exact page. Missing/extra findings, unknown fields, tool calls,
priority downgrades and unsupported draft text invalidate the entire response.

Explanations, solution framing and risk language are rendered from checked
excerpts and reviewed templates. This intentionally restricts free-form model
claims. SEO draft text must be an exact 20–160 character excerpt of selected
observed content/title, or the model must abstain. This avoids invented business
facts, but does not prove an excerpt is relevant, current or an effective snippet.
No ranking or traffic improvement is claimed. Human review remains mandatory.

## Provider and deployment

`AdvisorProvider` is a replaceable Python protocol; business logic does not depend
on an SDK. The first concrete adapter is `OllamaProvider`, using official local
`/api/tags` and `/api/chat` JSON-schema APIs. Default candidate: `qwen3:8b`; supported
local alternatives are configurable in `FG_AI_MODEL`. This is a candidate for
assessment, not a quality endorsement or a validated production model.

The adapter connects only to fixed `127.0.0.1:11434`, without proxy environment,
redirects, authentication secrets or configurable remote URLs. It checks that the
explicit model is already installed. It never pulls weights or selects cloud
model names. Provision a trusted local-only model server with outbound network
disabled after separately authorized model installation; do not proxy this port
to a cloud service. A locally named model is not proof of an uncompromised server.
Bind the model service to loopback, isolate its process and retain model version/
digest provenance during real evaluation. This does not relax website HTTPS/SSRF
or WordPress Application Password protections.

Enable only on an authorized host with sufficient existing resources:

```
FG_AI_AUTHORIZED=1
FG_AI_PROVIDER=ollama-local
FG_AI_MODEL=qwen3:8b
FG_AI_LEDGER_DB=/srv/filip-guard/advisor-ledger.sqlite
FG_AI_DAILY_CALLS=20
```

These are operator configuration names, not values to commit into a live service.
Ollama/model installation and hardware provisioning have not been performed.
There is no per-token paid API adapter or automatic paid fallback. Local compute
still requires capacity; an existing free UI host may be insufficient. Do not
create a paid instance to run this model without separate authorization.

Requests have a 20-second maximum total transport deadline (15 by default),
bounded input/output bytes, 8,192 context window and at most 1,600 output tokens
(1,200 default). No retries, streaming, thinking output or tool definitions are
sent. Early EOF, wrong declared length, slow headers and invalid/truncated model
outputs fall back to rules. No raw model response or provider error is shown.
The adapter checks completion reason, model identity and reported output count;
provider-reported usage is not an independent measurement of physical compute.

A private shared SQLite ledger reserves calls before inference, persists a global
daily cap and allows only one in-flight request. Tenant/site-scoped fingerprints
cache successes for an hour and failures for ten minutes. Failures and expired
reservations do not refund spent calls. The ledger is for this deployment, not
other software sharing the local server. It must persist across restarts; no
background thread or ephemeral UI session owns the budget.

## UI and AutoFix boundary

The authenticated `app.py` workspace offers **Analyze context with AI** after a
scan. Ownership/session checks run before and after inference and on cache reads.
Advice is saved beside the immutable scan in the existing per-customer/site
workspace. Reconnections recover advice without reusing repair approvals.

The UI shows source (`rules` or `model-assisted`), model, detected problem,
contextual explanation/recommendation, priority and rationale, risk, exact evidence,
missing information and draft scope. The anonymous demo remains deterministic;
monitoring never starts model inference. The model cannot change deterministic
monitoring findings or mark an issue resolved.

All current model-enriched SEO recommendations are informational. Supported
WordPress broken-link proposals still come from Scanner findings and the existing
resource mapping. They require replacement reachability, fresh resource version,
exact diff, separate explicit approval, verified encrypted external backup, CAS,
post-write verification and conditional rollback. Model output is never converted
into commands, SQL, arbitrary REST operations or an approval token. No SEO
metadata repair is silently represented as supported.

## Evaluation and current evidence

`python advisor_evaluation.py` reports the deterministic baseline on five synthetic
cases: craft commerce, technical documentation, nonprofit information, Romanian
content and unavailable/insufficient context. Explicit rubric: correct detected
problem, page-specific solution, observed draft or abstention, missing context,
no unsupported AutoFix authority.

Contract tests with a **simulated evidence selector** achieve page-specific framing
on 4/4 text-bearing cases versus 0/4 with the old generic rule wording; all five
retain correct findings and avoid unsupported execution. This measures the
renderer/validation design, **not real model reasoning or a measured AI quality
improvement**. Neither relevance nor multilingual quality can be inferred from
these deterministic fixture results.

With an authorized installed model, `python advisor_evaluation.py --local-model`
uses the same rubric and global budget. The output deliberately leaves real model
quality unvalidated: human-reviewed judgments and broader holdout tests are still
required. Record actual model digest, accepted/fallback rate, latency, evidence
selection relevance and unsupported-claim rate. Add adversarial/incomplete pages
and multilingual holdout cases; compare against rules blind to source. Do not
claim an improvement merely because a response passes JSON validation.

Tests additionally cover real loopback HTTP framing/deadlines against a simulated
Ollama server, malformed JSON, forged evidence, hallucinated draft claims, schema
injection, unavailable models, no automatic downloads, quotas, cache/restart,
concurrent duplicates, account isolation and the unchanged explicit repair gate.
The real WordPress/MySQL UI journey uses **simulated model responses** while the
scanner, REST writes, backup encryption and rollback remain real.

Official API/model references checked 2026-11-24:
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/api/tags
- https://docs.ollama.com/capabilities/structured-outputs
- https://ollama.com/library/qwen3:8b

Outstanding: authorized model runtime, real inference, calibrated quality/latency,
independent adversarial review and human approval of SEO wording. This engine is
not declared final or ready for launch.
