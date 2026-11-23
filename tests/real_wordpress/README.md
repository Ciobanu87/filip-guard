# Isolated real WordPress integration

This runner creates a fresh WordPress installation and its own randomly named
SQL database. It generates test users, Application Passwords, TLS certificate
and keys, installs only the candidate companion, and binds both web servers to
loopback. Credentials are temporary and not printed. Cleanup drops its database,
stops child processes and deletes its generated files. Never supply an existing
WordPress installation as the clean source.

Requirements: Python project dependencies, PHP 8.3+ with mysqli/phar/iconv/ctype,
WP-CLI, and an isolated disposable MySQL/MariaDB service. CI supplies MySQL 8.0.36.

1. `python tests/real_wordpress/download.py /tmp/fg-wp-fixture`
2. Set `FG_WP_SOURCE=/tmp/fg-wp-fixture/wordpress`,
   `FG_WP_CLI=/tmp/fg-wp-fixture/wp-cli.phar`, `FG_WP_DB_USER`,
   `FG_WP_DB_PASSWORD` and `FG_WP_DB_PORT` for the disposable SQL service.
3. `python tests/real_wordpress/run.py`

Optional `FG_WP_PHP_BINARY` and `FG_WP_PHP_INI` select a portable PHP runtime.
Optional `FG_WP_DB_SERVER`, `FG_WP_DB_BASEDIR`, `FG_WP_DB_DATADIR` start a locally
installed MariaDB server with no Unix socket and TCP bound to 127.0.0.1. Initialize
that isolated data directory beforehand using `mariadb-install-db`. The runner
selects an available local TCP port. Never select a production data directory.

The fixture connector substitutes only the endpoint-to-loopback mapping inside
the test process. The application transport still verifies the local TLS
certificate, hostname, framing, bounds and deadline; production SSRF protections
are not disabled or configured to permit private addresses.

Tests are separate from ordinary offline unit discovery and are reported
separately. Passing this suite does not demonstrate compatibility with arbitrary
WordPress plugins, page builders, multisite or hosting-specific behavior.


The real suite contains 17 tests. It uses a fixture-only MU-plugin to observe real
save hooks and to inject a deterministic title change immediately before the SQL
CAS. Another fixture hook changes a title during save; the companion must report
uncertainty rather than success. No marketplace plugin compatibility is claimed.
Socket wrappers inject lost/truncated replies after the real server has processed
the request, including restoration failures. Native WordPress revisions and
post_updated/save_post/wp_after_insert_post events are checked against the real
WordPress APIs and SQL database.


Configuration-gate cases restart the isolated PHP process and assert the effective
WordPress environment/activation constant through a fixture-only authenticated
diagnostic route. This avoids relying on runtime opcode/stat-cache refresh when
changing boot-time configuration and does not weaken the companion's gate.


The suite additionally creates a second clean WordPress installation on the same
disposable SQL server, with a distinct .test hostname and TLS certificate. It uses
two customer accounts to verify administrative site proof, separate workspaces,
scoped credentials/backups, rejected cross-account approvals and blocked writes
when the simulated external archive is corrupt. Object storage remains simulated.
