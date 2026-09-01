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
<founder-user> ALL=(ai-developer) NOPASSWD: /home/user/AI-Pipeline/ops/control-center/launch_developer_sandboxed.sh
```

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

Note: `/run` is typically a tmpfs that's recreated on reboot — if this
directory isn't managed by the systemd unit's own `RuntimeDirectory=`
directive (see step 6's unit file, which already sets
`RuntimeDirectory=ai-pipeline` and handles this automatically), re-run
this step after every reboot, or prefer the systemd-managed path below.

---

## 6. Start `opsdb_broker.py` as a real, persistent service

**Preferred: systemd.** A ready-to-use unit file is already written —
`ops/control-center/opsdb-broker.service`. It defaults to running the
broker as the same account `launch_developer_session.py` runs under (the
Founder's own user) — see that file's own comments for the alternative
"Option B" (a separate, dedicated `ai-pipeline-broker` system account) and
what changes if you choose it.

```bash
sudo cp /home/user/AI-Pipeline/ops/control-center/opsdb-broker.service \
  /etc/systemd/system/opsdb-broker.service
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

**Option B — separate `ai-pipeline-broker` account** (if the Founder's
own interactive login should not also be the account
`opsdb_broker.py` runs as):

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin ai-pipeline-broker
sudo usermod -aG ai-pipeline-db ai-pipeline-broker
```

Then edit `/etc/systemd/system/opsdb-broker.service`, uncomment the
`User=ai-pipeline-broker` / `Group=ai-pipeline-db` lines, and set
`Environment=OPSDB_BROKER_TRUSTED_UIDS=<founder-user's numeric UID>`
(look it up via `id -u <founder-user>`) so `launch_developer_session.py`
— still running as the Founder's own account — remains able to call
`register_session`/`end_session` even though it's no longer the same
account the broker itself runs as (`opsdb_broker.py`'s own
`_default_trusted_uids()` reads this exact environment variable — see
that function's docstring).

**Manual-start alternative** (no systemd — e.g. a container init or a
plain `nohup`, for a quick trial run only, not recommended for real
production use since it has no restart-on-failure/boot-persistence):

```bash
sudo -u <founder-user> nohup python3 /home/user/AI-Pipeline/ops/control-center/opsdb_broker.py \
  >> /var/log/opsdb-broker.log 2>&1 &
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
through the broker. If this fails, check (in order): the broker's own
`systemctl status opsdb-broker.service` / journal output; that
`/run/ai-pipeline/opsdb.sock` exists and is group-readable by
`ai-developer`; that the sudoers line from step 3 is exactly right
(`sudo -l -U <founder-user>`); and that the worktree path is actually
group-owned per step 2's per-task chgrp instructions.

---

## 8. What this runbook deliberately does NOT do

- It does not change the default Developer-invocation path anywhere in
  this repository — `launch_developer_session.py` is not called by
  anything else yet. Cutting over is a separate, later decision (§7 of the
  architecture doc), gated on this runbook's own step 0 re-verification
  and a live QA charter.
- It does not authorize a broader sudoers rule, a second OS account beyond
  `ai-developer` (and, optionally, `ai-pipeline-broker`), or any network
  egress inside the sandbox. Any of those would be a new, separately
  reviewed architecture change, not an extension of this runbook.
- `DEVELOPER_MAX_BUDGET_USD` (in `launch_developer_sandboxed.sh`) and the
  wall-clock `--timeout-s` default (in `launch_developer_session.py`) are
  both explicitly flagged in those files as placeholder values needing
  Founder/CTO/Red Team confirmation, not numbers this runbook or
  Development independently authorized.
