# Existing Groq key: owner-only SSH entry, held application

Owner screenshot received 2026-11-27 shows Personal / Default Project, Billing,
Plans, $0, Current Plan. This is accepted evidence for that organization at that
time. It does not establish which organization an untested candidate key belongs
to, restore the missing usage ledger or authorize any inference.

The development preparation workflow installs only this public helper code as
root-owned mode 0700 `/usr/local/sbin/filip-guard-set-groq-key`. No Groq secret is
provided to GitHub, Actions, this conversation or an artifact. It creates no
public listener, tunnel endpoint or cloud resource and performs no provider call.

The owner must already have their own trusted interactive SSH connection as
`opc` to the existing server, with the established host identity verified. Do not
change or bypass host-key checking. From that SSH terminal run only:

```sh
sudo /usr/local/sbin/filip-guard-set-groq-key
```

Enter the existing candidate key twice at the hidden prompts, never as a command
argument, shell variable, shell command, redirected input or chat message. The
helper refuses noninteractive stdin/stderr and refuses getpass echo fallback.
Use a private terminal without session/input recording. No key is printed,
hashed into a report or sent to a subprocess, GitHub or Groq. No key is generated.

A structurally valid matching candidate is stored only on this existing Oracle
host at `/etc/filip-guard/secrets/groq-api-key`, app-owned mode 0400 under the
root-controlled secret directory. Only its path is added to root-private mode
0600 `runtime.env`. Existing keys/references are never replaced. Incomplete
configuration commit removes the newly created candidate. AI and backup flags
must already be zero and the UI/worker/timer inactive; they remain held. No free
plan flag, AI budget, ledger, authorization or service is enabled by this helper.

Success means **candidate stored**, not API validity or proof it is the named
key. A `gsk_` prefix alone cannot prove identity, validity, permissions or its
organization/plan. Do not retry the nine accepted cases. Separate reconciliation
and permission are still required before any eventual provider validation.

If the owner has no independent SSH client/session, this direct-entry route
cannot be completed solely through Actions: Actions must not receive this key.
Do not substitute a public HTTP form or shared clipboard. Establish the owner's
trusted SSH access first; never ask for a private SSH key in chat.
