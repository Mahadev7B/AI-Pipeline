#!/usr/bin/env python3
"""ops/control-center/launch_developer_session.py — TASK-023
(ops/reviews/cto-task023-architecture.md §4.1/§7 item 4).

The host-side launcher for a sandboxed Developer invocation — runs as the
Founder's own user (never as `ai-developer`). Concretely:

  1. Assembles this task's full transcript (task fields, architecture
     notes, mockup, CODING_STANDARDS.md) — §4.1 step 1: Developer does
     not get a live database read path inside the sandbox (the `query`
     verb is deliberately excluded from opsdb_broker.py, per the
     Correction section of the architecture doc), so everything Developer
     needs is assembled here, BEFORE the sandbox starts, not fetched from
     inside it.
  2. Generates a random per-session token (`secrets.token_hex(16)`) and
     registers `(token, task_id, agent="developer")` with opsdb_broker.py
     over its Unix socket, using the trusted-only `register_session` verb
     — this call's own peer credentials (this process's real UID, read via
     SO_PEERCRED on the broker's side) are what make the token's later
     task-id binding real enforcement, not a documentation convention
     (see opsdb_broker.py's own module docstring).
  3. Runs `sudo -u ai-developer ops/control-center/launch_developer_sandboxed.sh
     <worktree> <prompt-file>` via subprocess.Popen(..., start_new_session=True)
     — the same real-child-OS-process pattern agent_runtime.py's own
     `_run_claude()` already establishes for the unsupervised (zero-tool)
     paths, extended here with the `sudo -u` prefix and real tool grants.
  4. Streams the subprocess's stdout live to the caller's own stdout as it
     is produced — not a batch replay assembled after the fact (§4.2's
     own disclosed ergonomics tradeoff: this is a streamed subprocess
     output feed, not the native in-context Task-tool UI).
  5. Applies a wall-clock timeout and a process-group kill on expiry —
     the exact `start_new_session=True` + `os.killpg(os.getpgid(...),
     SIGKILL)` pattern agent_runtime.py's own `_kill_process_group()`
     already implements; reused directly here (imported from
     agent_runtime), not reimplemented.
  6. Calls `end_session` on the broker when the sandboxed process exits
     (success, failure, or timeout alike) so a stale token cannot be
     reused for anything ever again.

NOT INVOKED END TO END as part of TASK-023's Development pass — it
depends on the `ai-developer` account and a real, running
opsdb_broker.py, neither of which exist yet in this environment. See
ops/reviews/task023-os-provisioning-runbook.md. This module IS
syntax-checked (`python3 -m py_compile`) and its pure/testable pieces
(transcript assembly, the broker register/end-session request shapes)
can be exercised directly against the in-process broker the same way
ops/db/test_opsdb_broker.py already does — left to Code Review/QA to
decide whether a dedicated test file for this launcher is worth adding
before the account exists to run it for real.

DELIBERATELY NOT WIRED IN as this repo's default Developer-invocation
path — this session's own ability to dispatch Developer via the native
Task-tool subagent mechanism is untouched by this file's existence. §7's
own sequencing gates the actual cutover on DevOps' production-host
feasibility re-verification and a live QA charter, both explicitly out of
this Development pass's scope.
"""
from __future__ import annotations

import argparse
import os
import secrets
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTROL_CENTER_DIR = Path(__file__).resolve().parent
DB_DIR = REPO_ROOT / "ops" / "db"

sys.path.insert(0, str(DB_DIR))
sys.path.insert(0, str(CONTROL_CENTER_DIR))
import opsdb  # noqa: E402
import opsdb_broker  # noqa: E402
import agent_runtime  # noqa: E402 — reuses _kill_process_group() directly, see module docstring
import review_transcripts  # noqa: E402 — reuses _read_coding_standards()/CODING_STANDARDS_PATH

LAUNCH_SCRIPT = CONTROL_CENTER_DIR / "launch_developer_sandboxed.sh"

# PLACEHOLDER VALUE — see the identical disclosure in
# launch_developer_sandboxed.sh next to DEVELOPER_MAX_BUDGET_USD. This is
# the WALL-CLOCK ceiling on the whole supervised session (independent of
# the model's own per-call $ budget, which the sandboxed claude
# invocation enforces on itself via --max-budget-usd). Neither the
# architecture document nor agent_runtime.py's own DEFAULT_TIMEOUT_S
# (30s, sized for a short Ask-Agent exchange) names a figure appropriate
# for a full, open-ended Developer implementation task — 30 minutes is a
# conservative starting placeholder for real supervised work, NOT a
# reviewed number. Confirm or correct before this is ever actually
# invoked (§7 sequencing item 3).
DEFAULT_TIMEOUT_S = 1800.0

_TASK_FIELDS_FOR_TRANSCRIPT = (
    "title", "business_goal", "user_story", "priority", "dependencies",
    "requirements", "acceptance_criteria", "mockup_design",
    "architecture_notes", "tests_required", "security_considerations",
    "blockers", "next_action",
)


class LaunchError(Exception):
    """Raised for any failure before/around the sandboxed subprocess
    itself (missing task, broker unreachable, registration refused) —
    distinct from a real invocation's own failure/timeout, which is
    reported via the returned dict instead of an exception (matching
    agent_runtime.RuntimeResult's own "never raise for an ordinary
    invocation outcome" convention)."""


def assemble_developer_transcript(task_row) -> str:
    """§4.1 step 1: everything Developer needs, assembled here before the
    sandbox starts — task fields, CODING_STANDARDS.md, and explicit
    instructions covering the one thing that's genuinely different in
    this invocation mode: writes to operations.sqlite3 go through the
    broker-backed opsdb.py CLI exactly as always (same commands, same
    flags), but only handoff/task-status/task-step-status/task-progress/
    activity-log actually reach the database — everything else opsdb.py
    would normally do (query, task-update, etc.) has no path through the
    sandbox and will fail with a clear "does not exist" error, by design
    (§3 of the architecture doc)."""
    lines = [
        f"You are Developer working on TASK-{task_row['id']:03d}: {task_row['title']}",
        "",
        "You are running in a SANDBOXED invocation "
        "(ops/reviews/cto-task023-architecture.md) — a real OS-level process, "
        "not the native Task-tool subagent mechanism. Everything you need for "
        "this task is assembled below; there is no live database read path "
        "inside this sandbox (operations.sqlite3 itself is not present in your "
        "filesystem — only a fixed set of opsdb.py write commands reach it, "
        "through a broker).",
        "",
    ]
    for field in _TASK_FIELDS_FOR_TRANSCRIPT:
        value = task_row[field] if field in task_row.keys() else None
        if value:
            label = field.replace("_", " ").title()
            lines.append(f"## {label}")
            lines.append(str(value))
            lines.append("")

    lines.append("## Coding standards")
    lines.append(review_transcripts._read_coding_standards())
    lines.append("")
    lines.append(
        "Hand off to Code Review with `python3 ops/db/opsdb.py handoff "
        "--task-id <this task> --from-agent developer --to-agent code-review "
        "--base-commit-sha <sha> --head-commit-sha <sha> ...` exactly as you "
        "always would — --task-id/--from-agent are accepted for CLI-syntax "
        "parity but the broker forces the real values for you; --to-agent "
        "must be code-review (the only value the broker will forward)."
    )
    return "\n".join(lines)


def register_session(socket_path: str, task_id: int) -> str:
    """Generates a fresh token and registers it with the broker. Raises
    LaunchError if the broker is unreachable or refuses the registration
    (e.g. this process's own UID is not in the broker's trusted set — see
    opsdb_broker.py's _default_trusted_uids())."""
    token = secrets.token_hex(16)
    try:
        response = opsdb_broker.send_request(
            socket_path,
            {"verb": "register_session", "args": {"token": token, "task_id": task_id, "agent": "developer"}},
        )
    except OSError as exc:
        raise LaunchError(f"could not reach opsdb_broker at {socket_path!r}: {exc}") from exc
    if not response.get("ok"):
        raise LaunchError(f"broker refused session registration: {response.get('error')}")
    return token


