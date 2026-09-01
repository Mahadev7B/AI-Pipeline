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
  3. Runs `sudo --preserve-env=OPSDB_BROKER_SOCKET,OPSDB_EGRESS_SOCKET -u
     ai-developer launch_developer_sandboxed.sh <worktree> <prompt-file>
     <token-file> <wallclock-seconds>` via subprocess.Popen(...,
     start_new_session=True) — the same real-child-OS-process pattern
     agent_runtime.py's own `_run_claude()` already establishes, extended
     with the `sudo -u` prefix and real tool grants. The broker token
     travels as a group-readable FILE (B2.1 — survives `sudo`'s env_reset,
     stays out of the process table); only the non-secret socket PATHS
     travel as `--preserve-env` env vars.
  4. Streams the subprocess's stdout live to the caller's own stdout as it
     is produced — not a batch replay assembled after the fact (§4.2's
     own disclosed ergonomics tradeoff: this is a streamed subprocess
     output feed, not the native in-context Task-tool UI).
  5. Wall-clock enforcement is PRIMARILY the inner `timeout --signal=KILL
     <wallclock>` inside the sandbox (B2.4 — run as ai-developer against
     its own tree, where the killer has permission, plus bwrap
     `--die-with-parent`). This launcher keeps only a BACKSTOP outer timer
     reusing agent_runtime._kill_process_group() — hardened so the
     PermissionError a Founder-UID `killpg` of the root/ai-developer
     process group raises is reported (a loud stderr warning) and returned
     as `False` rather than thrown away in the timer thread. When that
     happens the launcher stops draining the child's stdout, returns
     `abandoned=True`/`ok=False` with an explicit error, and never blocks
     forever on a process nobody was permitted to kill (Code Review R3).
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
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CONTROL_CENTER_DIR = Path(__file__).resolve().parent
DB_DIR = REPO_ROOT / "ops" / "db"

sys.path.insert(0, str(DB_DIR))
sys.path.insert(0, str(CONTROL_CENTER_DIR))
import opsdb  # noqa: E402
import opsdb_broker  # noqa: E402
import egress_proxy  # noqa: E402 — for its DEFAULT_SOCKET_PATH only
import agent_runtime  # noqa: E402 — reuses _kill_process_group() directly, see module docstring
import review_transcripts  # noqa: E402 — reuses _read_coding_standards()/CODING_STANDARDS_PATH

LAUNCH_SCRIPT = CONTROL_CENTER_DIR / "launch_developer_sandboxed.sh"

# B2.2 (Code Review REJECT): the prompt and token files must be readable by
# `ai-developer`, so they go in a session dir INSIDE the per-task worktree
# (already bind-mounted and group-shared via ai-pipeline-dev with the setgid
# bit, §4.4) — NOT a mode-0700 tempfile.mkdtemp() the sandbox's UID cannot
# even traverse. The dir name is dot-prefixed and cleaned up in `finally`.
_SESSION_SCRATCH_DIRNAME = ".ai-pipeline-session"

# B2.4: wall-clock is enforced PRIMARILY inside the sandbox by
# `timeout --signal=KILL` (as ai-developer, against its own tree). This
# launcher's own outer timer is only a BACKSTOP, so it is given extra grace
# beyond the inner ceiling — the inner timeout should always fire first.
_OUTER_TIMER_GRACE_S = 60.0

# CODE REVIEW R3 knobs. The output reader polls rather than blocking, so the
# timeout backstop can always make progress even when the kill was refused.
_STREAM_POLL_S = 0.5        # how long a single select() on the child's stdout waits
_POST_TIMEOUT_DRAIN_S = 5.0  # after the timeout fires, keep draining this long, then give up
_ABANDON_WAIT_S = 5.0        # bounded final wait() on an abandoned (unkillable) child
_READ_CHUNK = 65_536

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


def _write_session_files(worktree_path: Path, transcript: str, token: str) -> tuple[Path, Path, Path]:
    """Write the prompt and token files into a session dir INSIDE the
    worktree (B2.2) so `ai-developer` can read them via the shared
    ai-pipeline-dev group. Returns (session_dir, prompt_file, token_file).
    Files are 0640 (group-readable, not other-readable); the token is not a
    secret to the sandbox itself — it is handed to the sandbox anyway — but
    passing it as a file (not an env var) keeps it out of the process table
    and survives `sudo`'s env_reset (B2.1)."""
    session_dir = worktree_path / _SESSION_SCRATCH_DIRNAME
    session_dir.mkdir(mode=0o750, exist_ok=True)
    # mkdir(mode=...) is masked by the process umask (umask 077 would yield
    # 0700 and reproduce Code Review's original B2.2: ai-developer cannot
    # even traverse it), and exist_ok=True does not repair a pre-existing
    # wrong mode. chmod explicitly, exactly as the two files below do.
    session_dir.chmod(0o750)
    prompt_file = session_dir / "prompt.txt"
    prompt_file.write_text(transcript)
    prompt_file.chmod(0o640)
    token_file = session_dir / "broker-token"
    token_file.write_text(token)
    token_file.chmod(0o640)
    return session_dir, prompt_file, token_file


