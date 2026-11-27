# Owner-controlled independent master-key custody

Prepared operational tooling only. No application service, timer, paid resource,
Groq request, B2 upload or production master is created by installing this tool.
The owner authorized secure generation/install through SSH and encrypted-only
GitHub artifact transfer with retention at most one day; the decryption secret
must remain separate. Plaintext master storage in ChatGPT Library is forbidden.

## Minimum owner-only steps

1. Download `owner-custody.html` and open it locally on the owner's phone, outside
   ChatGPT preview/cloud browser. Generate the 43-character random recovery secret
   using local WebCrypto; save it privately, separately from the encrypted bundle.
   Do not post it or include it in screenshots. No network/storage API is used.
2. In the owner's already verified SSH terminal as `opc`, run:

   ```sh
   sudo /usr/local/sbin/filip-guard-master-custody prepare
   ```

   Paste the secret twice at hidden prompts. No characters/dots appear. No secret
   belongs in argv, shell variables, commands, reports or GitHub. Getpass echo
   fallback, noninteractive input, concurrent preparation, existing key versions,
   mismatched settings and active/enabled services are refused. Core dumps are
   disabled. No new master is generated before both inputs pass validation.
3. The agent retrieves only the encrypted custody bundle through pinned SSH and
   places it in an encrypted-only GitHub artifact, retention `1` day. The raw
   master and recovery secret never enter Actions, logs, repository or Library.
   Download the bundle onto the owner's device, keep it independently of Oracle
   and the content bucket, and keep another protected copy. Keep the secret apart.
4. In the LOCAL HTML tool, select the downloaded sealed JSON and enter the secret.
   Confirm independent bundle/secret custody. It decrypts the master in memory,
   then decrypts an actual existing-format application-state backup fixture,
   verifies its SQLite bytes/hash and produces a nonce-bound HMAC proof. It never
   displays or exports the plaintext master. Copy only the verification code.
5. In the same private SSH terminal run:

   ```sh
   sudo /usr/local/sbin/filip-guard-master-custody verify-owner
   ```

   Paste only the 64-character proof at its hidden prompt. Until it matches the
   current bundle and installed key, root custody status stays pending. Repeated
   verification is idempotent. No service or backup authorization is enabled.

These are custody operations, not account sign-in or account-password changes.
The owner must use a private terminal without input/session recording. Secret
memory erasure by Python/JavaScript cannot be guaranteed; close the local tool
and SSH operation after use. No plaintext master is a user-facing artifact.

## Cryptographic and operational checks

- Production master: OS CSPRNG, 32 bytes, app-owned mode `0400`, private `0700`
  versioned keyring. Existing versions/settings are never replaced or rotated.
- Owner secret: 32 random bytes encoded base64url, generated on the owner device;
  it is used only for this encrypted-custody purpose, not as an API/SSH key.
- Envelope: AES-256-GCM, random 16-byte salt/12-byte nonce, PBKDF2-HMAC-SHA256
  600,000 iterations; key version/deployment/KDF parameters authenticated as AAD.
  The iteration setting follows the currently published OWASP minimum for that
  PBKDF2 variant; this is not a claim of FIPS certification.
- Backup fixture: exact existing `application_state_backup` format, independent
  HKDF-SHA256 application-state subkey and AES-GCM, synthetic SQLite only. Python
  checks SQLite integrity during export/readback. Node WebCrypto independently
  decrypts and produces the same proof in tests; wrong secrets, changed context,
  altered master ciphertext and corrupted backup ciphertext fail closed.
- Root-only pending record contains verification material that is never exported.
  Bundle SHA-256 and random encrypted challenge bind the owner proof to this
  particular encrypted file. Source/fixture files and the full HTML CSP prevent
  network connections; localStorage/sessionStorage are never used.
- Installation is separate from generation. No background startup/import creates
  a master. Export never returns raw-key material and accepts only sealed schema.
  Failed pre-commit preparation removes only newly created unused key/bundle files;
  successful preparation is retained and never silently regenerated.
- Independent recovery is NOT complete until the owner actually downloads,
  retains and locally decrypts the bundle and returns its proof. An on-server
  round trip is not independent custody. Full real-state B2 recovery remains a
  separate bounded validation after zero-spend account checks, not this fixture.

Keep this public tool and format guide independently with the encrypted bundle.
For a real future host loss, the included `recover_owner_master.py` works
without the original host or database. On a new trusted private recovery host,
create an owner-controlled 0700 destination directory and run the script with
`--bundle SEALED_JSON --destination NEW_PRIVATE_KEY_FILE
--confirm-new-trusted-recovery-host`. The secret is prompted privately; an
existing destination is refused; only a mode-0400 key mount is created and no
key is printed. Use that private mount with the existing application recovery
CLI and the separately retained manifests/archives. Never upload its plaintext
output to ChatGPT Library or GitHub. The HTML fixture check
proves key/format recovery; it does not materialize arbitrary live customer data
or perform full WordPress restoration. Never delete old retained key versions.

References reviewed 2026-11-27:
https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
https://www.w3.org/TR/WebCryptoAPI/
