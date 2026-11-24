# Isolated service integration, not hosted-provider approval

`python tests/real_infrastructure/run.py` starts a real MinIO S3 server process
and a local aiosmtpd SMTP sink. Supply `FG_MINIO_BINARY` built from official MinIO
commit `9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a`
(`RELEASE.2025-10-15T17-29-55Z`, security fix included). CI builds that source with
its declared Go toolchain. `aiosmtpd==1.4.6` is a test-only dependency. No MinIO
binary or third-party source is vendored or included in the application image.
Official source: https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z

The seven tests cover actual SDK/HTTPS encrypted upload and verified independent
content recovery, object durability across server restart with a fresh client,
customer recovery in a separate process without the original app session/database,
and storage outage blocking repair before writes (WordPress is a local simulator
in this suite; separate CI exercises real WordPress/MySQL). SMTP uses real
STARTTLS, certificate and hostname verification, authentication, local message
receipt and persistent outbox deduplication. An untrusted certificate blocks mail.
A connection cut after DATA acceptance proves the unknown-send quarantine path.

All credentials/keys/certificates/accounts are generated exclusively for isolated
tests, scoped to private temporary directories and loopback sockets. `.test` DNS
is mapped only in the test process/child recovery process, preserving configured
TLS hostname validation. Production transports and gates are unchanged. Fixtures
never send a message beyond the local sink and print no secret values. Only
synthetic encrypted content is stored. `--smtp-only` runs three SMTP checks locally
without MinIO; the four S3 checks are explicitly skipped, never counted as passed.

A server restart test does not validate a cloud provider, geographic independence,
permanent hosting, power-loss durability, an owner's retained production keys,
or real inbox delivery/DKIM/spam handling. Existing deployment adapters require
separate authorized provider configuration and operational validation. This suite
adds reproducible integration evidence without paid accounts or owner credentials.
