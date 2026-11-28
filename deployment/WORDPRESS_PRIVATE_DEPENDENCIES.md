# Isolated Oracle WordPress pilot dependency admission

Owner authorization: 28 November 2026, PHP 8.3, mysqli and SQL solely for the
private pilot. No global installation, existing application update, public
service, cloud resource creation, real Groq/SMTP/B2 request or production use.

## Sources and cost check before installation

Official Oracle Linux documentation confirms the PHP 8.3 module stream. The
Oracle Linux 9 public AppStream aarch64 repository lists native PHP CLI/mysqlnd
and MariaDB server packages. The public Oracle yum server is free to use without
a support subscription; MariaDB Community Server is GPLv2. No marketplace image,
ULN subscription, enterprise database or paid support channel is used.

- https://docs.oracle.com/en/operating-systems/oracle-linux/9/relnotes9.6/ol9-features-DynamicProgramming.html
- https://yum.oracle.com/repo/OracleLinux/OL9/appstream/aarch64/
- https://docs.oracle.com/en/operating-systems/oracle-linux/software-management/sfw-mgmt-OLYumServers.html
- https://mariadb.org/about/
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm

Existing 1 OCPU / 6 GB / 47 GB allocation is rechecked via local metadata and
block-device inspection before execution. Previous owner evidence of a Free Tier
account without upgrade and no other allocations remains the account-level
basis; live billing is not polled. No allocation changes are issued.

## Installation boundaries

`dnf --installroot` writes signed dependencies, module state, RPM database,
cache and logs only inside a root-controlled temporary directory. Only the two
explicit public Oracle OL9 ARM64 repositories are enabled. Package GPG checking
uses the existing root-owned Oracle signing keys; TLS validation stays enabled.
Package scriptlets and weak dependencies are disabled. PHP CLI, mysqlnd/mysqli,
mbstring, XML and MariaDB 10.11 server are installed with necessary libraries.
No PHP-FPM, Apache or service start is requested. Any service files supplied as
package dependencies stay inside the temporary installroot.

The unchanged existing application Python environment runs the tests as the
separate existing `nobody` account. Only the disposable WordPress copy receives
the synthetic fixture policy. All SQL/PHP/TLS listeners exist only on loopback
inside an independent network namespace with no external interface or route.
The namespace has no real provider credentials or access to application state.

Private source is the already-tested immutable candidate
`ee593326f89b5db8a1f0700c6a9f18424a36e0e6`, with tar SHA-256
`75dbf433f0859ca93d6d970bd08af27a5280fc06526aa4f202d9f54222320902`.
WordPress 7.1.5 and WP-CLI 2.12.0 use the existing official-source download script
and pinned SHA-256 checks. Untrusted binaries and mismatched downloads stop the
pilot; validation is never bypassed.

Limits: 2 GiB private disk, 5 GiB minimum remaining free space, 820-second overall
controller deadline, bounded individual commands, sampled aggregate descendant
RSS monitoring (2 GiB termination threshold), and unprivileged test process
virtual-memory/file limits. Temporary runtime, database, test credentials and
logs are removed on normal controller exit including handled failures. A host
crash/SIGKILL cannot guarantee Python cleanup; the temporary directory prefix is
explicit for later read-only inspection/authorized cleanup if that occurs.

The pilot compares the host RPM package inventory and four application service
states before/after. These checks prove those boundaries; they do not assert a
full filesystem integrity audit or a live account billing audit. See the actual
run report for results rather than treating this admission design as a pass.
