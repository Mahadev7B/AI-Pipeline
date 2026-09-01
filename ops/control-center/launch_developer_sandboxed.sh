#!/usr/bin/env bash
# ops/control-center/launch_developer_sandboxed.sh — TASK-023
# (ops/reviews/cto-task023-architecture.md §2.3/§4.4/§7 item 3).
#
# The fixed, reviewed, non-parameterized-in-shell-syntax wrapper that
# actually builds and execs `bwrap ... -- claude --agent developer ...`.
# This is the exact sudoers NOPASSWD target
# (ops/reviews/task023-os-provisioning-runbook.md) — its own path is what
# the one narrowly-scoped sudoers line names, nothing broader.
#
# NOT EXECUTED as part of TASK-023's Development pass. It depends on the
# `ai-developer` account, the `ai-pipeline-dev`/`ai-pipeline-db` groups,
# and a real running opsdb_broker.py — none of which exist yet in this
# environment. See ops/reviews/task023-os-provisioning-runbook.md for how
# a human with root/sudo brings all of that up, after which this script
# is exercised for real as part of §7 sequencing item 3/item 7 (the QA
# charter, out of this task's own scope).
#
# WHY THIS SCRIPT IS SAFE TO CALL FROM A SUDOERS NOPASSWD LINE: every
# argument this script receives is used ONLY as literal argv elements in
# an exec'd array (bwrap's own argv, then claude's own argv nested after
# `--`) — never passed through `sh -c`, `eval`, or any other
# shell-re-interpretation step. Task/prompt CONTENT is passed as DATA (a
# file path this script reads with `cat`/`$(<file)`, never a shell string
# built by concatenating untrusted content into a command line) — per the
# architecture doc's own explicit requirement ("task content is passed as
# data, not spliced into shell syntax", §4.1 step 3). set -euo pipefail
# and IFS hardening below exist so an unexpected empty/missing argument
# fails loudly instead of silently expanding into something else.
#
# Usage:
#   launch_developer_sandboxed.sh <worktree-path> <prompt-file-path>
#
#   <worktree-path>    absolute path to this task's dedicated git worktree
#                       (§4.4 — bind-mounted read-write, owned via the
#                       shared ai-pipeline-dev group).
#   <prompt-file-path>  absolute path to a file (inside the worktree, or
#                       any other path THIS script's own caller can read)
#                       containing the full assembled task transcript —
#                       written by launch_developer_session.py's step 1
#                       (§4.1) BEFORE this script is invoked.
#
#   Environment (set by launch_developer_session.py before invoking this
#   script via `sudo -u ai-developer`, and explicitly re-asserted into the
#   sandbox below via --setenv, never a blanket env passthrough):
#     OPSDB_BROKER_SOCKET   the broker's fixed socket path
#                           (default /run/ai-pipeline/opsdb.sock)
#     OPSDB_BROKER_TOKEN    this session's per-invocation broker token

set -euo pipefail
IFS=$'\n\t'

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <worktree-path> <prompt-file-path>" >&2
  exit 64  # EX_USAGE
fi

WORKTREE_PATH="$1"
PROMPT_FILE_PATH="$2"

if [ ! -d "$WORKTREE_PATH" ]; then
  echo "error: worktree path does not exist or is not a directory: $WORKTREE_PATH" >&2
  exit 1
fi
if [ ! -f "$PROMPT_FILE_PATH" ]; then
  echo "error: prompt file does not exist: $PROMPT_FILE_PATH" >&2
  exit 1
fi

: "${OPSDB_BROKER_SOCKET:=/run/ai-pipeline/opsdb.sock}"
if [ -z "${OPSDB_BROKER_TOKEN:-}" ]; then
  echo "error: OPSDB_BROKER_TOKEN is not set — launch_developer_session.py must register a" >&2
  echo "session and export this before invoking this script (see its own module docstring)" >&2
  exit 1
fi
if [ ! -S "$OPSDB_BROKER_SOCKET" ]; then
  echo "error: OPSDB_BROKER_SOCKET ($OPSDB_BROKER_SOCKET) is not a live Unix socket — is" >&2
  echo "opsdb_broker.py running? See ops/reviews/task023-os-provisioning-runbook.md" >&2
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
# environment's install layout. Flagged explicitly for Code Review/Red
# Team to bless or correct before this ships — not a policy change, a
# concrete infra detail the architecture document's own §1 feasibility
# spike did not need to resolve (it invoked /bin/echo and /bin/sh, both
# already under /usr).
CLAUDE_INSTALL_DIR="/opt/claude-code"
CLAUDE_BIN="${CLAUDE_INSTALL_DIR}/bin/claude"

BWRAP_ARGS=(
  --unshare-all
  --die-with-parent
  --ro-bind /usr /usr
  --ro-bind "$CLAUDE_INSTALL_DIR" "$CLAUDE_INSTALL_DIR"
  --proc /proc
  --dev /dev
  --tmpfs /tmp
  --bind "$WORKTREE_PATH" "$WORKTREE_PATH"
  --bind "$OPSDB_BROKER_SOCKET" "$OPSDB_BROKER_SOCKET"
  --setenv OPSDB_BROKER_SOCKET "$OPSDB_BROKER_SOCKET"
  --setenv OPSDB_BROKER_TOKEN "$OPSDB_BROKER_TOKEN"
  # A writable, sandbox-local, ephemeral config dir for claude's own
  # runtime state (session cache etc.) — carved out of the tmpfs /tmp
  # already bound above, never the real $HOME/.claude.json this design's
  # whole point (§5 point 2) is to keep out of ai-developer's reach.
  --setenv CLAUDE_CONFIG_DIR /tmp/claude-config
  --setenv HOME /tmp
  --chdir "$WORKTREE_PATH"
)

# /bin, /lib, /lib64 are symlinks into /usr on this host (confirmed
# during Development: `readlink /bin` -> usr/bin) — already reachable via
# the /usr bind above without a separate --ro-bind. Left as a conditional
# for portability to a host where they are real, separate directories
# (§4.4's own "symlinks or real binds" phrasing anticipates exactly this).
for real_dir in /bin /lib /lib64; do
  if [ -d "$real_dir" ] && [ ! -L "$real_dir" ]; then
    BWRAP_ARGS+=(--ro-bind "$real_dir" "$real_dir")
  fi
done

PROMPT_TEXT="$(cat "$PROMPT_FILE_PATH")"

# PLACEHOLDER VALUE — flagged for explicit Founder/CTO sign-off, not
# something this Development pass invents authority for: neither
# ops/reviews/cto-task023-architecture.md nor agent_runtime.py's own
# MAX_BUDGET_USD ($0.50, sized for a short Ask-Agent/meeting exchange)
# names a figure appropriate for a full, real, open-ended Developer
# implementation task. $5.00 is a conservative starting placeholder, NOT
# a reviewed number — Red Team/Security should confirm or correct it
# before this wrapper is ever actually invoked (§7 sequencing item 3).
DEVELOPER_MAX_BUDGET_USD="5.00"

exec bwrap "${BWRAP_ARGS[@]}" -- \
  "$CLAUDE_BIN" \
  --agent developer \
  --tools "Read,Edit,Write,Bash,Grep,Glob,Skill" \
  --output-format stream-json \
  --max-budget-usd "$DEVELOPER_MAX_BUDGET_USD" \
  -p "$PROMPT_TEXT"
