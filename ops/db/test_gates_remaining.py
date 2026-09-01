#!/usr/bin/env python3
"""ops/db/test_gates_remaining.py — Milestone A (TASK-019) regression check.

Per Red Team's required fix (ops/reviews/red-team-milestone-a-review.md
§1.4/§5.2): reproduces, against a scratch database (never the live one —
see ops/db/README.md), the two real cases Red Team found and fixed:

1. TASK-19's own real history: BACKLOG -> ARCHITECTURE -> MOCKUP_REVIEW
   (a backward transition through GATE_STATUS_ORDER, index 3 -> index 2).
2. TASK-6's real history: ... -> SECURITY_REVIEW -> CODE_REVIEW (an
   ordinary Security-reject-and-rework bounce, index 9 -> index 7).

Both must show zero overlap between gates_completed() and
gates_remaining() once the fix (gates_remaining(effective_status,
completed) filtering by the completed set) is applied. This is the
"regression check (unit test or equivalent)" Red Team's §5, item 2
requires before Code Review.

Extended for the round-3 QA defect (qa_results id=68, see
ops/db/derived_state.py's gates_completed() docstring, bug-history item
2): gates_completed() previously judged EVERY historical entry into a
gate, not just its most recent one, so a gate exited-then-RE-ENTERED
(a reject/resubmit loop landing back in the identical gate — ordinary
expected workflow, not a rare edge case) could be wrongly marked
"completed" from a stale earlier visit while the task is actually
sitting live in that same gate right now. Cases 4-6 below cover this:
TASK-19's own real Code Review reject-then-resubmit history (the exact
case QA reproduced), a synthetic three-round bounce through the same
gate shaped after TASK-17's real three-round Red Team review history
(review_results ids 49-51: reject, reject, pass — task_status_history
itself never left RED_TEAM_REVIEW for those three rounds, so this case
is a shaped reproduction, not a literal replay, consistent with how
Case 3 below already treats TASK-17), and a task that bounces through
two DIFFERENT gates and returns to both.

Usage:
    OPSDB_PATH=/tmp/test-gates-remaining.sqlite3 python3 ops/db/test_gates_remaining.py

(Or simply `python3 ops/db/test_gates_remaining.py` — it sets its own
scratch OPSDB_PATH under the process's tempdir if the caller didn't.)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("OPSDB_PATH"):
    _scratch = Path(tempfile.mkdtemp(prefix="opsdb-test-gates-")) / "scratch.sqlite3"
    os.environ["OPSDB_PATH"] = str(_scratch)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testing_guard  # noqa: F401,E402 — raises if OPSDB_PATH isn't a scratch path
import opsdb  # noqa: E402
import derived_state as ds  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def make_task(conn, title: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, current_owner) VALUES (?, 'test')", (title,)
        )
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, "
            "changed_by_agent, note) VALUES (?, NULL, 'BACKLOG', 'test', 'created')",
            (task_id,),
        )
    return task_id


def replay(conn, task_id: int, transitions: list[str]) -> None:
    for to_status in transitions:
        opsdb.record_task_status(conn, task_id, to_status, "test")


def main() -> int:
    # require_exists=False: this scratch file doesn't exist yet — same as
    # `opsdb.py init` itself (cmd_init calls connect(require_exists=False)).
    conn = opsdb.connect(require_exists=False)
    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text()
    conn.executescript(schema_sql)
    ds_conn = conn  # same connection; row_factory already set by opsdb.connect()

    # ---- Case 1: TASK-19's real history — BACKLOG -> ARCHITECTURE -> MOCKUP_REVIEW ----
    t19 = make_task(conn, "TASK-19 reproduction: Milestone A gate model")
    replay(conn, t19, ["ARCHITECTURE", "MOCKUP_REVIEW"])
    # State: currently sitting at MOCKUP_REVIEW, having forward-exited ARCHITECTURE.
    status = conn.execute("SELECT status FROM tasks WHERE id = ?", (t19,)).fetchone()["status"]
    check("TASK-19 repro: tasks.status is MOCKUP_REVIEW", status == "MOCKUP_REVIEW", status)

    effective = ds.effective_gate_status(ds_conn, t19, status)
    completed = ds.gates_completed(ds_conn, t19)
    remaining = ds.gates_remaining(effective, completed)
    check("TASK-19 repro: effective_gate_status == MOCKUP_REVIEW", effective == "MOCKUP_REVIEW", str(effective))
    check("TASK-19 repro: ARCHITECTURE is in gates_completed()", "ARCHITECTURE" in completed, str(completed))
    check("TASK-19 repro: ARCHITECTURE is NOT in gates_remaining() (Red Team fix)",
          "ARCHITECTURE" not in remaining, str(remaining))
    check("TASK-19 repro: zero overlap between completed and remaining",
          not (set(completed) & set(remaining)),
          f"completed={completed} remaining={remaining}")

    # ---- Case 2: TASK-6's real history — ... SECURITY_REVIEW -> CODE_REVIEW bounce ----
    t6 = make_task(conn, "TASK-6 reproduction: Security-reject rework bounce")
    replay(conn, t6, [
        "ARCHITECTURE", "RED_TEAM_REVIEW", "READY_FOR_DEVELOPMENT", "IN_DEVELOPMENT",
        "CODE_REVIEW", "QA", "SECURITY_REVIEW", "CODE_REVIEW",
    ])
    status6 = conn.execute("SELECT status FROM tasks WHERE id = ?", (t6,)).fetchone()["status"]
    check("TASK-6 repro: tasks.status is CODE_REVIEW (post-bounce)", status6 == "CODE_REVIEW", status6)

    effective6 = ds.effective_gate_status(ds_conn, t6, status6)
    completed6 = ds.gates_completed(ds_conn, t6)
    remaining6 = ds.gates_remaining(effective6, completed6)
    check("TASK-6 repro: effective_gate_status == CODE_REVIEW", effective6 == "CODE_REVIEW", str(effective6))
    check("TASK-6 repro: QA is in gates_completed()", "QA" in completed6, str(completed6))
    check("TASK-6 repro: SECURITY_REVIEW is in gates_completed()", "SECURITY_REVIEW" in completed6, str(completed6))
    check("TASK-6 repro: QA is NOT in gates_remaining() (Red Team fix)",
          "QA" not in remaining6, str(remaining6))
    check("TASK-6 repro: SECURITY_REVIEW is NOT in gates_remaining() (Red Team fix)",
          "SECURITY_REVIEW" not in remaining6, str(remaining6))
    check("TASK-6 repro: zero overlap between completed and remaining",
          not (set(completed6) & set(remaining6)),
          f"completed={completed6} remaining={remaining6}")

    # ---- Sanity check: task_progress_row() composes both correctly, end-to-end ----
    row19 = ds.task_progress_row(ds_conn, t19)
    check("TASK-19 repro: task_progress_row() has zero completed/remaining overlap",
          not (set(row19["gates_completed"]) & set(row19["gates_remaining"])),
          str(row19))
    row6 = ds.task_progress_row(ds_conn, t6)
    check("TASK-6 repro: task_progress_row() has zero completed/remaining overlap",
          not (set(row6["gates_completed"]) & set(row6["gates_remaining"])),
          str(row6))

    # ---- Case 3: TASK-17's real history — BLOCKED must NOT count IN_DEVELOPMENT
    # as "completed" (a corrected bug in the architecture doc's own literal
    # SQL sketch, found while implementing — see gates_completed()'s docstring). ----
    t17 = make_task(conn, "TASK-17 reproduction: BLOCKED mid-Development")
    replay(conn, t17, [
        "ARCHITECTURE", "RED_TEAM_REVIEW", "IN_DEVELOPMENT", "BLOCKED",
    ])
    status17 = conn.execute("SELECT status FROM tasks WHERE id = ?", (t17,)).fetchone()["status"]
    check("TASK-17 repro: tasks.status is BLOCKED", status17 == "BLOCKED", status17)
    effective17 = ds.effective_gate_status(ds_conn, t17, status17)
    completed17 = ds.gates_completed(ds_conn, t17)
    check("TASK-17 repro: effective_gate_status walks back to IN_DEVELOPMENT",
          effective17 == "IN_DEVELOPMENT", str(effective17))
    check("TASK-17 repro: IN_DEVELOPMENT is NOT in gates_completed() (still sitting on it, just paused)",
          "IN_DEVELOPMENT" not in completed17, str(completed17))
    check("TASK-17 repro: ARCHITECTURE and RED_TEAM_REVIEW ARE in gates_completed()",
          {"ARCHITECTURE", "RED_TEAM_REVIEW"} <= set(completed17), str(completed17))
    check("TASK-17 repro: gates_completed() == 2 (matches CTO's own Part 5 worked example exactly)",
          completed17 == ["ARCHITECTURE", "RED_TEAM_REVIEW"], str(completed17))

    # ---- Case 4: TASK-19's own real Code Review reject-then-resubmit
    # history (qa_results id=68 -- the exact live reproduction QA found).
    # Real task_status_history rows 135-141: ARCHITECTURE -> MOCKUP_REVIEW
    # -> RED_TEAM_REVIEW -> IN_DEVELOPMENT -> CODE_REVIEW -> (reject)
    # IN_DEVELOPMENT -> (resubmit) CODE_REVIEW. Task is CURRENTLY sitting
    # in CODE_REVIEW for the second time -- it must show as CURRENT, never
    # DONE, even though CODE_REVIEW was entered-and-exited once already. ----
    t19b = make_task(conn, "TASK-19 repro: real Code Review reject-then-resubmit")
    replay(conn, t19b, [
        "ARCHITECTURE", "MOCKUP_REVIEW", "RED_TEAM_REVIEW", "IN_DEVELOPMENT",
        "CODE_REVIEW", "IN_DEVELOPMENT", "CODE_REVIEW",
    ])
    status19b = conn.execute("SELECT status FROM tasks WHERE id = ?", (t19b,)).fetchone()["status"]
    check("TASK-19 CR-reentry repro: tasks.status is CODE_REVIEW (post-resubmit)",
          status19b == "CODE_REVIEW", status19b)
    effective19b = ds.effective_gate_status(ds_conn, t19b, status19b)
    completed19b = ds.gates_completed(ds_conn, t19b)
    remaining19b = ds.gates_remaining(effective19b, completed19b)
    check("TASK-19 CR-reentry repro: effective_gate_status == CODE_REVIEW",
          effective19b == "CODE_REVIEW", str(effective19b))
    check("TASK-19 CR-reentry repro: CODE_REVIEW is NOT in gates_completed() "
          "(it's the task's live, current gate, not a stale earlier visit)",
          "CODE_REVIEW" not in completed19b, str(completed19b))
    check("TASK-19 CR-reentry repro: IN_DEVELOPMENT IS in gates_completed() "
          "(genuinely forward-exited on its second, most recent entry)",
          "IN_DEVELOPMENT" in completed19b, str(completed19b))
    check("TASK-19 CR-reentry repro: ARCHITECTURE/MOCKUP_REVIEW/RED_TEAM_REVIEW "
          "ARE in gates_completed()",
          {"ARCHITECTURE", "MOCKUP_REVIEW", "RED_TEAM_REVIEW"} <= set(completed19b),
          str(completed19b))
    check("TASK-19 CR-reentry repro: zero overlap between completed and remaining",
          not (set(completed19b) & set(remaining19b)),
          f"completed={completed19b} remaining={remaining19b}")

    # ---- Case 5: synthetic three-round bounce through the SAME gate,
    # shaped after TASK-17's real three-round Red Team review history
    # (review_results ids 49 reject, 50 reject, 51 pass -- task_status_history
    # itself stayed in RED_TEAM_REVIEW for all three real rounds, so this
    # case models what a three-round bounce looks like when the gate IS
    # re-entered via task_status_history, generalizing case 4 beyond a
    # single bounce). ----
    t17b = make_task(conn, "TASK-17-shaped repro: three-round bounce through same gate")
    replay(conn, t17b, [
        "ARCHITECTURE", "RED_TEAM_REVIEW", "IN_DEVELOPMENT",
        "RED_TEAM_REVIEW", "IN_DEVELOPMENT",
        "RED_TEAM_REVIEW", "IN_DEVELOPMENT", "CODE_REVIEW",
    ])
    status17b = conn.execute("SELECT status FROM tasks WHERE id = ?", (t17b,)).fetchone()["status"]
    check("Three-round repro: tasks.status is CODE_REVIEW", status17b == "CODE_REVIEW", status17b)
    effective17b = ds.effective_gate_status(ds_conn, t17b, status17b)
    completed17b = ds.gates_completed(ds_conn, t17b)
    remaining17b = ds.gates_remaining(effective17b, completed17b)
    check("Three-round repro: RED_TEAM_REVIEW IS in gates_completed() "
          "(finally forward-exited on its third, most recent entry)",
          "RED_TEAM_REVIEW" in completed17b, str(completed17b))
    check("Three-round repro: IN_DEVELOPMENT IS in gates_completed() "
          "(forward-exited on its third, most recent entry)",
          "IN_DEVELOPMENT" in completed17b, str(completed17b))
    check("Three-round repro: CODE_REVIEW (current) is NOT in gates_completed()",
          "CODE_REVIEW" not in completed17b, str(completed17b))
    check("Three-round repro: zero overlap between completed and remaining",
          not (set(completed17b) & set(remaining17b)),
          f"completed={completed17b} remaining={remaining17b}")

    # ---- Case 6: bounces through TWO different gates and returns to both
    # (Security REJECT sends the task back through Code Review AND QA a
    # second time before finally clearing Security Review) -- the general
    # form the fix must handle, not just a single-gate bounce. ----
    t_double = make_task(conn, "Double-gate repro: bounces through CODE_REVIEW and QA twice each")
    replay(conn, t_double, [
        "ARCHITECTURE", "RED_TEAM_REVIEW", "READY_FOR_DEVELOPMENT", "IN_DEVELOPMENT",
        "CODE_REVIEW", "QA", "SECURITY_REVIEW",
        "CODE_REVIEW", "QA", "SECURITY_REVIEW",
        "READY_TO_RELEASE",
    ])
    status_double = conn.execute("SELECT status FROM tasks WHERE id = ?", (t_double,)).fetchone()["status"]
    check("Double-gate repro: tasks.status is READY_TO_RELEASE", status_double == "READY_TO_RELEASE", status_double)
    effective_double = ds.effective_gate_status(ds_conn, t_double, status_double)
    completed_double = ds.gates_completed(ds_conn, t_double)
    remaining_double = ds.gates_remaining(effective_double, completed_double)
    check("Double-gate repro: CODE_REVIEW, QA, SECURITY_REVIEW ARE all in gates_completed() "
          "(each genuinely forward-exited on its own most recent entry)",
          {"CODE_REVIEW", "QA", "SECURITY_REVIEW"} <= set(completed_double), str(completed_double))
    check("Double-gate repro: READY_TO_RELEASE (current) is NOT in gates_completed()",
          "READY_TO_RELEASE" not in completed_double, str(completed_double))
    check("Double-gate repro: zero overlap between completed and remaining",
          not (set(completed_double) & set(remaining_double)),
          f"completed={completed_double} remaining={remaining_double}")

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
