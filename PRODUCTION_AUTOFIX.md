# Production AutoFix candidate — implemented, not activated

The existing exact-link engine is reused. This adds a separately gated production
route, not an automatic upgrade of the test workspace or a general WordPress
maintenance tool. No production policy, live-validation receipt, credential,
companion constant, Oracle file or service is provisioned by this change.

## Admission and trust boundary

The existing `.test` workspace and `FILIP_GUARD_TEST_REPAIRS` gate keep their scope.
They cannot enable production. A separate factory requires
`FG_AUTOFIX_PRODUCTION_AUTHORIZED=1`, private policy/validation files, the exact
reviewed release commit, existing complete private application state, retained
master and configured external encrypted backup. Test and production UI flags
cannot be mixed. Missing/invalid artifacts fail before state/secrets/provider use.

On WordPress, production additionally requires BOTH explicit constants:
`FILIP_GUARD_PRODUCTION_REPAIRS === true` and
`FILIP_GUARD_PRODUCTION_POLICY_JSON` containing the **same canonical policy bytes**.
The repository example sets neither to an active value. App and WordPress admissions
are separate; neither a browser field, AI recommendation, diagnostic boolean nor
the test flag grants production authority.

The private policy is operator authorization, not a secret or a signed attestation.
Its receipt hash binds a trusted operator-reviewed validation record; it does not
prove arbitrary fabricated JSON is true. The trusted operator/host and WordPress
owner control these artifacts. Never create `passed` observations from assumptions.
The application supplies no tool that manufactures a successful live receipt.
Existing host startup approval, Always Free/zero-cap evidence and service activation
review remain required; this route does not bypass `operations_host_gate.py`.

## Exact artifact contracts

Policy JSON must be ASCII canonical JSON (`sort_keys=True`, compact separators,
no trailing newline), a private regular file with no group/other access, at most
32 KiB. Unknown/duplicate fields are rejected. Required fields:

| Field | Requirement |
| --- | --- |
| `protocol`, `profile` | `filip-guard-production-v1`, `classic-html-link-v1` |
| `site_url` | Exact canonical HTTPS origin; no subdirectory, credentials or alternate origin |
| `source_commit` | Reviewed 40-character commit, equal to operator `FG_RELEASE_COMMIT` |
| `wp_version` | Exactly WordPress 7.1.5, pinned by the existing verified CI fixture; other versions stay blocked |
| `theme_sha256`, `companion_sha256` | Actual reviewed theme manifest and current companion source digests |
| `content_selector` | Reviewed unique content container, e.g. `article#post-{resource_id}` |
| `resources` | One to ten distinct `{kind: post/page, id: positive integer}` targets |
| `approved_at`, `expires_at` | Integer timestamps; explicit window at most one hour; no auto renewal |
| `validation_sha256` | SHA-256 of the separately retained private live-validation record |

Receipt protocol is `filip-guard-production-validation-v1`. It contains exactly
`target_origin`, `validation_origin`, `environment`, `source_commit`, `wp_version`,
`theme_sha256`, `companion_sha256`, `content_selector`, `validated_at`, `checks`,
and `protocol`. The canonical validation origin must differ from the target and
be an authorized local/development/staging copy. The record must be at most seven
days old at approval; release/profile fields must match. `checks` must contain
exactly `identity`, `compatibility`, `backup_restore`, `conditional_write`,
`independent_verification`, `rollback`, `recovery`, `tenant_isolation`, all proven
true by the authorized trial and retained evidence. No actual receipt exists for
the user's environment yet; CI creates explicitly synthetic fixture records only.

## Supported runtime profile, checked again before conditional writes

Single-site WordPress 7.1.5, exact reviewed theme/companion, only FILIP GUARD companion active,
no MU plugins or drop-ins, only reviewed core metadata keys, authenticated site
administrator, HTTPS and Application Password. Inventory binds exact resource,
revision/content hash, time (at most five minutes) and matching policy digest.
The gateway re-reads admission before each authenticated request; the companion
checks its own profile too. Version/theme/plugin/metadata/policy drift fails closed.
These are request-time drift checks, not a filesystem-wide atomic lock against
an administrator changing configuration mid-request. Freeze deployments/updates
for the reviewed admission window; post-row CAS remains the atomic write fence.

Only exact **quoted href-value** changes in classic post/page HTML are admitted;
no text/attributes/layout/settings/plugin/builder changes. Raw/inert/base content,
Gutenberg, shortcodes and known builders remain unsupported. The server tokenizes
anchor attributes so href-looking text inside title/data attributes is not authority.
Published destination candidates may be read outside the mutation resource list;
only listed source resources can produce production mutation plans.

## Integrated execution and recovery

1. Scanner records scoped missing-destination evidence, source/permalink inventory
   and time; only unambiguous 404/410 findings can propose a replacement.
2. The application registers the exact repair flow; AI has no execution authority.
   Prewrite recomputes the exact change from its retained diagnosis and rejects a
   direct unregistered/arbitrary content plan. Restore binds the verified parent.
3. Current-session exact approval, fresh scan, reachable destination and current
   resource version are checked. No implicit or cross-session approval is accepted.
4. Existing durable preparation claim precedes encrypted external upload/readback.
   Admission/flow are checked again after backup, before approval consumption.
5. The production gateway obtains fresh bound compatibility evidence. WordPress
   enforces policy/resource/profile and performs the existing full-row atomic CAS.
6. REST verifies exact stored content/version. A separate unauthenticated pinned
   HTTPS GET verifies changed anchor counts in the single reviewed public content
   container; navigation links outside it do not count. The replacement is checked
   again for a repair. A restore need not make the original broken target healthy.
7. Failure invokes only the existing conditional rollback against the exact write
   receipt, then verifies REST AND independently rendered restoration. A concurrent
   edit wins; failed/uncertain restoration stays held, never silently successful.
8. Manual restore requires a fresh proposal/explicit approval, a verified applied
   parent, unchanged current revision and retained content. It follows the same
   backup/conditional/public-verification path. Unknown outcomes remain held; the
   read-only recovery inspection cannot authorize retry or infer operation ownership.

A policy expiring/revoked mid-operation blocks further production requests, including
rollback if it can no longer be authorized. Preserve backups/journal and obtain
fresh reviewed recovery admission; do not bypass revocation to get a green result.
Authenticated local history remains accessible with expired admission while the
workspace is configured. Fresh remote inspection/mutation needs active admission.
No new retry loop, provider, key, schedule or automatic service activation is added.

## Remaining operational gates

An owner-authorized disposable copy matching the intended environment must produce
actual compatibility/backup/public-verification/rollback/recovery evidence, with
operator review of that record. Then prepare private admission on both sides for
a specific release/window/resources. Existing Oracle source installation, full
actual-state encrypted recovery, host approval, HTTPS access and service activation
remain separate unperformed operations. No real site or Oracle validation is
claimed from local/CI fixtures. SMTP/commercial work is not a prerequisite for the
repair algorithm; it remains separately held as previously documented.
