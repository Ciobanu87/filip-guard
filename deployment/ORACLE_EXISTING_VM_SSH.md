# Existing Oracle VM: pinned read-only SSH verification

This procedure never creates/replaces/resizes a VM, volume, IP or network rule.
It does not install packages, enable an application, change authentication or
approve a bill. No production API or encryption key is generated.

When the Work environment cannot route SSH and the owner's private key exists
only in Oracle Cloud Shell, the existing GitHub Actions route is an alternative.
The owner must explicitly grant that runner SSH access; the private key must
never be posted in chat, repository files, logs, screenshots or artifacts.

## Owner-only secure setup (no shell commands)

In repository Settings > Environments, create/select `filip-guard-oracle`.
Restrict its deployment branches to **filip-guard-development only**. Add these
three environment secrets using GitHub's private secret-value fields:

| Secret | Value |
| --- | --- |
| `FG_OCI_HOST` | Existing VM's public IP address |
| `FG_OCI_HOST_ED25519_SHA256` | Exact `SHA256:...` ED25519 host fingerprint from Oracle Console history |
| `FG_OCI_SSH_PRIVATE_KEY` | Full existing private-key file, including BEGIN/END lines |

The SSH private key grants the runner the existing `opc` account's privileges,
so limit it to this environment and the authorized development branch. It is not
an Oracle API key and cannot establish account billing/free-tier eligibility.
Do not replace Backblaze secrets. Keep the original SSH key independently retained.
A passphrase-protected key is not unlocked by this noninteractive probe; never
remove its passphrase merely to make a check pass.

Only after secure setup does an authorized developer change the nonsecret marker
`deployment/oracle-ssh-preflight-request.json` on the development branch.
The new workflow uses an explicit push/path filter, not main, a PR trigger or cron.
Creating this workflow does not itself connect to Oracle. No marker is supplied
until the owner authorizes the runner's access and confirms setup.

## Identity before credentials

The probe obtains only the ED25519 public host key, computes SHA-256 and compares
it with the trusted out-of-band Console fingerprint. A mismatch, missing key or
network error stops before the SSH private key is used. A scanned key alone is
not trusted. Authentication uses a private temporary known-hosts file,
`StrictHostKeyChecking=yes`, explicit ED25519, one explicit identity and no
password/agent fallback. Temporary key files are private and removed on exit.

After authentication, one fixed read-only command checks ARM architecture and
selected effective sshd security settings. Raw remote text, host IP, fingerprints,
private keys and host identifiers are not logged or archived. Output consists of
allowlisted boolean checks only. Nothing is silently hardened or changed; any
required security change needs separate review with rollback/lockout prevention.
This is a network- and credential-dependent check, not validated by local mocks.

## Always Free is a separate account-level check

The documented A1 allowance and aggregate boot/block volume pool apply in the
account's home region. Check all existing resources and monthly usage, image
eligibility, storage size/performance tier and actual billing before asserting
zero cost. A 1 OCPU / 6 GB VM alone does not establish that the whole tenancy is
within its allowance. A filesystem size, running Linux or successful SSH cannot
validate the boot volume's account-level price or the quoted cost estimate.
The probe always reports `always_free_billing_verified: false`.

Official references checked 2026-11-26:
- https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm
- https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments
