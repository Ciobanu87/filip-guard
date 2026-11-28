# Optional account verification and recovery

Development source only. No Oracle change, mail, new key or service activation
was performed. Existing username/password sign-in remains unchanged; this is
mailbox control verification, not proof of a person's identity. Public signup
stays disabled unless separately authorized. Commercial policy remains deferred.

## Boundaries implemented and tested offline

A signed-in customer re-enters their current password to request a verification
code for a recovery email. The ASCII address is validated and its domain normalized.
A cryptographically random 256-bit code expires after 15 minutes and is consumed
once. SHA-256 digests are stored for matching. Pending delivery is encrypted with
AES-GCM under an HKDF-derived purpose key from the **existing retained master**;
AAD binds account, purpose, recipient, contact epoch and credential version.
No alternate master, temporary plaintext token file or GitHub secret is created.

The existing private auth database holds contacts, challenges and rate reservations.
Contact addresses are private account data, not public metadata. They must not be
logged or exported to GitHub. An address becomes verified only when its code is
confirmed. Once verified, changing it is blocked pending separate owner review;
there is no unverified address replacement or mailbox-loss bypass.

Recovery requests return the same message for unknown/unverified/rate-limited
accounts. Only an active account's already verified address can receive a reset
code. Per-purpose limits are three requests per account/name per hour and thirty
requests globally per hour, persisted transactionally. Unknown-name floods cannot
create unlimited limiter rows within a window. New requests invalidate previous
codes of the same purpose; contact changes and password changes invalidate older
challenges. Concurrent confirmations can consume a code only once.

Password reset uses the existing scrypt password policy, preserves customer ID,
site ownership and encrypted credentials, revokes all previous sessions, clears
pending contact changes and requires a fresh login. Old session-bound repair
approvals cannot be used by the new session. AI history, budgets, backup keys,
WordPress credentials and other customers are not reset.

The existing monitoring worker claims at most one account message per iteration.
A durable `sending` reservation happens before decryption/network use. A crashed
or uncertain send is not automatically repeated. Expired/cancelled/sent payloads
are cleared; only the hash remains. Codes/passwords use password widgets and
clear-on-submit forms; no URLs carry codes and no automatic login follows reset.

Account mail and monitoring alerts share `smtp_daily_budget` in the same private
monitor DB, so their combined attempts cannot exceed its configured deployment
limit. Failed/unknown sends retain reservations. This is an application cap, not
proof of the provider's current plan or allowance for other applications.

## Prepared configuration, still disabled

`FG_ACCOUNT_RECOVERY_AUTHORIZED=1` **and** `FG_EMAIL_AUTHORIZED=1` are both required;
neither is enabled by this work. The account DB must match `FG_CUSTOMER_AUTH_DB`,
existing complete guard state must validate, and the retained mounted master and
`FG_GUARD_KEY_ID` must be available. Existing `FG_SMTP_CREDENTIALS_FILE`, approved
sender/host and `FG_SMTP_DAILY_LIMIT` configure the existing verified-TLS sender.
No secret is entered through chat, repository, environment example or UI form.

Before authorized deployment: install the reviewed source while services remain
held, prepare additive account tables using the existing auth DB, and include them
in the next encrypted **full-state** backup/recovery drill. Never initialize over
existing accounts or reconcile by deleting session/history/budget tables. The
old one-database external drill does not establish recovery of these new tables.

Remaining live validation requires owner-approved free SMTP configuration, sender
and consenting owner mailbox, followed by bounded actual verification/reset and
session-revocation checks. No real mail was sent by the tests. Without a previously
verified accessible mailbox, account recovery requires independent owner review;
knowledge of the username or WordPress password is not a recovery substitute.


The 2026-11-28 fixture now proves encrypted full-state recovery retains a pending
account code together with a held AutoFix journal. The restore marker remains
intact; this is not a live Oracle/B2 drill or authorization to replay recovered
mail. Password changes also recheck session revocation inside the credential
transaction, so logout between initial validation and transaction blocks change.
