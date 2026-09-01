#!/usr/bin/env python3
"""ops/db/test_phase_progress.py — Milestone D (TASK-022) regression check.

Reproduces, against a scratch database (never the live one — see
ops/db/README.md), the cases this milestone's architecture (CTO,
ops/reviews/cto-milestone-d-architecture.md) and Design (ops/reviews/
design-review-milestone-d.md) reviews both care about:

1. `opsdb.py phase-add`/`phase-set-status`'s validation discipline: a
   bad `--parent-id` is rejected with a clean error before any write
   (mirrors `risk-add`'s own scope-validation discipline, Part 6); a bad
   `--opened-decision-id`/`--task-id` is rejected by the real FK
   constraint; `phase-set-status`'s COALESCE-preserves-unless-supplied
   shape (same as `risk-resolve`); lookup by `--name` as well as `--id`.
2. `derived_state.phase_progress_rows()`: `sort_order` ordering and the
   decision/task LEFT JOINs resolving real values, honest NULL when
   absent.
3. `derived_state.founder_readiness_summary()`: both booleans computed
   live from the four Milestone A-D rows, never hardcoded — including
   the case where the `phases` table hasn't been backfilled at all
   (missing rows must not read as "complete").
4. `generate_progress._in_flight_rows()`: filters out tasks already
   reachable via a `phases.task_id` (Part 4.4/Design review §5's shared
   list), so Milestone D's own task never appears as a duplicate
   "needs attention" chip next to itself.

Usage:
    OPSDB_PATH=/tmp/test-phase-progress.sqlite3 python3 ops/db/test_phase_progress.py

(Or simply `python3 ops/db/test_phase_progress.py` — it sets its own
scratch OPSDB_PATH under the process's tempdir if the caller didn't.)
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("OPSDB_PATH"):
    _scratch = Path(tempfile.mkdtemp(prefix="opsdb-test-phases-")) / "scratch.sqlite3"
    os.environ["OPSDB_PATH"] = str(_scratch)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testing_guard  # noqa: F401,E402 — raises if OPSDB_PATH isn't a scratch path
import opsdb  # noqa: E402
import derived_state as ds  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "control-center"))

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def _task(conn, title: str, status: str = "DONE") -> int:
    with conn:
        cur = conn.execute("INSERT INTO tasks (title, status) VALUES (?, ?)", (title, status))
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, changed_by_agent, note) "
            "VALUES (?, NULL, ?, 'test', 'created')",
            (cur.lastrowid, status),
        )
    return cur.lastrowid


def _decision(conn, title: str) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO decisions (title, date, decision, recommending_agent) VALUES (?, '2026-09-01', 'x', 'cto')",
            (title,),
        )
    return cur.lastrowid


def _phase_add_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "name": None, "status": None, "sort_order": None, "parent_phase_id": None,
        "opened_decision_id": None, "closed_decision_id": None, "task_id": None,
        "milestones_total": None, "milestones_complete": None, "note": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _phase_set_status_args(**kwargs) -> argparse.Namespace:
    defaults = {
        "phase_id": None, "phase_name": None, "status": None,
        "closed_decision_id": None, "milestones_complete": None, "note": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def main() -> int:
    conn = opsdb.connect(require_exists=False)
    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text()
    conn.executescript(schema_sql)
    conn.commit()

    # ---- Case 0: founder_readiness_summary() on an unbackfilled table ----
    summary_empty = ds.founder_readiness_summary(conn)
    check("founder_readiness_summary(): empty phases table reads as not ready, never fabricated 'complete'",
          summary_empty == {"exploratory_testing_ready": False, "ui_100pct_complete": False,
                             "milestones_done": 0, "milestones_total": 4},
          str(summary_empty))

    # ---- Case 1: phase-add validation ----
    opsdb.cmd_phase_add(_phase_add_args(name="Phase 0", status="complete", sort_order=10))
    phase0_id = conn.execute("SELECT id FROM phases WHERE name='Phase 0'").fetchone()["id"]

    try:
        opsdb.cmd_phase_add(_phase_add_args(name="Bad parent", status="not_started", sort_order=99, parent_phase_id=9999))
        check("phase-add: bad --parent-id rejected with a clean error", False, "did not raise")
    except SystemExit as exc:
        check("phase-add: bad --parent-id rejected with a clean error", "no phases row with id=9999" in str(exc), str(exc))

    import sqlite3
    try:
        opsdb.cmd_phase_add(_phase_add_args(name="Bad decision", status="not_started", sort_order=98, opened_decision_id=9999))
        check("phase-add: bad --opened-decision-id rejected by the real FK constraint", False, "did not raise")
    except sqlite3.IntegrityError:
        check("phase-add: bad --opened-decision-id rejected by the real FK constraint", True)

    opsdb.cmd_phase_add(_phase_add_args(name="Phase 3", status="in_progress", sort_order=40))
    phase3_id = conn.execute("SELECT id FROM phases WHERE name='Phase 3'").fetchone()["id"]
    dec_a = _decision(conn, "Decision A")
    task_a = _task(conn, "Milestone A task", status="DONE")
    opsdb.cmd_phase_add(_phase_add_args(
        name="Milestone A", status="complete", sort_order=421,
        parent_phase_id=phase3_id, task_id=task_a, opened_decision_id=dec_a,
    ))
    milestone_a_id = conn.execute("SELECT id FROM phases WHERE name='Milestone A'").fetchone()["id"]

    # ---- Case 2: phase-set-status by --name and by --id, COALESCE shape ----
    opsdb.cmd_phase_set_status(_phase_set_status_args(phase_name="Milestone A", status="paused", note="halted"))
    row = conn.execute("SELECT status, note, opened_decision_id FROM phases WHERE id=?", (milestone_a_id,)).fetchone()
    check("phase-set-status --name: updates status and note", row["status"] == "paused" and row["note"] == "halted", str(dict(row)))
    check("phase-set-status: COALESCE preserves opened_decision_id (not settable via this command)",
          row["opened_decision_id"] == dec_a, str(dict(row)))

    opsdb.cmd_phase_set_status(_phase_set_status_args(phase_id=milestone_a_id, status="complete"))
    row2 = conn.execute("SELECT status, note FROM phases WHERE id=?", (milestone_a_id,)).fetchone()
    check("phase-set-status --id: updates status", row2["status"] == "complete", str(dict(row2)))
    check("phase-set-status: COALESCE preserves note when --note omitted", row2["note"] == "halted", str(dict(row2)))

    try:
        opsdb.cmd_phase_set_status(_phase_set_status_args(phase_name="Does Not Exist", status="complete"))
        check("phase-set-status: unknown --name rejected with a clean error", False, "did not raise")
    except SystemExit as exc:
        check("phase-set-status: unknown --name rejected with a clean error", "no phases row named" in str(exc), str(exc))

    # ---- Case 3: phase_progress_rows() ordering + LEFT JOIN ----
    rows = ds.phase_progress_rows(conn)
    ids_in_order = [r["id"] for r in rows]
    check("phase_progress_rows(): ordered by sort_order (Phase 0 before Phase 3 before Milestone A)",
          ids_in_order.index(phase0_id) < ids_in_order.index(phase3_id) < ids_in_order.index(milestone_a_id),
          str(ids_in_order))
    by_id = {r["id"]: r for r in rows}
    check("phase_progress_rows(): resolves the real opened_decision_date via LEFT JOIN",
          by_id[milestone_a_id]["opened_decision_date"] == "2026-09-01", str(by_id[milestone_a_id]))
    check("phase_progress_rows(): resolves the real task title via LEFT JOIN",
          by_id[milestone_a_id]["task_title"] == "Milestone A task", str(by_id[milestone_a_id]))
    check("phase_progress_rows(): a phase with no closed_decision_id renders an honest NULL, not fabricated",
          by_id[phase3_id]["closed_decision_id"] is None, str(by_id[phase3_id]))

    # ---- Case 4: founder_readiness_summary() — partial, then full ----
    _task(conn, "placeholder")  # keep task ids distinct from decision ids for clarity
    for name, sort_order in (("Milestone B", 422), ("Milestone C", 423), ("Milestone D", 424)):
        opsdb.cmd_phase_add(_phase_add_args(name=name, status="complete", sort_order=sort_order, parent_phase_id=phase3_id))
    summary_abc_and_d = ds.founder_readiness_summary(conn)
    check("founder_readiness_summary(): all four Milestones complete -> both booleans true",
          summary_abc_and_d["exploratory_testing_ready"] is True and summary_abc_and_d["ui_100pct_complete"] is True,
          str(summary_abc_and_d))
    check("founder_readiness_summary(): milestones_done reflects the real count",
          summary_abc_and_d["milestones_done"] == 4, str(summary_abc_and_d))

    opsdb.cmd_phase_set_status(_phase_set_status_args(phase_name="Milestone D", status="in_progress"))
    summary_abc_only = ds.founder_readiness_summary(conn)
    check("founder_readiness_summary(): A+B+C complete, D not -> exploratory_testing_ready True, ui_100pct_complete False",
          summary_abc_only["exploratory_testing_ready"] is True and summary_abc_only["ui_100pct_complete"] is False,
          str(summary_abc_only))

    # ---- Case 5: generate_progress._in_flight_rows() excludes phase-covered tasks ----
    import generate_progress as gp
    covered_task = task_a  # already linked to the Milestone A phases row
    uncovered_task = _task(conn, "Uncovered task", status="FOUNDER_APPROVAL")
    phase_rows = ds.phase_progress_rows(conn)
    in_flight = gp._in_flight_rows(conn, phase_rows)
    in_flight_ids = {t["id"] for t in in_flight}
    check("_in_flight_rows(): excludes a task already covered by a phases.task_id",
          covered_task not in in_flight_ids, str(in_flight_ids))
    check("_in_flight_rows(): includes a real non-DONE task not covered by any phase row",
          uncovered_task in in_flight_ids, str(in_flight_ids))

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
