#!/usr/bin/env bash
# ops/control-center/launch_developer_sandboxed.sh — TASK-023
# (ops/reviews/cto-task023-architecture.md §2.3/§4.4/§7 item 3, plus the
# Addendum's B2/B3 dispositions).
#
# The fixed, reviewed, non-parameterized-in-shell-syntax wrapper that
# actually builds and execs `bwrap ... -- claude --agent developer ...`.
# This is the exact sudoers NOPASSWD target
# (ops/reviews/task023-os-provisioning-runbook.md) — its own path is what
# the one narrowly-scoped sudoers line names, nothing broader.
#
# NOT EXECUTED as part of TASK-023's Development pass. It depends on the
# `ai-developer` account, the `ai-pipeline-dev`/`ai-pipeline-db` groups,
# the running opsdb_broker.py AND egress_proxy.py — none of which exist yet
# in this environment. See ops/reviews/task023-os-provisioning-runbook.md
# for how a human with root/sudo brings all of that up.
#
# WHY THIS SCRIPT IS SAFE TO CALL FROM A SUDOERS NOPASSWD LINE: every
# argument this script receives is used ONLY as literal argv elements in
# an exec'd array (bwrap's own argv, then the relay's argv, then claude's
# own argv nested after `--`) — never passed through `sh -c`, `eval`, or
# any other shell-re-interpretation step. Task/prompt CONTENT is passed as
# DATA (a file path this script reads with `$(<file)`, never a shell string
# built by concatenating untrusted content into a command line) — per the
# architecture doc's own explicit requirement ("task content is passed as
# data, not spliced into shell syntax", §4.1 step 3). The broker token is
# likewise read from a file (B2.1: keeps the capability token out of the
# process table and /proc/<pid>/environ, and survives `sudo`'s env_reset).
# set -euo pipefail and IFS hardening below exist so an unexpected
# empty/missing argument fails loudly instead of silently expanding.
#
# Usage:
#   launch_developer_sandboxed.sh <worktree-path> <prompt-file-path> \
#                                 <token-file-path> <wallclock-seconds>
#
#   <worktree-path>    absolute path to this task's dedicated git worktree
#                       (§4.4 — bind-mounted read-write, owned via the
#                       shared ai-pipeline-dev group).
#   <prompt-file-path>  absolute path to a file (inside the worktree,
#                       group-readable by ai-developer) containing the full
#                       assembled task transcript — written by
#                       launch_developer_session.py BEFORE this script runs.
#   <token-file-path>   absolute path to a 0640 group-readable file whose
#                       sole contents are this session's broker token
#                       (B2.1 — passed as data, not an env var, so `sudo`'s
#                       env_reset can't strip it and it never hits the
#                       process table).
#   <wallclock-seconds>  positive integer wall-clock ceiling; enforced
#                       INSIDE the sandbox by `timeout --signal=KILL`
#                       running as ai-developer against its own process
#                       tree (B2.4 — the killer already has permission,
#                       unlike the Founder-UID launcher's cross-UID killpg).
#
#   Environment (set by launch_developer_session.py, preserved across
#   `sudo` via `--preserve-env=OPSDB_BROKER_SOCKET,OPSDB_EGRESS_SOCKET`
#   with the sudoers SETENV: tag — non-secret socket PATHS only, never the
#   token; re-asserted into the sandbox below via --setenv):
#     OPSDB_BROKER_SOCKET   the opsdb broker's fixed socket path
#     OPSDB_EGRESS_SOCKET   the host-side egress proxy's fixed socket path
#                           (B3 — the sandbox's ONLY path to the model API)

set -euo pipefail
IFS=$'\n\t'

if [ "$#" -ne 4 ]; then
  echo "usage: $0 <worktree-path> <prompt-file-path> <token-file-path> <wallclock-seconds>" >&2
  exit 64  # EX_USAGE
fi

WORKTREE_PATH="$1"
PROMPT_FILE_PATH="$2"
TOKEN_FILE_PATH="$3"
WALLCLOCK_S="$4"

if [ ! -d "$WORKTREE_PATH" ]; then
  echo "error: worktree path does not exist or is not a directory: $WORKTREE_PATH" >&2
  exit 1