def _write_out(chunk: bytes) -> None:
    """Write raw child output to this process's own stdout.

    Code Review round-3 non-blocking item: `sys.stdout.buffer` is the right
    target for the real CLI path (the child's output is `stream-json`
    NDJSON — arbitrary UTF-8, forwarded byte-for-byte, never re-encoded),
    but a test harness that replaces `sys.stdout` with a text-only object
    (`io.StringIO`, pytest's capture) has no `.buffer` and this used to
    raise `AttributeError` in the middle of the read loop. Fall back to a
    decoded text write in that case."""
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is not None:
        buffer.write(chunk)
        buffer.flush()
    else:
        sys.stdout.write(chunk.decode("utf-8", errors="replace"))
        sys.stdout.flush()


def _stream_process_output(proc: subprocess.Popen, timed_out: threading.Event) -> tuple[bool, str | None]:
    """Stream the child's combined stdout/stderr to our own stdout as it is
    produced, WITHOUT ever blocking indefinitely (Code Review R3).

    Returns `(reached_eof, failure_kind)`:
      * `(True, None)`  — the stream reached EOF. The normal path, including
        a timeout whose kill actually worked.
      * `(False, "timeout")` — we stopped draining a stream that never
        closed after the wall-clock timeout fired: the refused-cross-UID-kill
        case the B2.4 backstop exists for.
      * `(False, "read_error")` — `select`/`os.read` failed with NO timeout
        in play. Code Review round-3 non-blocking item: this is a broken
        pipe/closed fd, NOT an unkillable session, and the caller must not
        describe it as "exceeded the timeout and could not be killed",
        which would be simply false.

    Either False is "abandoned" — the caller must not treat it as a clean
    exit — but the two have different causes and must be reported
    differently.

    Why not `for line in proc.stdout` plus a `close()` from the timer
    thread: closing a buffered stream while another thread is blocked
    reading it does not reliably unblock that reader (the reader holds the
    stream's lock, and the close raises `RuntimeError: reentrant call`
    instead). Polling the raw fd with select() and os.read() has no such
    interaction, so the timeout is always able to take effect.

    NDJSON note (Code Review round-3 C1): this loop is deliberately a raw
    BYTE pump, not a line reader. `--output-format stream-json --verbose`
    emits newline-delimited JSON with many events per turn and individual
    lines measured at 2 KB+ (the `init` event) and unbounded above, so any
    line-oriented or fixed-width framing here would risk truncation or
    interleaving. Forwarding chunks verbatim is correct for arbitrarily
    long lines and preserves the live streaming §4.1 step 4 requires;
    verified against the real binary's real NDJSON output.
    """
    fd = proc.stdout.fileno()
    give_up_at: float | None = None
    while True:
        if timed_out.is_set() and give_up_at is None:
            # Drain whatever the (possibly dying) child still has to say,
            # then stop — bounded, so a survivor cannot block us forever.
            give_up_at = time.monotonic() + _POST_TIMEOUT_DRAIN_S
        if give_up_at is not None and time.monotonic() >= give_up_at:
            return (False, "timeout")
        try:
            readable, _, _ = select.select([fd], [], [], _STREAM_POLL_S)
        except (OSError, ValueError):
            return (False, "timeout" if timed_out.is_set() else "read_error")
        if not readable:
            continue
        try:
            chunk = os.read(fd, _READ_CHUNK)
        except OSError:
            return (False, "timeout" if timed_out.is_set() else "read_error")
        if not chunk:
            return (True, None)  # EOF — every writer of this pipe is gone
        _write_out(chunk)


