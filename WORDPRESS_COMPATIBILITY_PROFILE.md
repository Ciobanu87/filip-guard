# WordPress AutoFix compatibility: classic-html-link-v1

This profile narrows the existing broken-anchor-content repair. It does not add
new repair types, install anything or authorize production changes. `.test`
origin restrictions, the companion's nonproduction/test constant, HTTPS,
Application Passwords, per-resource permissions and explicit approval all remain.

## Content supported by this candidate

Classic HTML post/page content, within the existing one-megabyte UTF-8 limit,
for an exact reviewed href replacement. Both original and replacement are checked
before proposal, before the gateway write and inside the PHP conditional handler.
Gutenberg opening block markers, shortcode forms and known Elementor/Visual
Composer/Beaver/Divi markers are rejected. A conservative false positive requires
manual review, not stripping a marker to bypass the restriction. Unknown plugin
behavior cannot be inferred from content alone.

Backups contain selected content/revision evidence, not the whole site or builder
metadata. Restore uses the same profile, permissions, separate approval and
conditional concurrency checks; unsupported later content cannot be overwritten.
The endpoint still does a conditional post-row SQL update followed by its existing
hooks/revisions; it does not emulate every `wp_update_post` input filter.

## Environment evidence required before an isolated trial

`assess_compatibility` accepts a trusted snapshot and operator-reviewed evidence.
It binds exact site, resource type/ID, revision and content SHA-256, and rejects
evidence older than five minutes or dated in the future. Candidate scope requires:

- Local/development/staging WordPress 6.x, single-site.
- Only the reviewed FILIP GUARD companion active; no MU plugins or drop-ins.
- Reviewed theme fingerprint; no inferred generic theme compatibility.
- Only listed core metadata keys; builder/custom metadata remains a blocker.

The version range is an admission to isolated validation, **not a claim that all
WordPress 6.x versions were tested**. Evidence must come from an authorized
server-side inventory; no browser form or client-supplied dictionary can authorize
a write. The companion now exposes an owner-only authenticated GET inventory, protected
by the same nonproduction/test, TLS, Application Password and resource guards.
It returns only plugin/drop-in names, metadata **keys** (no values), runtime
version/environment and a bounded SHA-256 manifest of actual parent/child theme
files. Symlinks, more than 1,000 entries, 10 MB or two seconds of theme traversal
yield an unknown fingerprint. No absolute theme paths, credentials or metadata
values are returned. The gateway binds origin to its verified transport and
checks the snapshot identity. This collector is tested in disposable CI only;
unknown inventory remains blocked and must not be filled with assumed defaults.

Even complete diagnostic evidence returns `production_write_authorized=false`
and `live_compatibility_proven=false`. The global readiness report separately
requires `wordpress_compatibility_verified`; all its checks still cannot enable
writes. Content restrictions alone do not prevent arbitrary plugins from running
in an explicitly activated nonproduction test installation.

## Validation still requiring approval and actual environment evidence

Review the installed version, theme code/hash, active/MU/drop-in plugins, relevant
metadata and permissions for the exact intended environment. Use an explicitly
authorized disposable copy of that environment to prove the supported repair,
core revisions/hooks, external verified content backup, conditional conflicts,
post-write verification, uncertain outcomes and separately approved restoration.
Custom plugins/builders need their own compatibility work; they stay unsupported
until that work is justified and approved within scope.

The current application accepts only `.test` mutation origins. A separate production candidate is now implemented behind independent private
operator and WordPress-side gates; see `PRODUCTION_AUTOFIX.md`. It is not activated
or approved for any real environment. The legacy test route remains `.test` only. Do not bypass
that restriction, turn a readiness boolean into authority or enable the companion
in production merely because offline tests pass. Product-wide production AutoFix
live readiness therefore remains incomplete; the conservative profile and its tests
are complete development evidence for this bounded candidate only.


## Repair admission and interrupted operations

Only unambiguous observed 404/410 destinations are offered for link replacement.
401/403, 429, 5xx, mixed failures and missing evidence do not establish a content
repair; they remain monitoring findings. Even 404/410 does not establish why the
server returned that status. Scan evidence expires after fifteen minutes and is
checked at proposal and approval. Replacement availability is checked again at
approval; only a complete nonempty HTTP 200 HTML response passes the default probe.
Reachability is not proof of relevance; exact human review remains mandatory.

Href replacement ignores anchors inside inert/raw-text contexts and rejects
document base/plaintext contexts that would invalidate URL interpretation. A
read-only recovery review never reclassifies matching content as verified apply
or rollback. Details and crash boundaries are recorded in the internal audit.
