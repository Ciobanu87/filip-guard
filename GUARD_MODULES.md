# Read-only guard modules

The versioned `read-only-guard-v1` contract composes independent checks with the
existing Website Scanner/Advisor. Commerce Guard observes configured public
catalog/product routes and optional Product JSON-LD price/currency expectations.
It never enters cart/checkout, adds products, places orders or tests payments.
API & App Guard checks configured public GET routes, expected HTTP statuses,
bounded JSON shape and optional exact nonsecret health values. It does not run
browser journeys, send authentication headers or execute requests with bodies.
Infrastructure Guard checks public A/AAAA addresses, verified TLS identity/expiry,
and opt-in authoritative RDAP expiration for an explicitly selected registered
apex containing the authorized host. No missing registration date is guessed.

Every module returns observations, deterministic recommendations and
`autofix=false`. Registry entries are trusted source code, never customer/model
imports. A future AI Agent Guard can implement the versioned contract after
separate authorization and validation; it is intentionally not registered or
implemented now. Existing WordPress proposals/approval/backup/CAS/rollback are
not changed by any module. No model inference is needed for these checks.

All HTTP requests reuse the existing DNS-pinned, certificate-verified HTTPS
transport. Redirects, partial responses, credentials, private/mixed DNS and
oversize/ambiguous responses remain blocked. Customer paths have no query,
fragment, credentials, traversal or known mutation/login/cart/checkout routes.
Only explicit public idempotent endpoints should be configured; an anonymous GET
cannot prove that a poorly designed remote server has no internal side effects.
No cookies, raw API/HTML bodies, response secrets or RDAP contact data are stored.

One shared per-run time/request budget covers Website Guard and extensions;
existing scheduler rate limits/leases remain authoritative. A partial or failed
check contributes no verified resolution scope. Successful and failed checks use
stable category/URL identities so recovered checks can resolve the right issue.
Removed/disabled checks do not prove previous problems resolved. No arbitrary
service ports, DNS record editing, certificate renewal, registrar access or domain
renewal is implemented. RDAP uses only IANA-discovered HTTPS services, binds the
returned domain identity and rejects ambiguous/missing expiration events.

Official protocol references inspected 2026-11-24:
- https://www.iana.org/assignments/rdap-dns
- https://data.iana.org/rdap/dns.json
- https://www.rfc-editor.org/rfc/rfc9224.html

Core tests use controlled HTTP/DNS/TLS/RDAP fixtures, not customer services or
new Groq calls. Real provider/store ownership, endpoint contracts and registry
coverage must be validated in an authorized environment before launch claims.

## Integrated scheduling, account isolation and UI

The existing `MonitoringService` now stores additive, owner-bound guard settings
in `monitor_guard_settings`. Website Guard remains the default. Selecting a new
module does not replace its Scanner/Advisor, repairs, historical results or
notifications. Checks flow through the same durable leases, request reservations,
per-site cadence, history, in-app inbox and existing email outbox. Changing module
settings fences an in-flight run and does not reuse its unique schedule slot or
refund any request. Network/budget failures stay unverified, rather than becoming
invented endpoint failures or false resolutions.

`app.py` exposes the controls through its existing monitoring section. Three tabs
separate module settings. Configure only public idempotent routes (at most three
per Commerce/API module); HTTP 206 and redirect statuses cannot be expected as a
successful health contract. JSON checks support up to eight required top-level
keys and one exact public text/boolean/integer health value. No expressions,
secret fields, custom headers or authenticated API requests are accepted. Product
checks support Offer prices and AggregateOffer ranges. DNS baselines are
canonicalized public IPs; certificate/registry timestamps and observed conditions
are shown as plain evidence. Unknown/missing domain registration data remains
unknown, not a fabricated expiry date.

## Independent non-WordPress resources

`GuardAssetDirectory` is an additive adapter over the existing WordPress directory.
Previously authorized WordPress sites need no new proof. An independent website,
store or API can instead prove domain control by publishing a random public token
at `/.well-known/filip-guard-verification.txt`. The caller must be authenticated;
proofs are bound to customer/origin, expire in 15 minutes, contain only a stored
SHA-256 digest, are consumed once, and permit at most five network confirmations
per hour/customer, at least 60 seconds apart. HTTPS identity, public DNS and exact
plain-text content are required; no redirect/reflection/query shortcut exists.
A fresh valid browser session cannot rescue an expired proof. Logout/revocation
during verification prevents the grant. Another account cannot take over an
already bound origin or read its settings/history.

The resulting read-only grant expires after 30 days; an expired grant disables
background scheduling and must be renewed. This is distinct from a browser session
and never creates a WordPress credential or repair permission. API-only resources
default to a single public root HTTP check, not a guessed health contract or a
Website crawl. The owner explicitly selects additional paths/expectations before
running those checks. Multiple guards can share the same authorized resource.

For a fresh authorized host without WordPress/S3/master-key setup, the operator
can initialize only the existing private account/site/monitor paths with:

```
python operations_guard_setup.py --initialize-read-only
```

This explicit bootstrap creates no account, password or key, makes no network
request and starts no worker. It refuses a nonempty site directory whose registry
is missing, so it cannot silently replace lost state. Restart uses the existing
configuration; initialization must never be used to hide a lost volume. Account
registration remains separately controlled by `FG_CUSTOMER_REGISTRATION`.

Unit/UI tests use synthetic resources and controlled protocol responses. Domain
file placement is a real proof prerequisite, not a simulated customer grant in
production. New model calls are neither necessary nor made by any guard. The
accepted nine-case Groq evaluation and prepared one-call authenticated-app probe
remain separate; this extension does not claim that pending live probe ran.
Permanent hosting, actual cloud recovery/key custody and real inbox delivery are
still operator-access launch gates, as documented in `deployment/OPERATIONS.md`.


## Real transport integration correction

The additional real WordPress checks exposed an Accept-header mismatch hidden
by isolated exchange mocks: the new guard requested a media bundle the shared
transport did not recognize. The fix adds one explicit, constant public-guard
media bundle to the existing allowlist. Arbitrary/wildcard/injected Accept values
still fail before connection. Hostname/TLS verification, DNS pinning, redirects,
response bounds, method/body restrictions and authorization checks are unchanged.
A wire-level regression test now exercises the actual transport validator and
checks anonymous GET/no-cookie behavior. No accepted Groq case is repeated.
