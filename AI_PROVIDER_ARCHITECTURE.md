# Provider independence without changing the current provider

The existing architecture already separates the application from inference
transport. This continuation retains that design and does not add/enable a new
real provider, run an inference service or alter Oracle configuration.

| Boundary | Existing responsibility |
| --- | --- |
| `AdvisorProvider.generate` | Bounded messages/schema input and structured selection output |
| `ContextualAdvisor` | Sanitized evidence, selection validation, tenant-scoped cache, shared durable budget, safe fallback |
| `advisor_groq.GroqFreeProvider` | Current Groq transport, explicit credential readiness, fixed HTTPS origin, free-plan/consent prerequisites |
| `configured_advisor` | Operator-controlled allowlist and provider/model selection; no dynamic imports from customers/models |
| Application and monitoring | Explicit on-demand advice; monitoring does not invoke inference or authorize repairs |

The already-existing local adapter remains opt-in and inactive. No new adapter
is registered in configuration. A future approved provider implements the same
contract and is explicitly registered in the trusted factory; the application,
Scanner, ownership directory and repair engine do not need reconstruction. This
is not automatic failover: provider changes, live validation and any cost-bearing
operation still require the owner's authorization.

## Shared protections and isolated provider metadata

Cooldown admission now applies to every adapter using the shared engine, rather
than only a hardcoded Groq name. A provider's cooldown is keyed by provider/model,
while the daily call budget remains global across adapters and customers. Changing
an adapter must not create a new budget. Cache identity already includes provider,
model and the authenticated customer/site scope.

Original historical 429 rows lacked provider identity. Only the existing Groq
adapter explicitly declares `legacy_quota_recovery=True`, preserving its prior
reconciliation behavior. An unrelated future adapter must not reinterpret those
legacy rows as its own quota event. New quota responses use the provider/model
key directly. There is no deletion, refund or reset of historical reservations,
consumption, cooldowns or the nine accepted live evaluation results.

The new generic/indexed adapters in tests are simulations only, not selectable
services. Tests cover structured compatibility, cross-adapter global budgets,
cache separation, generic cooldown persistence across restarts/tenants, and
absence of legacy-quota contamination. They do not demonstrate the semantic
quality, billing status or live availability of any new provider. Groq remains
the current configured provider; no secret or runtime flag is changed here.
