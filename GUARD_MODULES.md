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
