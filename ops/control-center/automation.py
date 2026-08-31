"""ops/control-center/automation.py — Phase 3A Part B (TASK-015).

Limited Automated Orchestration: a background poller that notices when a
task genuinely enters CODE_REVIEW with a real, complete Developer handoff,
and — if the Founder has turned automation on — triggers exactly one
automated Code Review invocation for it. Full design:
ops/reviews/cto-phase3a-architecture.md §B.1-§B.13; independently reviewed
in ops/reviews/security-phase3a-threat-model.md (required fixes C1-C4) and
ops/reviews/red-team-phase3a-architecture.md (required fixes RT1-RT3,
non-blocking NB1-NB5) — every one of those corrections is folded into this
module, cited inline at the exact line it fixes, not merely present as a
comment elsewhere.

Mirrors meeting_orchestrator.py's separation from server.py: pure
orchestration glue, imports opsdb/agent_runtime, never touches sqlite3
directly except through opsdb.py functions, never invokes the runtime
except through agent_runtime.invoke_agent(). server.py's main() starts
run_poll_loop() as a daemon thread right after startup reconciliation.

THE CENTRAL DECISION (§B.1): the automated Code Review invocation is
zero-tool (--tools "", --strict-mcp-config, unconditional in
agent_runtime._run_claude() regardless of caller — this module cannot,
and does not try to, change that). The diff and file content are
assembled by THIS deterministic Python module, from git's own object
database, and fed directly into the transcript — never real Bash/Read
tool grants for an unsupervised invocation. This is why this module
exists as a distinct, careful surface: it is a genuinely NEW
filesystem/subprocess-touching surface (§B.1.2), driven by data pulled
from the database (`handoffs.files_changed`/`base_commit_sha`/
`head_commit_sha`), not a fixed argv the way agent_runtime.py's own
Popen call already is.

CLAIM-FIRST ORDERING (Red Team's Phase 3A review, RT3 — CRITICAL, stated
here in prose because the whole design's idempotency and
no-infinite-reprocessing properties depend on getting this exactly
right): opsdb.create_automation_event() is called as the VERY FIRST step
for any eligible-looking trigger row, strictly BEFORE the
handoff-existence check, the SHA validity checks, and the file-path
validation — not only before the real model invocation. Every §B.10
fail-closed scenario therefore produces exactly one permanent, claimed,
'skipped' row, never a candidate that was merely looked at and discarded
without a record — without claiming first, a task manually moved to
CODE_REVIEW with no handoff (or a typo'd SHA, or an older pre-Phase-3A
handoff with nothing to validate) would be re-evaluated by the
candidate-finding query on EVERY subsequent POLL_INTERVAL_S cycle,
forever, under entirely non-adversarial conditions. This module extends
that same claim-first principle to the §B.7 per-task/company-wide caps
too (a deliberate, disclosed extension beyond RT3's own literal wording,
which only enumerates the §B.10 scenarios by name) — for the identical
reason: Red Team's NB1 explicitly expects a real automation_events row to
exist for a capped candidate ("outcome='capped'... at no cost beyond the
two call sites already needing to set some outcome value regardless"),
and a cap check performed BEFORE the claim would leave a capped
candidate permanently un-claimed and re-evaluated forever, the exact
infinite-reprocessing defect RT3 fixed for the other scenarios.

PER-CANDIDATE ISOLATION (Security's Phase 3A threat-model review,
required fix C2, and Red Team's RT2 correction of the same pseudocode):
_poll_once()'s per-candidate loop wraps EACH candidate's processing
individually — one candidate's failure marks ITS OWN already-claimed row
failed/skipped with a concrete reason and continues to the next
candidate in the same cycle, never left silently 'running' for
reconcile_stuck_automation_events() to find only at the next server
restart, never aborting the whole cycle's batch.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402
import agent_runtime  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODING_STANDARDS_PATH = REPO_ROOT / "ops" / "CODING_STANDARDS.md"

POLL_INTERVAL_S = 20  # Red Team's Phase 3A review, open question 1: affirmed, no change
_stop_event = threading.Event()

# §B.6/§B.7 — every one of these four caps enforced exactly as specified,
# affirmed by Red Team's Phase 3A review (open question 1): no change.
MAX_CANDIDATES_PER_CYCLE = 5
MAX_AUTOMATED_INVOCATIONS_PER_TASK = 3   # lifetime, across repeated CODE_REVIEW re-entries
MAX_AUTOMATED_TRANSITIONS_PER_TASK = 3   # currently identical in effect — see §B.7's own reasoning:
                                          # this milestone's only automatic transition (REJECT ->
                                          # IN_DEVELOPMENT) happens at most once per automation_events
                                          # row, so today one cap enforces both; kept as a textually
                                          # distinct constant since a future phase could decouple them.
MAX_AUTOMATED_INVOCATIONS_PER_DAY = 20
MAX_AUTOMATION_SPEND_USD_PER_DAY = 10.00
_RESERVED_COST_PER_RUNNING_USD = 0.50  # matches agent_runtime.MAX_BUDGET_USD

MAX_REVIEW_TRANSCRIPT_CHARS = 60_000

AUTOMATION_NOTE_PREFIX = "[Automated, Phase 3A]"

# §B.1/§B.13/Security's required fix C1: SHA format validation, before
# ANY git subprocess call ever touches a caller-supplied SHA.
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

_GIT_TIMEOUT_S = 30.0
_MAX_LOG_CHARS = 2_000  # R5: same truncation agent_runtime.py already applies to stderr_text[:2000]


def _truncate_for_log(text: str) -> str:
    return text[:_MAX_LOG_CHARS]


# ---------------------------------------------------------------- loop ----

def run_poll_loop() -> None:
    """Started as a daemon thread in server.py's main(), right after
    startup reconciliation, before serve_forever(). Stopped via
    _stop_event.set() on shutdown with a short join() — belt-and-
    suspenders on top of httpd.daemon_threads=True, which already
    guarantees this thread can't block process exit even if not joined."""
    while not _stop_event.is_set():
        try:
            _poll_once()
        except Exception as exc:  # noqa: BLE001 — one bad cycle must not kill the whole loop
            sys.stderr.write(
                f"[automation] unhandled error in poll cycle: {type(exc).__name__}: "
                f"{_truncate_for_log(str(exc))}\n"
            )
        _stop_event.wait(POLL_INTERVAL_S)