fi
if [ ! -f "$PROMPT_FILE_PATH" ]; then
  echo "error: prompt file does not exist: $PROMPT_FILE_PATH" >&2
  exit 1
fi
if [ ! -r "$TOKEN_FILE_PATH" ]; then
  echo "error: token file does not exist or is not readable: $TOKEN_FILE_PATH" >&2
  echo "(launch_developer_session.py writes it 0640, group ai-pipeline-dev — see the runbook)" >&2
  exit 1
fi
case "$WALLCLOCK_S" in
  ''|*[!0-9]*)
    echo "error: wallclock-seconds must be a positive integer, got: $WALLCLOCK_S" >&2
    exit 64 ;;
esac
if [ "$WALLCLOCK_S" -lt 1 ]; then
  echo "error: wallclock-seconds must be >= 1, got: $WALLCLOCK_S" >&2
  exit 64
fi

: "${OPSDB_BROKER_SOCKET:=/run/ai-pipeline/opsdb.sock}"
: "${OPSDB_EGRESS_SOCKET:=/run/ai-pipeline/egress.sock}"

# B2.1: the token is DATA read from a file, never an env var — survives
# `sudo` env_reset and stays out of the process table. Read it here (as
# ai-developer, which has group-read via ai-pipeline-dev) and --setenv it
# into the sandbox, which is fine (sandbox-internal env).
OPSDB_BROKER_TOKEN="$(<"$TOKEN_FILE_PATH")"
if [ -z "$OPSDB_BROKER_TOKEN" ]; then
  echo "error: token file $TOKEN_FILE_PATH is empty" >&2
  exit 1
fi

if [ ! -S "$OPSDB_BROKER_SOCKET" ]; then
  echo "error: OPSDB_BROKER_SOCKET ($OPSDB_BROKER_SOCKET) is not a live Unix socket — is" >&2
  echo "opsdb_broker.py running? See ops/reviews/task023-os-provisioning-runbook.md" >&2
  exit 1
fi
if [ ! -S "$OPSDB_EGRESS_SOCKET" ]; then
  echo "error: OPSDB_EGRESS_SOCKET ($OPSDB_EGRESS_SOCKET) is not a live Unix socket — is" >&2
  echo "egress_proxy.py running? See ops/reviews/task023-os-provisioning-runbook.md" >&2
  exit 1
fi

# This script's own directory — the fixed relay script lives beside it.
# $0 is the absolute sudoers-named path, so this resolves absolutely.
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
RELAY_SCRIPT="$SELF_DIR/egress_relay.py"
if [ ! -f "$RELAY_SCRIPT" ]; then
  echo "error: egress relay script not found next to this wrapper: $RELAY_SCRIPT" >&2
  exit 1
fi

# The real, installed claude CLI binary — hardcoded to its absolute path
# rather than resolved via $PATH lookup inside the sandbox (§4.4 lists
# /usr, /bin, /lib, /lib64 as the standard read-only system-path binds;
# this hosting environment's actual `claude` install lives under
# /opt/claude-code, confirmed via `readlink -f "$(which claude)"` during
# Development — DEVIATION FROM THE LETTER OF §4.4, DOCUMENTED HERE, NOT
# SILENTLY WIDENED: this is the one additional read-only bind
# (/opt/claude-code, narrowly, not the whole /opt tree) needed for the
# sandboxed process to be able to exec `claude` AT ALL in this specific
# environment's install layout.
CLAUDE_INSTALL_DIR="/opt/claude-code"
CLAUDE_BIN="${CLAUDE_INSTALL_DIR}/bin/claude"
if [ ! -x "$CLAUDE_BIN" ]; then
  echo "error: the claude CLI was not found at $CLAUDE_BIN" >&2
  echo "(this wrapper binds only $CLAUDE_INSTALL_DIR — a different install layout" >&2
  echo "needs a reviewed change to the bind set, not an ad-hoc widening)" >&2
  exit 1
fi

# bwrap itself — absolute, like every other binary in this exec chain, so
# the launch never depends on sudo's `secure_path` (Code Review non-blocking
# item: bwrap was the one non-absolute name in an otherwise fully-absolute
# chain).
BWRAP_BIN="/usr/bin/bwrap"
if [ ! -x "$BWRAP_BIN" ]; then
  echo "error: bubblewrap not found at $BWRAP_BIN — install it (apt-get install -y bubblewrap)" >&2
  echo "see ops/reviews/task023-os-provisioning-runbook.md step 4" >&2
  exit 1