def end_session(socket_path: str, token: str) -> None:
    """Best-effort — a failure here must never mask the real outcome of
    the sandboxed invocation itself (same "cleanup failure never masks
    the primary result" discipline this codebase already applies
    elsewhere, e.g. meeting_orchestrator's reservation rollback)."""
    try:
        opsdb_broker.send_request(socket_path, {"verb": "end_session", "args": {"token": token}})
    except OSError as exc:
        sys.stderr.write(f"[launch_developer_session] warning: end_session failed: {exc}\n")


def run_sandboxed_developer_session(task_id: int, worktree_path: Path,
                                     socket_path: str = opsdb_broker.DEFAULT_SOCKET_PATH,
                                     timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
    """Returns {"ok": bool, "returncode": int|None, "timed_out": bool,
    "error": str|None}. Streams the sandboxed process's combined
    stdout/stderr live to THIS process's own stdout as it is produced —
    §4.1 step 4's disclosed streamed-subprocess-output ergonomics."""
    conn = opsdb.connect()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    finally:
        conn.close()
    if task_row is None:
        raise LaunchError(f"no such task TASK-{task_id:03d}")

    transcript = assemble_developer_transcript(task_row)
    prompt_dir = Path(tempfile.mkdtemp(prefix=f"developer-session-task{task_id}-"))
    prompt_file = prompt_dir / "prompt.txt"
    prompt_file.write_text(transcript)
    # World-unreadable by default umask concerns aside, this is explicit
    # defense-in-depth: the prompt file (task content, never a secret, but
    # no reason to leave it group/other-readable) is chmod'd narrowly and
    # `ai-developer` needs read access via the worktree's own shared-group
    # bind — the prompt file itself lives OUTSIDE the worktree in this
    # scratch dir, so it must be independently reachable to `ai-developer`;
    # see ops/reviews/task023-os-provisioning-runbook.md for the concrete
    # ownership/group step this implies (writing the prompt file under the
    # worktree itself, which IS bind-mounted, is the simpler alternative a
    # real deployment may prefer — left as an explicit choice for whoever
    # wires this up for real, not silently decided here).
    prompt_file.chmod(0o640)

    token = register_session(socket_path, task_id)

    cmd = ["sudo", "-u", "ai-developer", str(LAUNCH_SCRIPT), str(worktree_path), str(prompt_file)]
    env = os.environ.copy()
    env["OPSDB_BROKER_SOCKET"] = socket_path
    env["OPSDB_BROKER_TOKEN"] = token

    result = {"ok": False, "returncode": None, "timed_out": False, "error": None}
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            start_new_session=True,  # own process group — agent_runtime._kill_process_group() needs this
        )
    except (FileNotFoundError, OSError) as exc:
        end_session(socket_path, token)
        result["error"] = f"could not start sandboxed Developer process: {exc}"
        return result

    timed_out = threading.Event()

    def _on_timeout() -> None:
        timed_out.set()
        agent_runtime._kill_process_group(proc)

    timer = threading.Timer(timeout_s, _on_timeout)
    timer.start()
    try:
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        proc.wait()
    finally:
        timer.cancel()
        end_session(socket_path, token)

    result["timed_out"] = timed_out.is_set()
    result["returncode"] = proc.returncode
    result["ok"] = (proc.returncode == 0) and not result["timed_out"]
    if result["timed_out"]:
        result["error"] = f"sandboxed Developer session exceeded {timeout_s:g}s and was killed"
    elif proc.returncode != 0:
        result["error"] = f"sandboxed Developer session exited with code {proc.returncode}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", type=int, required=True, dest="task_id")
    parser.add_argument("--worktree-path", type=Path, required=True, dest="worktree_path")
    parser.add_argument("--socket-path", default=opsdb_broker.DEFAULT_SOCKET_PATH, dest="socket_path")
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S, dest="timeout_s")
    args = parser.parse_args()

    try:
        result = run_sandboxed_developer_session(
            args.task_id, args.worktree_path, socket_path=args.socket_path, timeout_s=args.timeout_s,
        )
    except LaunchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not result["ok"]:
        print(f"error: {result['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