def _automation_enabled(conn: sqlite3.Connection) -> bool:
    """§B.10 scenario 5: automation_state is unreadable (a real DB error
    mid-read) — treat as disabled, never default to enabled. Same
    fail-closed instinct founder_auth.py's credential-read error handling
    already establishes for this codebase."""
    try:
        row = conn.execute("SELECT enabled FROM automation_state WHERE id = 1").fetchone()
    except sqlite3.Error as exc:
        sys.stderr.write(f"[automation] could not read automation_state — treating as disabled: "
                          f"{type(exc).__name__}: {exc}\n")
        return False
    if row is None:
        return False
    return bool(row["enabled"])


def _find_candidate_history_rows(conn: sqlite3.Connection, limit: int) -> list[sqlite3.Row]:
    """§B.3/§B.10 scenario 1: any task_status_history row with
    to_status='CODE_REVIEW' that has NO automation_events row yet (any
    status — a claimed-and-skipped row still means "already looked at,
    never again"). Ordered oldest-first so an older, longer-waiting
    trigger is processed before a newer one within the per-cycle cap."""
    return conn.execute(
        """
        SELECT tsh.id AS history_id, tsh.task_id
        FROM task_status_history tsh
        WHERE tsh.to_status = 'CODE_REVIEW'
          AND NOT EXISTS (
              SELECT 1 FROM automation_events ae WHERE ae.trigger_status_history_id = tsh.id
          )
        ORDER BY tsh.id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def _poll_once() -> None:
    """One poll cycle. Checked-and-re-checked kill switch (§B.5: "checked
    once at the top of each cycle, and again immediately before claiming a
    candidate"); §B.7's per-cycle batch cap bounds this cycle's own work
    (candidates beyond the cap are simply picked up on a later cycle — no
    row created, no state to mark, per Red Team's NB1)."""
    conn = opsdb.connect()
    try:
        if not _automation_enabled(conn):
            return
        candidates = _find_candidate_history_rows(conn, MAX_CANDIDATES_PER_CYCLE)
    finally:
        conn.close()

    for row in candidates:
        history_id, task_id = row["history_id"], row["task_id"]
        try:
            _process_candidate(history_id, task_id)
        except Exception as exc:  # noqa: BLE001 — one candidate's failure must not abort the batch (Security's C2)
            sys.stderr.write(
                f"[automation] candidate task={task_id} history={history_id} failed: "
                f"{type(exc).__name__}: {_truncate_for_log(str(exc))}\n"
            )
            continue


# ------------------------------------------------------------- claim ------

def _process_candidate(history_id: int, task_id: int) -> None:
    """Claims the trigger row FIRST (RT3), strictly before every §B.10
    eligibility check and every §B.7 cap check below — so every
    eligibility/cap failure still produces exactly one permanent, claimed,
    'skipped' row, and this exact trigger event is genuinely never
    re-evaluated again on a later cycle. From the moment the claim
    succeeds, this function is responsible for ending that event
    (completed/failed/skipped) on EVERY exit path, including an
    unexpected exception — see the try/except wrapping everything after
    the claim, which marks the row failed/error rather than leaving it
    'running' for restart-time reconciliation alone to find."""
    conn = opsdb.connect()
    try:
        # §B.5: re-checked immediately before claiming, closing the narrow
        # window where a cycle is already mid-flight when the Founder
        # clicks Stop.
        if not _automation_enabled(conn):
            return
        event_id = opsdb.create_automation_event(conn, task_id, history_id)
    finally:
        conn.close()

    if event_id is None:
        # Already claimed (idempotency, §B.10 scenario 1) or tasks.status
        # no longer matches CODE_REVIEW (§B.10 scenario 4) — nothing new
        # to do or record.
        return

    try:
        _review_claimed_event(event_id, task_id)
    except Exception as exc:  # noqa: BLE001 — this row must never be left 'running'
        _end_event(event_id, "failed", outcome="error",
                   skip_reason=f"unhandled error: {_truncate_for_log(f'{type(exc).__name__}: {exc}')}")
        raise


def _end_event(event_id: int, status: str, outcome: str | None = None,
                review_result_id: int | None = None, cost_usd: float | None = None,
                truncated: bool = False, skip_reason: str | None = None) -> None:
    conn = opsdb.connect()
    try:
        opsdb.end_automation_event(conn, event_id, status, outcome=outcome,
                                    review_result_id=review_result_id, cost_usd=cost_usd,
                                    truncated=truncated, skip_reason=skip_reason)
    finally:
        conn.close()


def _skip(event_id: int, reason: str, outcome: str | None = None) -> None:
    _end_event(event_id, "skipped", outcome=outcome, skip_reason=reason)


# ------------------------------------------------------- eligibility ------

def _today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _check_task_lifetime_cap(conn: sqlite3.Connection, task_id: int, event_id: int) -> str | None:
    """§B.7 per-task lifetime cap — a task legitimately re-entering
    CODE_REVIEW after a Founder-resumed fix is a genuinely new trigger
    event with its own row, so the per-event UNIQUE constraint alone would
    let automated review repeat indefinitely for the same task; this is
    the actual defense-in-depth answer to that. Counts every OTHER
    automation_events row this task has (any status — a skip still counts
    as "an automatic attempt was made"), excluding the just-claimed
    current row."""
    prior = conn.execute(
        "SELECT COUNT(*) FROM automation_events WHERE task_id = ? AND id != ?",
        (task_id, event_id),
    ).fetchone()[0]
    if prior >= MAX_AUTOMATED_INVOCATIONS_PER_TASK:
        return "per-task automated-invocation cap reached — needs manual review"
    return None


def _check_daily_invocation_cap(conn: sqlite3.Connection, event_id: int) -> str | None:
    """§B.7 company-wide daily cap — a final defense-in-depth ceiling,
    independent of the spend ceiling below (a cheap invocation hitting a
    count-based loop before it ever gets expensive enough to trip the
    dollar ceiling is still worth catching). Counts events that actually
    reached (or are reaching) a real invocation today — status='skipped'
    rows never did, so they don't count against this cap."""
    today = _today_prefix()
    count = conn.execute(
        "SELECT COUNT(*) FROM automation_events "
        "WHERE id != ? AND status != 'skipped' AND started_at LIKE ?",
        (event_id, today + "%"),
    ).fetchone()[0]
    if count >= MAX_AUTOMATED_INVOCATIONS_PER_DAY:
        return "daily automated-invocation count ceiling reached"
    return None


def _check_daily_spend_cap(conn: sqlite3.Connection, event_id: int) -> str | None:
    """§B.6 — sums automation_events.cost_usd for rows started today, plus
    a worst-case $0.50 reservation for every row currently status='running'
    today (this event's own row is already inserted status='running' at
    this point, so its own reservation is counted exactly once here, not
    doubled) — if the total would exceed the daily ceiling, skip."""
    today = _today_prefix()
    spent = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0) FROM automation_events "
        "WHERE id != ? AND started_at LIKE ?",
        (event_id, today + "%"),
    ).fetchone()[0]
    running = conn.execute(
        "SELECT COUNT(*) FROM automation_events WHERE status = 'running' AND started_at LIKE ?",
        (today + "%",),
    ).fetchone()[0]
    if spent + running * _RESERVED_COST_PER_RUNNING_USD > MAX_AUTOMATION_SPEND_USD_PER_DAY:
        return "daily automation spend ceiling reached"
    return None


def _commit_exists(sha: str) -> bool:
    """Security's required fix C1: confirms a SHA resolves to a real
    commit object in THIS repository before it is trusted for a diff —
    `git cat-file -e <sha>^{commit}` is a read-only existence check, no
    output. `--` before the object argument is accepted by cat-file and
    costs nothing (defense-in-depth, though this argument can never be
    mistaken for an option — it is only ever called after _SHA_RE has
    already confirmed it's pure lowercase hex)."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", "--", f"{sha}^{{commit}}"],
            cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[automation] git cat-file failed for {sha!r}: {type(exc).__name__}: {exc}\n")
        return False
    return result.returncode == 0


def _validate_repo_path(rel_path: str) -> bool:
    """§B.1.2's required path validation, exactly: reject absolute paths,
    reject anything where Path(repo_root, path).resolve() does not remain
    inside repo_root, reject a '..' component after normalization
    (redundant with resolve() but cheap, per the doc). Any exception while
    normalizing (e.g. an embedded null byte, which Python's own stdlib
    raises ValueError on immediately — Security's required fix C2's
    concern about a malformed candidate) is treated as an invalid path,
    not allowed to propagate uncaught."""
    try:
        p = Path(rel_path)
        if p.is_absolute():
            return False
        if any(part == ".." for part in p.parts):
            return False
        resolved = (REPO_ROOT / rel_path).resolve()
        resolved.relative_to(REPO_ROOT.resolve())
    except (ValueError, OSError):
        return False
    return True


def _review_claimed_event(event_id: int, task_id: int) -> None:
    """Everything after the claim: §B.10 eligibility checks (handoff, SHA,
    paths) -> §B.7 caps -> transcript assembly -> the real, zero-tool
    invocation -> §B.1.1/§B.8 verdict handling. Every expected fail-closed
    or capped outcome ends the event and returns NORMALLY (never raises) —
    only a genuinely unexpected bug should propagate to
    _process_candidate()'s own outer try/except."""
    conn = opsdb.connect()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        handoff_row = conn.execute(
            "SELECT * FROM handoffs WHERE task_id = ? AND from_agent = 'developer' "
            "AND to_agent = 'code-review' ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()

    # §B.10 scenario 2.
    if handoff_row is None:
        _skip(event_id, "no completed Developer handoff found")
        return

    base_sha = handoff_row["base_commit_sha"]
    head_sha = handoff_row["head_commit_sha"]

    # §B.10 scenario 3.
    if not base_sha or not head_sha:
        _skip(event_id, "handoff missing base/head commit — cannot assemble a diff automatically")
        return

    # Security's required fix C1 / §B.10 scenario 8 (new, added by that
    # fix): format validation BEFORE any git subprocess call, then
    # existence validation.
    if not (_SHA_RE.match(base_sha) and _SHA_RE.match(head_sha)):
        _skip(event_id, "recorded base/head SHA does not resolve to a real commit in this repository")
        return
    if not (_commit_exists(base_sha) and _commit_exists(head_sha)):
        _skip(event_id, "recorded base/head SHA does not resolve to a real commit in this repository")
        return

    # §B.1.2 / §B.10 scenario 6: every files_changed entry validated; ANY
    # failing entry fails the WHOLE candidate closed, never a silent
    # partial file set.
    try:
        files_changed = json.loads(handoff_row["files_changed"] or "[]")
    except (json.JSONDecodeError, TypeError):
        files_changed = None
    if not isinstance(files_changed, list) or not files_changed:
        sys.stderr.write(f"[automation] task={task_id}: handoff has no usable files_changed list\n")
        _skip(event_id, "invalid file path in handoff — see server log")
        return
    validated_paths: list[str] = []
    for entry in files_changed:
        if not isinstance(entry, str) or not _validate_repo_path(entry):
            sys.stderr.write(f"[automation] task={task_id}: rejected file path in handoff: {entry!r}\n")
            _skip(event_id, "invalid file path in handoff — see server log")
            return
        validated_paths.append(entry)

    # §B.7 caps — claimed first, same reasoning as every check above (see
    # module docstring's "CLAIM-FIRST ORDERING" note for why this is
    # deliberately extended beyond RT3's literal §B.10 scope).
    conn = opsdb.connect()
    try:
        cap_reason = _check_task_lifetime_cap(conn, task_id, event_id)
        if cap_reason is None:
            cap_reason = _check_daily_invocation_cap(conn, event_id)
        if cap_reason is None:
            cap_reason = _check_daily_spend_cap(conn, event_id)
    finally:
        conn.close()
    if cap_reason is not None:
        _skip(event_id, cap_reason, outcome="capped")
        return

    transcript, truncated = _assemble_transcript(task_row, handoff_row, base_sha, head_sha, validated_paths)

    _invoke_and_record(event_id, task_id, transcript, truncated)


# --------------------------------------------------------- transcript -----

def _git_diff(base_sha: str, head_sha: str, paths: list[str]) -> str:
    """Fixed argv, never a shell string (same injection-safety convention
    agent_runtime.py's own Popen call already established). `--` separates
    the two revision arguments from the pathspec arguments that follow
    (Security's required fix C1)."""
    cmd = ["git", "--no-pager", "diff", "--no-color", base_sha, head_sha, "--", *paths]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[automation] git diff failed: {type(exc).__name__}: {exc}\n")
        return "(git diff could not be computed)"
    if result.returncode != 0:
        sys.stderr.write(f"[automation] git diff exited {result.returncode}: "
                          f"{_truncate_for_log(result.stderr.decode('utf-8', errors='replace'))}\n")
        return "(git diff could not be computed)"
    return result.stdout.decode("utf-8", errors="replace")


def _git_show_file(head_sha: str, path: str) -> str | None:
    """Correction (Security's Phase 3A threat-model review, R1): retrieves
    the file's committed content from git's OWN OBJECT DATABASE
    (`git show <sha>:<path>`), never a live filesystem read of the working
    tree (Path(...).read_text()) — closes a working-tree symlink/TOCTOU
    exposure more robustly than path validation alone: git never touches a
    filesystem symlink at this path when resolving a tree object.

    Deliberately NOT given a `--` separator before the combined
    `<sha>:<path>` object argument — verified empirically that `git show
    -- <sha>:<path>` silently treats the whole string as a PATHSPEC
    instead of an object reference (no revision precedes `--`, so `git
    show` defaults to HEAD and then filters by a pathspec that never
    matches, returning an empty result with exit code 0 — a silent,
    wrong-content failure, not a loud one). This form is safe without `--`
    regardless: the argument always begins with `head_sha`, which
    `_SHA_RE`/`_commit_exists()` have already confirmed is pure lowercase
    hex — it can never be misread as a `-`-prefixed option."""
    cmd = ["git", "--no-pager", "show", f"{head_sha}:{path}"]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[automation] git show failed for {path!r}: {type(exc).__name__}: {exc}\n")
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def _read_coding_standards() -> str:
    try:
        return CODING_STANDARDS_PATH.read_text()
    except OSError as exc:
        sys.stderr.write(f"[automation] could not read CODING_STANDARDS.md: {type(exc).__name__}: {exc}\n")
        return "(CODING_STANDARDS.md could not be read)"


def _assemble_transcript(task_row: sqlite3.Row, handoff_row: sqlite3.Row, base_sha: str, head_sha: str,
                          paths: list[str]) -> tuple[str, bool]:
    """§B.1's bullet list, assembled by deterministic Python — never real
    tool grants for the (unsupervised) invocation this feeds. Graceful,
    disclosed truncation at MAX_REVIEW_TRANSCRIPT_CHARS if exceeded — the
    instructions block (including the truncation notice, when present) is
    appended AFTER truncation, so the model always receives the real
    VERDICT: instruction regardless of how much content had to be cut."""
    parts: list[str] = []
    parts.append(f"TASK-{task_row['id']:03d}: {task_row['title']}")
    if task_row["business_goal"]:
        parts.append(f"Business goal: {task_row['business_goal']}")
    if task_row["acceptance_criteria"]:
        parts.append(f"Acceptance criteria: {task_row['acceptance_criteria']}")
    if task_row["architecture_notes"]:
        parts.append(f"Architecture notes: {task_row['architecture_notes']}")
    if task_row["tests_required"]:
        parts.append(f"Tests required: {task_row['tests_required']}")

    parts.append("")
    parts.append("Developer's handoff record:")
    if handoff_row["work_completed"]:
        parts.append(f"Work completed: {handoff_row['work_completed']}")
    parts.append(f"Files changed: {handoff_row['files_changed']}")
    if handoff_row["tests_added"]:
        parts.append(f"Tests added: {handoff_row['tests_added']}")
    if handoff_row["expected_behavior"]:
        parts.append(f"Expected behavior: {handoff_row['expected_behavior']}")
    if handoff_row["known_limitations"]:
        parts.append(f"Known limitations: {handoff_row['known_limitations']}")

    parts.append("")
    parts.append(f"git diff {base_sha}..{head_sha} (scoped to files_changed):")
    parts.append(_git_diff(base_sha, head_sha, paths))

    parts.append("")
    parts.append("Full final content of every changed/added file "
                  "(retrieved via `git show <head_sha>:<path>` — the committed object, never a working-tree read):")
    for path in paths:
        content = _git_show_file(head_sha, path)
        parts.append(f"--- {path} ---")
        parts.append(content if content is not None else "(could not retrieve this file's content from the commit)")

    parts.append("")
    parts.append("CODING_STANDARDS.md (verbatim):")
    parts.append(_read_coding_standards())

    content = "\n".join(parts)
    truncated = len(content) > MAX_REVIEW_TRANSCRIPT_CHARS
    if truncated:
        content = content[:MAX_REVIEW_TRANSCRIPT_CHARS] + "\n\n[content truncated at 60,000 characters]"

    truncation_note = (
        "\n\nNOTE: the content above was truncated to fit this automated review's size limit — you do "
        "not have the complete picture. Per your role doc's automated-invocation note, a truncated "
        "transcript must not receive VERDICT: PASS.\n"
        if truncated else ""
    )
    instructions = (
        "\n\nYou are reviewing this in AUTOMATED mode — a narrower context than a human-supervised "
        "session (see your role doc's automated-invocation note for exactly what this means and what "
        "it structurally cannot catch). Give your real findings, then end your entire reply with, as "
        "the STRICTLY LAST non-blank line, exactly one of:\nVERDICT: PASS\nVERDICT: REJECT"
        f"{truncation_note}"
    )
    return content + instructions, truncated


# ---------------------------------------------------------- invocation ----

_VERDICT_LINE_RE = re.compile(r"^VERDICT:\s*(PASS|REJECT)\s*$", re.IGNORECASE)


def _parse_verdict(reply_text: str | None) -> str | None:
    """Correction (Red Team's Phase 3A review, required fix RT2 — CRITICAL):
    the VERDICT: line must be the STRICTLY LAST non-blank line of the
    reply, and ONLY that line is parsed. This document's original design
    specified reusing meeting_orchestrator._parse_synthesis()'s own
    label-anchored, whole-reply scan — genuinely unsafe for a single
    binary label: a model explaining a REJECT verdict has every natural,
    benign reason to mention the other value earlier in its own reasoning
    (e.g. "Normally this would warrant VERDICT: PASS, but because the
    diff duplicates an existing scoping predicate, my actual conclusion is
    VERDICT: REJECT") — a whole-reply scan can silently select the WRONG
    verdict from prose like this, with no error and no signal. Returns
    'pass'/'reject', or None for a PARSE FAILURE (no match, or a VERDICT:
    token anywhere other than the exact final non-blank line) — callers
    MUST treat None as a fourth, distinct outcome from the three
    error_kind invocation-failure cases, never a guessed default."""
    if not reply_text:
        return None
    lines = [ln for ln in reply_text.splitlines() if ln.strip()]
    if not lines:
        return None
    m = _VERDICT_LINE_RE.match(lines[-1].strip())
    if not m:
        return None
    return m.group(1).lower()


def _invoke_and_record(event_id: int, task_id: int, transcript: str, truncated: bool) -> None:
    """The real, zero-tool `code-review` invocation, and every one of
    §B.8's four outcomes (pass / reject / invocation failure / RT2's new
    parse-failure case). agent_runs is still given a row for consistency
    (§B.3.1) even though the routing decision around the invocation is
    pure Python, attributed to `orchestrator` elsewhere — the invocation
    itself is real, attributed to `code-review`, exactly like every other
    Code Review session. No lock/connection is ever held across the
    invocation itself (same discipline server.py's own _handle_ask()
    already follows)."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_run(conn, "code-review", "task",
                                  agent_runtime.AUTOMATED_CODE_REVIEW_ACTIVITY_LABEL, scope_id=task_id)
    finally:
        conn.close()

    result = agent_runtime.invoke_agent("code-review", transcript,
                                         timeout_s=agent_runtime.AUTOMATED_REVIEW_TIMEOUT_S)

    if not result.ok:
        sys.stderr.write(
            f"[automation] task={task_id}: automated Code Review invocation failed "
            f"({result.error_kind}): {_truncate_for_log(result.error or '')}\n"
        )
        conn = opsdb.connect()
        try:
            opsdb.end_run(conn, run_id, "failed")
        finally:
            conn.close()
        # §B.8: no review_results row fabricated from a call that didn't
        # actually produce one.
        _end_event(event_id, "failed", outcome="error", cost_usd=result.cost_usd, truncated=truncated,
                   skip_reason=f"invocation failed ({result.error_kind})")
        return

    verdict = _parse_verdict(result.response_text)
    if verdict is None:
        # RT2's new, fourth §B.8 case: a successful invocation with an
        # unparseable verdict — treated identically to an invocation
        # failure. No review_results row fabricated, never automatically
        # retried (the UNIQUE constraint already prevents re-claiming this
        # trigger event).
        sys.stderr.write(
            f"[automation] task={task_id}: automated Code Review reply had no VERDICT: line as the "
            f"strictly-last non-blank line — parse failure, not a guess\n"
        )
        conn = opsdb.connect()
        try:
            opsdb.end_run(conn, run_id, "failed")
        finally:
            conn.close()
        _end_event(event_id, "failed", outcome="error", cost_usd=result.cost_usd, truncated=truncated,
                   skip_reason="automated review reply had no parseable VERDICT: line")
        return

    findings = [result.response_text or ""]
    conn = opsdb.connect()
    try:
        opsdb.end_run(conn, run_id, "ended")
        if verdict == "pass":
            # §B.8: tasks.status is left UNCHANGED at CODE_REVIEW — no
            # automatic advance to QA, per the Founder's explicit
            # instruction. reviewed_by_agent is still "code-review" —
            # automation_events.review_result_id is what distinguishes an
            # automated session from a human-supervised one, not a change
            # to the shared review_results table's shape.
            review_id = opsdb.record_review_result(conn, task_id, "code", "code-review", "pass",
                                                     findings=findings)
            opsdb.end_automation_event(conn, event_id, "completed", outcome="pass",
                                        review_result_id=review_id, cost_usd=result.cost_usd,
                                        truncated=truncated)
        else:
            # §B.8: a single, mechanical tasks.status transition — pure
            # bookkeeping, NEVER a new Developer model invocation.
            review_id = opsdb.record_review_result(conn, task_id, "code", "code-review", "reject",
                                                     findings=findings, returned_to="developer")
            opsdb.record_task_status(
                conn, task_id, "IN_DEVELOPMENT", changed_by_agent="orchestrator",
                note=f"{AUTOMATION_NOTE_PREFIX} Code Review rejected — routed back to Developer "
                     f"(automation_events id={event_id}).",
            )
            opsdb.end_automation_event(conn, event_id, "completed", outcome="reject",
                                        review_result_id=review_id, cost_usd=result.cost_usd,
                                        truncated=truncated)
    finally:
        conn.close()
