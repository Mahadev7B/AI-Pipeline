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

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