fi

# Coreutils/interpreter absolute paths — the sandbox has /usr bound but no
# guaranteed PATH; name them absolutely so the exec below never depends on
# $PATH.
#
# CODE REVIEW R1 (reproduced live): these must be REAL paths, resolved
# HOST-SIDE, so that this wrapper's own exec chain does not depend on any
# /etc indirection being visible inside the namespace. On this host
# `/usr/bin/python3` is a symlink to `/etc/alternatives/python3` ->
# `/usr/bin/python3.11`; with `/etc` unbound, exec'ing the unresolved path
# fails with `failed to run command '/usr/bin/python3': No such file or
# directory`. `readlink -f` runs out here, on the host, where the whole of
# /etc is readable. (A narrow read-only /etc/alternatives bind IS added
# below, but only so Developer's own `python3 ...` commands work inside the
# sandbox — the launch itself must not depend on it, and does not.)
TIMEOUT_BIN="$(readlink -f /usr/bin/timeout 2>/dev/null || true)"
PYTHON_BIN="$(readlink -f /usr/bin/python3 2>/dev/null || true)"
for resolved in "$TIMEOUT_BIN" "$PYTHON_BIN"; do
  if [ -z "$resolved" ] || [ ! -x "$resolved" ]; then
    echo "error: could not resolve a required interpreter/binary to a real path" >&2
    echo "(timeout='$TIMEOUT_BIN' python3='$PYTHON_BIN')" >&2
    exit 1
  fi
  # Every exec'd binary must live under a path this script actually binds
  # read-only into the namespace. /usr is the only such tree for these two;
  # anything else means the host layout changed and this wrapper must be
  # re-reviewed rather than silently widened to make it work.
  case "$resolved" in
    /usr/*) ;;
    *)
      echo "error: $resolved resolves outside /usr, which is the only system tree this" >&2
      echo "wrapper binds — refusing to widen the bind set implicitly. Re-review §4.4." >&2
      exit 1 ;;
  esac
done

# Fixed loopback endpoint the in-sandbox relay binds and claude is pointed
# at via HTTPS_PROXY (the relay sets HTTPS_PROXY itself, in-process, before
# exec'ing claude — see egress_relay.py). A fixed port is fine: it lives on
# the sandbox's OWN loopback, isolated in its netns.
EGRESS_RELAY_PORT="8889"

BWRAP_ARGS=(
  --unshare-all
  --die-with-parent
  # Code Review non-blocking item: start from an EMPTY environment rather
  # than whatever sudo's env_keep happens to let through, then re-assert
  # only the variables named below. This also neutralizes any ambient
  # http_proxy/https_proxy/no_proxy on the host — an inherited NO_PROXY
  # entry could otherwise make `claude` bypass the in-sandbox relay for
  # that host and fail with an unexplained no-route error. Must come FIRST:
  # bwrap applies these arguments in order, so a --setenv before
  # --clearenv would be wiped.
  --clearenv
  # ORDER MATTERS, and bwrap applies these in sequence: the pseudo/virtual
  # filesystems go FIRST so that a later, more specific bind can never be
  # silently shadowed by one of them. (Observed for real while verifying
  # R1: with `--tmpfs /tmp` emitted after a `--ro-bind` of a path that
  # happened to live under /tmp, the tmpfs hid the bind and the exec failed
  # with a bare "No such file or directory". A deployment whose worktree or
  # scratch paths live under /tmp would have hit exactly that.)
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --ro-bind /usr /usr
  --ro-bind "$CLAUDE_INSTALL_DIR" "$CLAUDE_INSTALL_DIR"
  --ro-bind "$RELAY_SCRIPT" "$RELAY_SCRIPT"
  --bind "$WORKTREE_PATH" "$WORKTREE_PATH"
  --bind "$OPSDB_BROKER_SOCKET" "$OPSDB_BROKER_SOCKET"
  # B3: the ONE permitted egress path — a single bind-mounted Unix socket to
  # the host-side allowlisting egress proxy. --unshare-all (incl.
  # --unshare-net) is retained: the sandbox has no interface/route/DNS; this
  # socket traverses the filesystem namespace, not the network namespace.
  --bind "$OPSDB_EGRESS_SOCKET" "$OPSDB_EGRESS_SOCKET"
  --setenv OPSDB_BROKER_SOCKET "$OPSDB_BROKER_SOCKET"
  --setenv OPSDB_BROKER_TOKEN "$OPSDB_BROKER_TOKEN"
  --setenv EGRESS_UNIX_SOCKET "$OPSDB_EGRESS_SOCKET"
  --setenv EGRESS_RELAY_PORT "$EGRESS_RELAY_PORT"
  # A writable, sandbox-local, ephemeral config dir for claude's own
  # runtime state (session cache etc.) — carved out of the tmpfs /tmp
  # already bound above, never the real $HOME/.claude.json this design's
  # whole point (§5 point 2) is to keep out of ai-developer's reach. NOTE
  # (B4): because this config dir starts empty on a per-session tmpfs,
  # hasTrustDialogAccepted can never be true inside the sandbox, so the
  # developer_pretooluse.py PreToolUse hook does NOT fire here — and that is
  # correct and intended, not a gap: the namespace containment (filesystem/
  # network/PID + the brokers) is strictly stronger than a string-pattern
  # denylist hook and structurally supersedes it. See the addendum's B4
  # disposition; do NOT seed a trust flag to force an inert, redundant hook.
  --setenv CLAUDE_CONFIG_DIR /tmp/claude-config
  --setenv HOME /tmp
  # --clearenv above means NOTHING is inherited, so the basics have to be
  # re-asserted explicitly here or the sandboxed process gets no PATH at all.
  --setenv PATH /usr/local/bin:/usr/bin:/bin
  --setenv LANG C.UTF-8
  --setenv TERM dumb
  --chdir "$WORKTREE_PATH"
)

# CODE REVIEW R1 (reproduced live by the reviewer AND re-reproduced here):
# bwrap starts from an EMPTY root and creates only the paths it is told to.
# It does NOT recreate this host's `/lib64 -> usr/lib64` symlink just
# because /usr is bound. Every dynamically-linked binary here asks the
# kernel for interpreter `/lib64/ld-linux-x86-64.so.2`, so with nothing
# emitted for /bin, /lib, /lib64 the sandbox cannot exec ANYTHING:
#
#   bwrap ... --ro-bind /usr /usr ... -- /usr/bin/timeout ... /usr/bin/echo hello
#   -> bwrap: execvp /usr/bin/timeout: No such file or directory   (exit 1)
#
# Re-creating the symlinks with --symlink makes the identical command print
# `hello`, exit 0. The previous version of this loop emitted NOTHING in the
# symlink case, with a comment claiming /usr covered it; it does not.
for sys_path in /bin /sbin /lib /lib32 /lib64 /libx32; do
  if [ -L "$sys_path" ]; then
    # Re-create the host's own symlink INSIDE the namespace (e.g.
    # `usr/bin` for /bin). --symlink takes the link target first.
    link_target="$(readlink "$sys_path")"
    if [ -n "$link_target" ]; then
      BWRAP_ARGS+=(--symlink "$link_target" "$sys_path")
    fi
  elif [ -d "$sys_path" ]; then
    # A host where these are real, separate directories (§4.4's "symlinks
    # or real binds") — bind them read-only instead.
    BWRAP_ARGS+=(--ro-bind "$sys_path" "$sys_path")
  fi
done

# /etc: NARROW, ENUMERATED binds only — never a blanket `--ro-bind /etc
# /etc`. The egress allowlist config lives at
# /etc/ai-pipeline/egress-allowlist.json and MUST stay invisible inside the
# sandbox (architecture doc Addendum B3: "not bind-mounted into the
# sandbox"; Red Team verified property #5: the sandboxed Developer, even as
# root in its own user namespace, cannot read or widen it). A whole-/etc
# bind would hand it straight to the sandbox.
#
# What is actually needed, derived by exec'ing inside the sandbox rather
# than by reasoning about it:
#   * /etc/alternatives, read-only. NOT needed for this wrapper's own exec
#     chain — TIMEOUT_BIN/PYTHON_BIN are resolved to real paths host-side
#     above, so the launch works even without it — but a plain `python3` (or
#     `editor`, `awk`, ...) PATH lookup inside the sandbox goes through
#     /usr/bin/python3 -> /etc/alternatives/python3, and Developer's own
#     legitimate work runs `python3` constantly. Verified inside a real
#     sandbox: without this bind, `python3 -c ...` fails "No such file or
#     directory"; with it, it runs. It contains only symlinks — no secret,
#     and NOT the allowlist config, which is what the guard below enforces.
#   * /etc/ssl (+ /etc/pki on RH-family hosts) for the system CA bundle, so
#     TLS from the sandboxed CLI to the model API can verify a chain.
#   * /etc/passwd + /etc/group, read-only, so getpwuid()/getgrgid() resolve
#     the sandbox's own uid (Node's os.userInfo() and git both call them).
#     Both are world-readable on the host and carry no secret.
# Deliberately NOT bound: /etc itself, /etc/shadow, /etc/sudoers*,
# /etc/ai-pipeline (the egress allowlist).
# Mirrors egress_proxy.DEFAULT_CONFIG_PATH's directory and the runbook's §6b
# location. If a deployment moves the config, move this with it — the guard
# below is only as good as this value.
EGRESS_ALLOWLIST_DIR="/etc/ai-pipeline"   # host-only — must NEVER be reachable inside
for etc_path in /etc/alternatives /etc/ssl /etc/pki /etc/passwd /etc/group; do
  # Fail closed if this list ever grows into something that would expose the
  # allowlist config (e.g. a well-meaning future "/etc" entry).
  case "$EGRESS_ALLOWLIST_DIR/" in
    "$etc_path"/*)
      echo "error: refusing to bind $etc_path — it would expose $EGRESS_ALLOWLIST_DIR" >&2
      echo "inside the sandbox, breaking the B3 allowlist trust boundary." >&2
      exit 1 ;;
  esac
  if [ -e "$etc_path" ]; then
    BWRAP_ARGS+=(--ro-bind "$etc_path" "$etc_path")
  fi
done

PROMPT_TEXT="$(<"$PROMPT_FILE_PATH")"

# PLACEHOLDER VALUE — flagged for explicit Founder/CTO sign-off, not
# something this Development pass invents authority for: neither
# ops/reviews/cto-task023-architecture.md nor agent_runtime.py's own
# MAX_BUDGET_USD ($0.50, sized for a short Ask-Agent/meeting exchange)
# names a figure appropriate for a full, real, open-ended Developer
# implementation task. $5.00 is a conservative starting placeholder, NOT
# a reviewed number — Red Team/Security should confirm or correct it
# before this wrapper is ever actually invoked (§7 sequencing item 3).
DEVELOPER_MAX_BUDGET_USD="5.00"

# B2.4: wall-clock enforcement runs INSIDE the sandbox via `timeout
# --signal=KILL`, executed as ai-developer against ai-developer's own
# process tree (the killer has permission, unlike the Founder-UID
# launcher's cross-UID killpg). --signal=KILL sends a hard SIGKILL at the
# ceiling. When timeout exits it is this sandbox's PID-namespace init (via
# the exec below), so its exit tears down the whole namespace —
# including the relay — and bwrap's --die-with-parent reaps everything if
# the launcher itself dies first.
#
# The relay (egress_relay.py) is the exec target: it binds the sandbox
# loopback, then forks+execs claude with the argv below passed through
# unchanged (no shell re-interpretation of $PROMPT_TEXT — it is a single
# argv element handed to os.execv). See egress_relay.py's own docstring.
exec "$BWRAP_BIN" "${BWRAP_ARGS[@]}" -- \
  "$TIMEOUT_BIN" --signal=KILL "$WALLCLOCK_S" \
  "$PYTHON_BIN" "$RELAY_SCRIPT" \
  "$CLAUDE_BIN" \
  --agent developer \
  --tools "Read,Edit,Write,Bash,Grep,Glob,Skill" \
  --output-format stream-json \
  --max-budget-usd "$DEVELOPER_MAX_BUDGET_USD" \
  -p "$PROMPT_TEXT"
