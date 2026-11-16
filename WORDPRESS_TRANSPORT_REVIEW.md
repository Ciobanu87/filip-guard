# WordPress HTTPS transport — development review

Base: `eb4f2e3c6cf8625917af8778481a4e73d641bcc3` on
`filip-guard-development`. The user approved a local commit of this review and implementation; no push,
deployment, or changes to `main` were performed.

## Changes

- `wordpress_secure_https.py`: strict, bounded HTTP/1.0 and HTTP/1.1 GET response
  parser. Returns status, immutable header pairs and decoded body through
  `parse_http_response`; `secure_https_get` preserves its raw-bytes return API.
- Rejects invalid status/header syntax, obsolete folded headers, control bytes,
  duplicate/invalid Content-Length, conflicting framing, truncation and extra
  bytes after explicitly framed bodies. Handles ordinary chunked bodies.
- Limits: 2 MiB for the entire wire response; 64 KiB for status plus headers;
  8 KiB per header/status line; 100 header fields.
- Redirects (all 3xx), informational responses (1xx), compression, chunk
  extensions, trailers and protocol upgrades are deliberately rejected. This
  conservative subset can reject otherwise valid HTTP responses.
- Hostname, path and timeout checked before opening the connection. Requests
  explicitly ask for identity encoding. IPv6 Host values use brackets.
- A monotonic I/O deadline prevents extending reads indefinitely by sending
  occasional bytes. Sockets are closed on success and failure.
- TLS no longer hides abrupt EOF (`suppress_ragged_eofs=False`), so a truncated
  close-delimited response cannot be accepted merely because the peer drops TCP.
- Existing connection unit tests now use controlled public DNS records instead
  of relying on live network access. No production URL/DNS checks were relaxed.
- Scanner, AI Advisor, UI and adapter implementation were not modified.

Protocol reference: [RFC 9112, sections 4–7](https://www.rfc-editor.org/rfc/rfc9112.html).
This is a limited transport implementation, not a complete HTTP client.

## Verification

Runtime: Python 3.12.14. Command:

```sh
python -m unittest discover -s . -p 'test_*.py' -v
```

Result: **82 tests passed; no failures or skips**. This includes five real local
TLS tests (trusted certificate, hostname mismatch, untrusted certificate,
chunked response, abrupt EOF). These fixtures generate a temporary certificate
using the OpenSSL CLI and do not connect to any public WordPress site.

The pre-change suite had 57 tests after installing declared dependencies; two
failed because existing connection tests required real DNS. Those unit tests
now mock DNS; all 25 added tests pass. Parameterized subcases also cover malformed
responses, request injection, limits, deadline exhaustion and socket cleanup.
`git diff --check` passes.

Tests explicitly verify that the default `WordPressConnection.verify()` guard
and `create_safe_session()` still block authentication/session creation.
GitHub Actions was not triggered, so its Python 3.11 result is unverified.

## Remaining work before enabling authentication

1. Bound system DNS and the entire multi-address TCP/TLS connect phase. The
   current deadline bounds send/read after connection, and rejects a connection
   that has already exhausted the budget, but cannot interrupt DNS or prevent
   each address/handshake from using its existing individual timeout.
2. Extend real TLS failure coverage (e.g. expired certificates, handshake stalls,
   multi-IP fallback) and test controlled WordPress interoperability. Servers
   omitting TLS close_notify now fail closed and may require a deliberate
   compatibility decision.
3. The new transport remains standalone and unauthenticated. The legacy
   `WordPressAdapter` still uses `requests.Session` directly; its integration
   must route every request through the verified transport before credentials
   are permitted. The connection verification entry point remains blocked;
   that guard alone does not make direct legacy-adapter usage safe.
4. Define the authenticated API contract, JSON/content-type and HTTP error
   handling. A validated HTTP error response (4xx/5xx) is not API success.
5. Review strict-subset compatibility (1xx, compression, trailers/extensions)
   before adding support. Keep redirects disabled unless every target is
   separately authorized, resolved and pinned.
6. Validate the final integration and obtain explicit approval before enabling
   credentials or website changes. Backup, authorization and rollback work
   remains separate from this read-only GET transport increment.

No credentials were entered or transmitted, and no external website was edited.
