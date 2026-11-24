# Cloud AI validation — first owner responses received; quality still pending

Update: the owner completed the first real run (three provider responses, zero
accepted selections). See [AI_REPAIR_VALIDATION.md](AI_REPAIR_VALIDATION.md) for the
evidence, corrections and updated notebook. Prior setup details below remain
applicable; the original no-inference statements describe preparation only.

This extends the existing provider protocol and preserves Ollama, Scanner rules,
evidence validation, the explicit customer AI button, and all WordPress approval/
backup/CAS/verification/rollback gates. Nothing deploys or changes `main`.

## Choice checked against official documentation (2026-11-24)

| Candidate | Relevant verified offering | Decision |
| --- | --- | --- |
| Groq Free / `qwen/qwen3.8-27b` | Free-plan limits list this model; strict JSON-schema output; multilingual model; Developer upgrade requires a payment method | Selected for bounded synthetic evaluation; owner must confirm the actual organization is Free with no billing/upgrade |
| Gemini Developer API | Free tier for selected models; structured output; account/model availability and unpaid data terms require attention | Viable alternative, not integrated as a second dependency; does not remove the owner-key requirement |
| Ollama local | Already implemented; needs installed model/runtime resources | Retained; not required for a phone-only owner |

No provider is assumed to be free simply because it has a key. At review time
Groq's rate-limit page lists 30 RPM, 1,000 RPD, 8,000 TPM, 200,000 TPD for the selected
model's Free tier, while exact organization limits may differ. A payment method
is needed to upgrade to Developer. Do not upgrade, add a payment method, buy
credits or request a paid host. Free quotas can change or be exhausted.

The application cannot determine billing tier from a completion response. The
operator's Free-plan confirmation is a required account check, not a technical
billing lock. If an organization is later upgraded, local limits alone cannot
promise zero cost. Remain on Free. The adapter never performs billing operations.

## Security and integration

`GroqFreeProvider` implements the existing `AdvisorProvider` contract without a
new SDK. The fixed destination is `api.groq.com:443`, path
`/openai/v1/chat/completions`. It reuses DNS-pinned, publicly resolved, certificate/
hostname-verified connection establishment and strict HTTP response parsing. It
does not change WordPress transport/header policy or support arbitrary endpoints.
Bearer credentials are sent only to that destination. Redirects, partial replies,
invalid framing, wrong model, tool/function calls, refusals, missing usage and
truncated JSON fail closed. Errors contain no provider payload or secret values.
Sockets close in all cases. No retries, tools, streaming or reasoning output.

The existing sanitized evidence bundle uses opaque IDs, not customer/site URLs,
query tokens, WordPress credentials, cookies, forms, raw HTML or exceptions.
Cloud input has an additional conservative 6,000-byte content/schema bound; output
is capped at 1,600 tokens, with a 20-second total transport limit. Model-reported
usage must be consistent and bounded, but is not independent token accounting.
The evidence validator still refuses invented SEO draft facts or new operations.

The existing durable ledger reserves calls before inference, isolates cached
results by customer/site and preserves failed reservations. The cloud path adds a
shared 61-second interval and a configured maximum of 20 calls/day. Rate-limited
UI requests return deterministic recommendations; they are not queued/retried.
These conservative application bounds do not replace organization-wide quotas.

Groq documents inference-data retention only in specified circumstances, optional
Zero Data Retention controls and US data location. No claim of unconditional zero
retention or EU residency is made. Enable available data controls and obtain
appropriate authorization before any client data use. The prepared live runner
uses **synthetic** content only. Nothing has sent customer data in this session.

## First real test from an Android phone

Open the development notebook:
https://colab.research.google.com/github/Ciobanu87/filip-guard/blob/filip-guard-development/notebooks/validate_cloud_advisor.ipynb

Use the free default CPU runtime. No GPU, Pro subscription, compute credit or
installation on the phone is needed. Colab is an interactive test session, not a
production host: resources are limited, storage/runtime state can disappear, and
we do not run a background service or tunnel around those limits.

1. Sign in to https://console.groq.com/keys and create an API key in a **Free**
   organization after checking billing/limits. If payment is requested, stop.
2. In Colab's Secrets/key sidebar, add `GROQ_API_KEY` and enable notebook access.
   Never paste its value into notebook code, GitHub files, reports or this chat.
3. Review the printed development revision, confirm the three explicit checkboxes
   and run the notebook cells. At most seven calls are paced 61 seconds apart.
   Download the sanitized JSON report; it includes no API key.

Missing keys, quota exhaustion or blocked regional/runtime access remain a real
blocker; no account cycling, credential borrowing or paid fallback is attempted.
The notebook has no executed outputs checked in. It clones only the development
branch and records the exact executed revision. This reproducible path is prepared
and its Python cells compile, but the Colab UI and a real Groq call have not been
validated without the owner's login/key.

## Existing authorized server configuration (optional; no host provisioned)

Use a mounted private secret file (0600/0400), never a secret in Git:

```
FG_AI_AUTHORIZED=1
FG_AI_PROVIDER=groq-free
FG_AI_MODEL=qwen/qwen3.8-27b
FG_GROQ_API_KEY_FILE=/run/credentials/filip-guard/groq-key
FG_AI_FREE_PLAN_CONFIRMED=1
FG_AI_CLOUD_DATA_CONSENT=1
FG_AI_LEDGER_DB=/srv/filip-guard/advisor-ledger.sqlite
FG_AI_DAILY_CALLS=20
```

Both confirmation flags are deliberately absent by default. Reuse persistent
private ledger storage across workers/restarts for an ongoing service. Do not
mistake Colab's temporary test ledger for production persistence. The key file is
read only when needed. Disabled/default configuration never retrieves a cloud key.

A bounded server-side validation command is also prepared:
`python validate_cloud_advisor.py --authorized-live-test --output /private/new-report.json`.
It refuses overwriting an existing report and never contacts WordPress. A failed
provider call is not retried. The report requires **new successful provider
responses** to mark real inference executed: cached recommendations alone do not
qualify. Even a successful request does not set `quality_validated=true`.

## Evaluation and remaining work

Seven representative synthetic cases cover business content, documentation,
nonprofit content, Romanian page text, unavailable content, a WordPress article
and filtered prompt injection. For each, record latency, source/fallback status,
fresh provider response, retained Scanner diagnosis, page-specific framing,
extractive draft or abstention, and no AutoFix authority. Include review samples
without secrets and record the source commit. Diagnostic correctness remains
rule-based; explanations are rendered from reviewed templates and selected quotes.
The Romanian case evaluates evidence/draft selection, **not fluent Romanian
model-generated explanations**. Filtering an injection is pipeline defense, not
proof of universal model injection resistance.

Current tests use mocked API responses/sockets. No real Groq inference, external
latency, stability or quality improvement is claimed. After owner authentication:
run the notebook, review all seven results, repeat on held-out English/Romanian
pages with human relevance judgments, and compare blind against the deterministic
baseline. Check acceptance/fallback rates and token/latency stability. Do not
infer reasoning quality from JSON-schema compliance or a page quote alone.

Official references:
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/billing-faqs
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://console.groq.com/docs/your-data
- https://ai.google.dev/gemini-api/docs/pricing
- https://research.google.com/colaboratory/faq.html
- https://codelabs.developers.google.com/onramp/instructions
