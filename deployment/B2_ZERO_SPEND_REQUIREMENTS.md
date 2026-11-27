# Backblaze account verification required before any real backup activity

The mounted existing credentials/adapter and earlier synthetic B2 recovery are
already completed evidence; do not repeat them without a new technical reason.
Current account-wide free capacity/caps still require authenticated owner-account
inspection. Public pricing is not proof of the state of this particular account.

Reviewed official documentation on 2026-11-27:

- First 10 GB storage free; downloads generally free up to 3x monthly average
  storage. ABC transactions are shown as free; the pricing overview qualifies
  this for pay-as-you-go customers. Do not upgrade/add payment to obtain a tier.
- Caps are dollar limits after free allowances. Clear `No Cap` and set every
  available storage/download/transaction charge cap to `$0`. Confirm the saved
  UI state, not just an entered form. Updates may take up to ten minutes.
- Class D Event Notification outbound calls cannot be protected by those caps.
  Verify no event-notification configuration is active for this workload and no
  other account activity defeats the account-wide zero-spend requirement.
- Verify current usage/account-wide free space, bucket privacy, all versions and
  unfinished uploads as applicable. Retain a conservative free-headroom floor
  of 384 MiB for the existing short-lived host approval; do not invent measured
  usage or infer account-wide values from a bucket-scoped API key.
- Verify no charged extra feature, upgrade or payment activation. No new bucket,
  key, service, retention/delete policy or paid resource is needed for this step.
  Never delete owner objects or keys to create free space without authorization.
- Only after the caps are verified effective and custody independently verified:
  authorize one bounded host-state encrypted export/readback/new-destination
  recovery using the existing adapter (one SDK attempt; no automatic retries).
  Keep restore holds, the original AI reservations and all key versions.
- UI/worker/backup service/timer remain disabled and inactive. Even after both
  blockers are validated, obtain the owner's final activation approval before
  writing activation consent or enabling any service/timer.

Do not report current account caps/free headroom as verified until actually seen
in the authenticated account. Preserve account evidence privately; no account
IDs, secret values or private billing exports belong in the repository.

Sources:
https://www.backblaze.com/cloud-storage/pricing
https://www.backblaze.com/cloud-storage/transaction-pricing
https://www.backblaze.com/docs/cloud-storage-data-caps-and-alerts
https://www.backblaze.com/docs/cloud-storage-create-and-manage-caps-and-alerts


## Provider feature gate and one manual recovery validation

A link to the public Event Notifications article is not evidence of an empty rule
list. The bounded native inspection distinguishes a successful list with no
enabled rules from the provider's exact `400 bad_request: API not enabled`
response on the notification-read endpoint. The latter is recorded as an
unavailable notification API, not as a fabricated empty list. It is consistent
with the official reference requiring Support to enable the feature. No Support
enablement, notification write or credential expansion is part of this task.
Unauthorized, restricted-prefix, malformed-parameter and other errors never
satisfy this check. A future enabled feature needs a fresh successful rule read.

The separate manual workflow requires already owner-confirmed saved zero-dollar
caps, verified independent master custody, held/disabled units, no runtime-user
writers, a complete bounded all-version bucket inventory, no unfinished uploads,
and at least eight maximum-size archive slots below the 10 GB free allowance.
It reserves a new private attempt before any write, permits only one existing
format encrypted state upload and two recovery reads, and never retries or
overwrites a prior attempt. The original SQLite files must stay byte-identical.
The downloaded ciphertext is restored into a new private directory with the
existing restore-review hold. This neither initializes missing customer state
nor enables the scheduled backup or any application service. Existing account
activities outside this scoped key remain outside its inspection scope.

The recovery manifest and completion record stay private under the existing
server recovery directory; no private object identifiers or storage totals are
published in repository source or Actions output. Independent key custody was
verified separately on the owner's device. This manual check is SQLite state
recovery, not a claim of a full WordPress or whole-VM restore.
