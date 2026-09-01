# TASK-023 OS-provisioning runbook — commands a human with root/sudo runs

This is the companion document to `ops/reviews/cto-task023-architecture.md`
(twice reviewed by Red Team; PASS on re-verification,
`ops/reviews/red-team-task023-reverification.md`) and this task's own
Development handoff. Every command below is real, copy-pasteable, and
was **not executed** during Development — the harness's own safety
classifier will not let an autonomous agent run `useradd`, edit sudoers,
or start a persistent privileged daemon without a human directly
approving each one in the moment (see the Development handoff for the
full account of why this task was split this way). All product/application
code this runbook depends on (`ops/control-center/opsdb_broker.py`,
`ops/control-center/egress_proxy.py`, `ops/control-center/egress_relay.py`,
`ops/db/opsdb.py`'s broker client mode, `ops/control-center/
launch_developer_sandboxed.sh`, `ops/control-center/
launch_developer_session.py`) is already written, syntax-checked, and
(where it has no OS dependency) tested — see the Development handoff for
exactly what was and wasn't exercised.

Follow this top to bottom, in order. Every command assumes the repo lives
at `/home/user/AI-Pipeline` (adjust every literal path below if that's not
true on the real deployment host) and that you are running as `root` or
via `sudo`.

---

## 0. Before you start: re-run the feasibility spike on THIS host

`ops/reviews/cto-task023-architecture.md` §1 ran its bubblewrap/namespace
feasibility tests in the Development *container*, not necessarily the
real production host — §7's own sequencing makes this DevOps' required,
independent gate before anything below proceeds. Re-run, verbatim, on the
actual deployment host:

```bash
# 1. Confirm bubblewrap is present (read-only check — safe to run any time)
which bwrap && bwrap --version

# 2. Unprivileged user-namespace creation — the specific case the
#    architecture doc flagged as needing direct verification, not assumed
su -s /bin/sh nobody -c \
  'bwrap --ro-bind / / --proc /proc --dev /dev --unshare-all --die-with-parent /bin/echo unpriv-bwrap-ok'
# expect: "unpriv-bwrap-ok", exit 0

# 3. Network isolation
bwrap --ro-bind / / --proc /proc --dev /dev --unshare-all --die-with-parent \
  curl -m 5 http://example.com
# expect: curl fails to resolve/connect (no interface reachable)

# 4. PID-namespace containment (Red Team's re-verification Finding 2 test)
nohup sleep 120 >/dev/null 2>&1 & echo "host pid: $!"
bwrap --ro-bind / / --proc /proc --dev /dev --unshare-all --die-with-parent \
  /bin/sh -c 'ps aux; echo ---; ls /proc | head'
# expect: the host PID from the line above does NOT appear anywhere

# 5. THE WRAPPER'S OWN BIND SET CAN ACTUALLY EXEC (Code Review R1 — this
#    exact check is why R1 existed: tests 1-4 all use `--ro-bind / /`,
#    which the real wrapper deliberately does NOT, so they never caught a
#    bind set that could not exec anything at all).
bwrap --unshare-all --die-with-parent --clearenv \
  --proc /proc --dev /dev --tmpfs /tmp \
  --ro-bind /usr /usr --ro-bind /opt/claude-code /opt/claude-code \
  --symlink usr/bin /bin --symlink usr/sbin /sbin \
  --symlink usr/lib /lib --symlink usr/lib64 /lib64 \
  --ro-bind /etc/alternatives /etc/alternatives --ro-bind /etc/ssl /etc/ssl \
  --ro-bind /etc/passwd /etc/passwd --ro-bind /etc/group /etc/group \
  --setenv PATH /usr/local/bin:/usr/bin:/bin --setenv HOME /tmp \
  -- /usr/bin/timeout --signal=KILL 30 /opt/claude-code/bin/claude --version
# expect: the claude version string, exit 0. (Adjust the --symlink lines if
# this host has REAL /bin,/lib,/lib64 directories instead of symlinks into
# /usr — the wrapper detects that itself; this hand-run check does not.)
```

If any of these differ from `ops/reviews/cto-task023-architecture.md` §1's
recorded results, STOP and take it back to CTO/Red Team before continuing
— do not proceed on an unverified assumption that this host behaves the
same as the Development container.

---

## 1. Create the dedicated `ai-developer` OS account

Per §2.3 of the architecture doc: system account, no login shell, no home
directory, owns nothing sensitive by default.

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ai-developer
```

Verify:

```bash
id ai-developer
# expect: uid=<n>(ai-developer) gid=<n>(ai-developer) groups=<n>(ai-developer)
getent passwd ai-developer | grep -q '/usr/sbin/nologin$' && echo "no-login shell: OK"
```

---

## 2. Create the two shared groups

Per §4.4: `ai-pipeline-dev` (Founder's own user + `ai-developer`, shared
read-write access to a Developer task's own git worktree) and
`ai-pipeline-db` (the broker's own account + `ai-developer`, shared access
to the broker's Unix socket only — never the database file itself, which
only the broker process ever opens directly).

```bash
sudo groupadd ai-pipeline-dev
sudo groupadd ai-pipeline-db

# Replace <founder-user> with the actual login the Founder/CTO/DevOps use
# interactively on this host.
sudo usermod -aG ai-pipeline-dev <founder-user>
sudo usermod -aG ai-pipeline-dev ai-developer
sudo usermod -aG ai-pipeline-db  ai-developer
# <founder-user> also needs ai-pipeline-db if launch_developer_session.py
# runs under that same account (Option A below) — it does not need it if
# the broker runs under a separate ai-pipeline-broker account (Option B).
sudo usermod -aG ai-pipeline-db  <founder-user>
```

Verify:

```bash
getent group ai-pipeline-dev ai-pipeline-db
```

**Per-task worktree ownership** (done at task-launch time, not once —
`launch_developer_session.py` does not currently automate this; a human
or a follow-up DevOps change should wire this into the worktree-creation
step before this ships for real):

```bash
# For each new task worktree created for a sandboxed Developer session:
sudo chgrp -R ai-pipeline-dev /path/to/that/worktree
sudo chmod -R g+rwX /path/to/that/worktree
# setgid bit so new files Developer creates inherit the group, not
# ai-developer's own primary group
sudo find /path/to/that/worktree -type d -exec chmod g+s {} +
```

---

## 3. The one narrowly-scoped sudoers line

Per §4.4: NOPASSWD for exactly the fixed wrapper script path, nothing
broader — never `NOPASSWD: ALL`.

```bash
sudo visudo -f /etc/sudoers.d/ai-pipeline-developer-sandbox
```

Put exactly this one line in that file (replace `<founder-user>` with the
real account `launch_developer_session.py` runs under):

```
<founder-user> ALL=(ai-developer) NOPASSWD:SETENV: /home/user/AI-Pipeline/ops/control-center/launch_developer_sandboxed.sh
```

The `SETENV:` tag (B2.1, Code Review) is REQUIRED and is why
`launch_developer_session.py` can call `sudo
--preserve-env=OPSDB_BROKER_SOCKET,OPSDB_EGRESS_SOCKET`: without it, `sudo`'s
`env_reset` strips both, the wrapper cannot find the broker/egress sockets,
and every launch fails. `SETENV:` here permits ONLY the two non-secret
socket PATHS the launcher explicitly names via `--preserve-env` — it does
NOT allow a blanket environment passthrough, and the broker capability
TOKEN never travels this way at all (it is passed as a group-readable
`0640` file argument, keeping it out of the process table — see the
wrapper's own header and `launch_developer_session.py`).

Set correct permissions (visudo does this automatically if you edited via
`visudo -f`; if you created the file another way, fix it explicitly):

```bash
sudo chmod 0440 /etc/sudoers.d/ai-pipeline-developer-sandbox
sudo visudo -c   # validates the whole sudoers configuration, not just this file
```

Verify the exact, narrow scope (should show nothing broader than the one
line above):

```bash
sudo -l -U <founder-user> | grep ai-developer
```

**Why this is safe as written**: sudoers matches on the exact executable
path with no wildcard, no arguments restricted (arguments are safe to
leave unrestricted here because `launch_developer_sandboxed.sh` itself
never re-interprets its arguments as shell syntax — see that script's own
header comment) and no `ALL=(ALL)` anywhere in this line. `<founder-user>`
gains the ability to run exactly one fixed script as exactly one
low-privilege account — nothing else.

---

## 4. Confirm bubblewrap is installed

Already checked in step 0's spike, but as a standalone check (this
project's own feasibility spike already confirmed `bubblewrap 0.9.0-1ubuntu0.1`
was present with no custom build needed on the Development container —
confirm the same package is present on the real host):

```bash
which bwrap
bwrap --version
# if missing:
sudo apt-get install -y bubblewrap
```

---

## 5. Create the broker's runtime directory and socket path

```bash
sudo mkdir -p /run/ai-pipeline
sudo chgrp ai-pipeline-db /run/ai-pipeline
sudo chmod 2770 /run/ai-pipeline   # setgid so the socket file created inside inherits the group
```

Both the opsdb broker socket (`/run/ai-pipeline/opsdb.sock`) and the egress
proxy socket (`/run/ai-pipeline/egress.sock`) live in this one directory,
group `ai-pipeline-db`, so `ai-developer` (a group member) can reach both
bind-mounted sockets and nothing else.

Note: `/run` is typically a tmpfs that's recreated on reboot — both the
`opsdb-broker.service` and `egress-proxy.service` units set
`RuntimeDirectory=ai-pipeline` and handle this automatically; if you start
either proxy some other way, re-run this step after every reboot.

**What systemd actually does to this directory, and why both units pin
`Group=ai-pipeline-db`** (Code Review non-blocking item): on start, systemd
creates `/run/ai-pipeline` and **chowns it to that unit's `User=`/`Group=`**,
overriding the manual `chgrp`/`chmod` above. If either unit ran with, say,
the Founder's own primary group, the directory would become `0770
<founder>:<founder-group>` and `ai-developer` could not traverse it to reach
*either* socket. Both shipped units therefore set `Group=ai-pipeline-db`
(not a placeholder — only `User=` is), and both set
`RuntimeDirectoryPreserve=yes`, without which stopping either unit deletes
the shared directory out from under the other one, taking its socket with
it. Do not "simplify" either setting away.

---

## 6. Start `opsdb_broker.py` as a real, persistent service

**Preferred: systemd.** A ready-to-use unit file is already written —
`ops/control-center/opsdb-broker.service`.

**REQUIRED EDIT before it will start (B2.3, Code Review):** the shipped
unit has intentionally-invalid `User=`/`Group=` PLACEHOLDERS, so systemd
refuses to start it until you set them — it will NEVER silently run as root
(running as root breaks registration, because
`opsdb_broker._default_trusted_uids()` would become `{0}` and refuse the
Founder-UID launcher's `register_session`). Pick one:

- **Option A (simplest):** set `User=` to the Founder's own account — the
  same account `launch_developer_session.py` runs as — and leave
  `OPSDB_BROKER_TRUSTED_UIDS` unset (it defaults to the broker's own UID,
  which is then also the launcher's UID: registration just works, no extra
  config). Leave `Group=ai-pipeline-db` as shipped (see step 5 for why it is
  pinned rather than set to the Founder's primary group); the Founder's
  account still opens the database as its owner, and systemd grants the unit
  all of that account's supplementary groups as usual.
- **Option B (dedicated account):** set `User=ai-pipeline-broker`, keep
  `Group=ai-pipeline-db`, and uncomment
  `Environment=OPSDB_BROKER_TRUSTED_UIDS=<founder numeric UID>` (from `id -u
  <founder-user>`) so the launcher — a different UID than the broker — can
  still register.

```bash
sudo cp /home/user/AI-Pipeline/ops/control-center/opsdb-broker.service \
  /etc/systemd/system/opsdb-broker.service
sudo $EDITOR /etc/systemd/system/opsdb-broker.service   # set User=/Group= (see above) — REQUIRED
sudo systemctl daemon-reload
sudo systemctl enable --now opsdb-broker.service
sudo systemctl status opsdb-broker.service
```

Verify it's actually listening:

```bash
sudo -u <founder-user> test -S /run/ai-pipeline/opsdb.sock && echo "socket present"
ls -la /run/ai-pipeline/opsdb.sock
# expect: srw-rw---- ... <founder-user or ai-pipeline-broker> ai-pipeline-db ... opsdb.sock
```

If you chose **Option B** (a separate `ai-pipeline-broker` account, so the
Founder's own interactive login is not also the account `opsdb_broker.py`
runs as), create it first, then set the unit's `User=`/`Group=` and
`OPSDB_BROKER_TRUSTED_UIDS` as described in the REQUIRED-EDIT box above:

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ai-pipeline-broker
sudo usermod -aG ai-pipeline-db ai-pipeline-broker
```

---

## 6b. Start `egress_proxy.py` — the model-API egress carve-out (B3)

The sandbox keeps `--unshare-all` (no network), and reaches the model API
through exactly ONE bind-mounted Unix socket served by a host-side,
allowlisting HTTP-CONNECT proxy (`ops/control-center/egress_proxy.py`,
architecture doc Addendum B3). This proxy runs as a trusted account —
NEVER `ai-developer` — with a host-owned allowlist config file that is NOT
bind-mounted into the sandbox.

First, write the allowlist config (owned by the trusted account or root,
`0644` — i.e. root-writable only, and world-READABLE on the host like most
of `/etc`; the security property that matters is that it is **not
bind-mounted into the sandbox**, so it is neither readable nor widenable
from *inside* the sandbox, which is what Red Team verified as property #5.
`launch_developer_sandboxed.sh` binds only an enumerated handful of `/etc`
paths — `/etc/alternatives`, `/etc/ssl`, `/etc/pki`, `/etc/passwd`,
`/etc/group` — never `/etc` itself, and it refuses to start if that list is
ever edited into something that would expose `/etc/ai-pipeline`. Verified
live during Development: with this file present on the host, `ls
/etc/ai-pipeline` from inside the real sandbox reports it does not exist.
If you prefer it unreadable on the host as well, `chmod 0640` and `chgrp`
it to the egress proxy's own account — the proxy is the only process that
reads it):

```bash
sudo mkdir -p /etc/ai-pipeline
sudo tee /etc/ai-pipeline/egress-allowlist.json >/dev/null <<'JSON'
{
  "allow": ["api.anthropic.com:443"],
  "upstream_proxy": null
}
JSON
sudo chmod 0644 /etc/ai-pipeline/egress-allowlist.json
```

- `allow` is an exact list of `hostname:port`. `api.anthropic.com:443` is
  the model API. Deliberately narrower than the ambient environment's own
  `NO_PROXY`: package registries (`registry.npmjs.org`, `pypi.org`,
  `files.pythonhosted.org`) are NOT listed and are therefore denied — the
  "no ad-hoc `pip install`" property is preserved, not reopened.
- `upstream_proxy` (optional): set it to this environment's own agent
  egress proxy `host:port` (see `HTTPS_PROXY` / `/root/.ccr/README.md`) if
  outbound HTTPS on this host must be chained through it; the egress proxy
  then issues its own CONNECT to that upstream for allowlisted destinations.
  Leave `null` for a host with direct outbound to the API.

Then install the unit (same REQUIRED `User=` edit discipline as the broker —
an intentionally-invalid placeholder, fails loud with `217/USER`, never
root, never `ai-developer`; `Group=ai-pipeline-db` is already correct and
should be left alone, see step 5).

Note on the unit's own sandboxing: it sets `ProtectSystem=strict`
(everything read-only except the explicit `ReadWritePaths=`) but
`ProtectHome=false`, matching `opsdb-broker.service`. `ProtectHome=true`
would replace `/home` with an empty tmpfs inside the unit's mount
namespace, and since both `WorkingDirectory=` and `ExecStart=` live under
`/home/user/AI-Pipeline`, systemd would fail the unit at `200/CHDIR` and
python would not find the script (reproduced during Development). If you
relocate the repo outside `/home`, `ProtectHome=true` becomes correct
again — change both units together.

```bash
sudo cp /home/user/AI-Pipeline/ops/control-center/egress-proxy.service \
  /etc/systemd/system/egress-proxy.service
sudo $EDITOR /etc/systemd/system/egress-proxy.service   # set User=/Group= to a trusted account — REQUIRED
sudo systemctl daemon-reload
sudo systemctl enable --now egress-proxy.service
sudo systemctl status egress-proxy.service
```

Verify the socket exists and is group-usable by `ai-developer` (`660`,
group `ai-pipeline-db`):

```bash
ls -la /run/ai-pipeline/egress.sock
# expect: srw-rw---- ... <trusted-account> ai-pipeline-db ... egress.sock
```

**Manual-start alternative** (either proxy — no systemd, quick trial only,
no restart-on-failure/boot-persistence; run as a trusted non-root account,
never `ai-developer`):

```bash
sudo -u <founder-user> nohup python3 /home/user/AI-Pipeline/ops/control-center/opsdb_broker.py \
  >> /var/log/opsdb-broker.log 2>&1 &
sudo -u <founder-user> EGRESS_PROXY_CONFIG_PATH=/etc/ai-pipeline/egress-allowlist.json \
  nohup python3 /home/user/AI-Pipeline/ops/control-center/egress_proxy.py \
  >> /var/log/egress-proxy.log 2>&1 &
```

---

## 7. End-to-end smoke check (once every step above is done)

This is a real, minimal exercise of the full chain — NOT the full live QA
charter (§7 sequencing item 7 of the architecture doc — that remains QA's
job next, out of scope for this runbook and for TASK-023's own
Development pass).

```bash
cd /home/user/AI-Pipeline
sudo -u <founder-user> python3 ops/control-center/launch_developer_session.py \
  --task-id <a real, existing task id currently IN_DEVELOPMENT> \
  --worktree-path /home/user/AI-Pipeline \
  --timeout-s 60
```

Expect: the sandboxed `claude --agent developer` process starts, its
stream-json output appears live on your terminal, and — if the task
prompt asks it to do so — a real `handoff`/`task-status` call succeeds
through the broker, AND the model call itself succeeds via the egress
proxy. If this fails, check (in order): the broker's own `systemctl status
opsdb-broker.service` / journal output; the egress proxy's `systemctl
status egress-proxy.service` / journal (a model call that hangs or errors
usually means the egress proxy is down, or `api.anthropic.com:443` is
missing from `/etc/ai-pipeline/egress-allowlist.json`, or `upstream_proxy`
is needed on this host but unset); that both `/run/ai-pipeline/opsdb.sock`
and `/run/ai-pipeline/egress.sock` exist and are group-readable by
`ai-developer`; that the sudoers line from step 3 is exactly right and
carries the `SETENV:` tag (`sudo -l -U <founder-user>`); and that the
worktree path is actually group-owned per step 2's per-task chgrp
instructions.

---

## 8. What this runbook deliberately does NOT do

- It does not change the default Developer-invocation path anywhere in
  this repository — `launch_developer_session.py` is not called by
  anything else yet. Cutting over is a separate, later decision (§7 of the
  architecture doc), gated on this runbook's own step 0 re-verification
  and a live QA charter.
- It does not authorize a broader sudoers rule, an OS account beyond
  `ai-developer` and the trusted proxy account(s) (`ai-pipeline-broker`
  and/or `ai-pipeline-egress`), or any network egress inside the sandbox
  BEYOND the single allowlisted model-API destination class the B3 egress
  proxy permits (§6b). Widening the egress allowlist to anything other than
  the model API host(s) — a package registry, a paste site, any general
  destination — is a new, separately reviewed architecture change, not an
  extension of this runbook. The sandbox itself keeps `--unshare-all`
  (`--unshare-net`): it has no interface/route/DNS, and the ONLY egress is
  the one host-enforced, allowlisting proxy socket.
- `DEVELOPER_MAX_BUDGET_USD` (in `launch_developer_sandboxed.sh`) and the
  wall-clock `--timeout-s` default (in `launch_developer_session.py`) are
  both explicitly flagged in those files as placeholder values needing
  Founder/CTO/Red Team confirmation, not numbers this runbook or
  Development independently authorized.