def run_sandboxed_developer_session(task_id: int, worktree_path: Path,
                                     socket_path: str = opsdb_broker.DEFAULT_SOCKET_PATH,
                                     egress_socket_path: str = egress_proxy.DEFAULT_SOCKET_PATH,
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
    token = register_session(socket_path, task_id)
    session_dir, prompt_file, token_file = _write_session_files(worktree_path, transcript, token)

    # B2.1: the token travels as a FILE argument; only the non-secret socket
    # PATHS travel as env vars, preserved across `sudo`'s env_reset via
    # `--preserve-env` (the sudoers line carries the matching SETENV: tag —
    # see the runbook). B2.4: the inner wall-clock ceiling is passed as a
    # positional arg (int seconds) for `timeout --signal=KILL` inside the
    # sandbox to enforce as ai-developer against its own tree.
    cmd = [
        "sudo",
        "--preserve-env=OPSDB_BROKER_SOCKET,OPSDB_EGRESS_SOCKET",
        "-u", "ai-developer",
        str(LAUNCH_SCRIPT),
        str(worktree_path),
        str(prompt_file),
        str(token_file),
        str(int(timeout_s)),
    ]
    env = os.environ.copy()
    env["OPSDB_BROKER_SOCKET"] = socket_path
    env["OPSDB_EGRESS_SOCKET"] = egress_socket_path

    result = {"ok": False, "returncode": None, "timed_out": False,
              "kill_refused": False, "abandoned": False, "error": None}
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            # Observed against the real binary while verifying C1: with an
            # inherited stdin the CLI blocks for 3s per launch waiting for
            # piped input ("Warning: no stdin data received in 3s") before
            # proceeding. DEVNULL also means the sandboxed session can never
            # consume keystrokes from the watching human's own terminal.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Bytes, not text: the stream is drained with os.read() on the raw
            # fd (see _stream_process_output) so a timer thread can never be
            # blocked behind a buffered text read that will not return.
            env=env,
            start_new_session=True,  # own process group — agent_runtime._kill_process_group() needs this
        )
    except (FileNotFoundError, OSError) as exc:
        end_session(socket_path, token)
        shutil.rmtree(session_dir, ignore_errors=True)
        result["error"] = f"could not start sandboxed Developer process: {exc}"
        return result

    timed_out = threading.Event()
    kill_refused = threading.Event()

    def _on_timeout() -> None:
        # B2.4 BACKSTOP ONLY — the inner `timeout --signal=KILL` (running as
        # ai-developer) is the primary enforcement. This outer killpg fires
        # `_OUTER_TIMER_GRACE_S` later and cannot throw in this timer thread
        # if the cross-UID kill is refused: agent_runtime._kill_process_group()
        # handles PermissionError (the process group holds root-owned `sudo`
        # and ai-developer-owned `bwrap`/`claude` this Founder-UID process
        # cannot signal) and returns False instead.
        #
        # CODE REVIEW R3: a timeout that cannot be enforced must be LOUD and
        # must not hang. Setting `timed_out` alone was not enough — the
        # reader was blocked on a stream that a surviving process never
        # closes. So: record the timeout, record whether the kill was
        # actually refused, and let _stream_process_output() (which polls
        # `timed_out` between reads rather than blocking indefinitely) stop
        # draining and return. Nothing here touches proc.stdout directly:
        # closing a buffered stream from a second thread while the reader
        # holds its lock does not reliably unblock the reader.
        timed_out.set()
        if not agent_runtime._kill_process_group(proc):
            kill_refused.set()
            sys.stderr.write(
                f"[launch_developer_session] WARNING: the outer wall-clock backstop "
                f"could not kill the sandboxed session (pid {proc.pid}); it may still "
                "be running under ai-developer. The session is being ABANDONED, not "
                "reported as a clean exit. Check for a surviving `bwrap`/`claude` "
                "process and see ops/reviews/task023-os-provisioning-runbook.md.\n"
            )
            sys.stderr.flush()

    timer = threading.Timer(timeout_s + _OUTER_TIMER_GRACE_S, _on_timeout)
    timer.start()
    try:
        reached_eof, failure_kind = _stream_process_output(proc, timed_out)
        if reached_eof:
            proc.wait()
        else:
            # The stream never closed after the timeout — do NOT wait
            # forever on a process nobody was permitted to kill.
            try:
                proc.wait(timeout=_ABANDON_WAIT_S)
            except subprocess.TimeoutExpired:
                pass
    finally:
        timer.cancel()
        try:
            proc.stdout.close()
        except OSError:
            pass
        end_session(socket_path, token)
        shutil.rmtree(session_dir, ignore_errors=True)

    result["timed_out"] = timed_out.is_set()
    result["kill_refused"] = kill_refused.is_set()
    result["abandoned"] = not reached_eof
    result["returncode"] = proc.returncode
    result["ok"] = (proc.returncode == 0) and not result["timed_out"] and reached_eof
    if result["abandoned"] and failure_kind == "read_error":
        # Code Review round-3 non-blocking item: this branch is a stream
        # read failure with NO timeout in play (broken pipe, closed fd). It
        # must NOT claim the session "exceeded the timeout and could not be
        # killed" — that would be false, and would send whoever reads it
        # hunting for a surviving bwrap process that does not exist.
        result["error"] = (
            "the sandboxed Developer session's output stream failed before it closed "
            "(read error, not a timeout); output may be incomplete and the exit status "
            "may not reflect the real outcome"
        )
    elif result["abandoned"]:
        result["error"] = (
            f"sandboxed Developer session exceeded {timeout_s:g}s and could NOT be killed "
            "by this launcher (cross-UID kill refused); its output stream was abandoned "
            "and the process may still be running as ai-developer"
        )
    elif result["timed_out"]:
        result["error"] = f"sandboxed Developer session exceeded {timeout_s:g}s and was killed"
    elif proc.returncode != 0:
        result["error"] = f"sandboxed Developer session exited with code {proc.returncode}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", type=int, required=True, dest="task_id")
    parser.add_argument("--worktree-path", type=Path, required=True, dest="worktree_path")
    parser.add_argument("--socket-path", default=opsdb_broker.DEFAULT_SOCKET_PATH, dest="socket_path")
    parser.add_argument("--egress-socket-path", default=egress_proxy.DEFAULT_SOCKET_PATH,
                         dest="egress_socket_path")
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S, dest="timeout_s")
    args = parser.parse_args()

    try:
        result = run_sandboxed_developer_session(
            args.task_id, args.worktree_path, socket_path=args.socket_path,
            egress_socket_path=args.egress_socket_path, timeout_s=args.timeout_s,
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
