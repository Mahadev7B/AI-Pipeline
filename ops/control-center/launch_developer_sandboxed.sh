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

# Coreutils absolute paths — the sandbox has /usr bound but no guaranteed
# PATH; name them absolutely so the exec below never depends on $PATH.
TIMEOUT_BIN="/usr/bin/timeout"
PYTHON_BIN="/usr/bin/python3"

# Fixed loopback endpoint the in-sandbox relay binds and claude is pointed
# at via HTTPS_PROXY (the relay sets HTTPS_PROXY itself, in-process, before
# exec'ing claude — see egress_relay.py). A fixed port is fine: it lives on
# the sandbox's OWN loopback, isolated in its netns.
EGRESS_RELAY_PORT="8889"

BWRAP_ARGS=(
  --unshare-all
  --die-with-parent
  --ro-bind /usr /usr
  --ro-bind "$CLAUDE_INSTALL_DIR" "$CLAUDE_INSTALL_DIR"
  --ro-bind "$RELAY_SCRIPT" "$RELAY_SCRIPT"
  --proc /proc
  --dev /dev
  --tmpfs /tmp
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
  --chdir "$WORKTREE_PATH"
)

# /bin, /lib, /lib64 are symlinks into /usr on this host (confirmed during
# Development: `readlink /bin` -> usr/bin) — already reachable via the /usr
# bind above. Left as a conditional for portability to a host where they
# are real, separate directories (§4.4's "symlinks or real binds").
for real_dir in /bin /lib /lib64; do
  if [ -d "$real_dir" ] && [ ! -L "$real_dir" ]; then
    BWRAP_ARGS+=(--ro-bind "$real_dir" "$real_dir")
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
exec bwrap "${BWRAP_ARGS[@]}" -- \
  "$TIMEOUT_BIN" --signal=KILL "$WALLCLOCK_S" \
  "$PYTHON_BIN" "$RELAY_SCRIPT" \
  "$CLAUDE_BIN" \
  --agent developer \
  --tools "Read,Edit,Write,Bash,Grep,Glob,Skill" \
  --output-format stream-json \
  --max-budget-usd "$DEVELOPER_MAX_BUDGET_USD" \
  -p "$PROMPT_TEXT"
