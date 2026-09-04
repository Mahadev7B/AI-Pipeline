#!/usr/bin/env python3
"""ops/db/test_risk_register.py — Milestone C (TASK-021) regression check.

Reproduces, against a scratch database (never the live one — see
ops/db/README.md), the cases this milestone's architecture (CTO,
ops/reviews/cto-milestone-c-architecture.md), Design (ops/reviews/
design-review-milestone-c.md) and Red Team (review_results.id=65)
reviews all care about:

1. derived_state.related_decisions_for_risk()'s word-boundary regex:
   matches the literal 'risks.id=N' convention this project's decisions
   already use; matches the Red Team-requested loosened whitespace
   variant 'risks.id = N' too, at zero extra cost; does NOT false-match
   a longer id ('risks.id=30' must not match risk_id=3); returns []
   (never fabricates a relation) when no decision names the risk at all.
2. derived_state.risk_register_rows()'s grouping/ordering: open before
   mitigated before resolved, severity-descending within each group, and
   the task-scope LEFT JOIN resolving a real task title.

Usage:
    OPSDB_PATH=/tmp/test-risk-register.sqlite3 python3 ops/db/test_risk_register.py

(Or simply `python3 ops/db/test_risk_register.py` — it sets its own
scratch OPSDB_PATH under the process's tempdir if the caller didn't.)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("OPSDB_PATH"):
    _scratch = Path(tempfile.mkdtemp(prefix="opsdb-test-risks-")) / "scratch.sqlite3"
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


def _agent(conn, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO agents (name, role, model, skills, frameworks, tools, "
        "permissions_allow, permissions_deny) VALUES (?, 'x', 'x', '[]', '[]', '[]', '[]', '[]')",
        (name,),
    )


def _risk(conn, scope_type: str, scope_id, title: str, severity: str, status: str,
          raised_by: str = "cto", owner=None, mitigation=None, resolved: bool = False) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO risks (scope_type, scope_id, raised_by_agent, title, "
            "description, severity, status, owner_agent, mitigation, resolved_at) "
            "VALUES (?, ?, ?, ?, 'test description', ?, ?, ?, ?, ?)",
            (scope_type, scope_id, raised_by, title, severity, status, owner, mitigation,
             "2026-09-01T00:00:00.000Z" if resolved else None),
        )
    return cur.lastrowid


def main() -> int:
    conn = opsdb.connect(require_exists=False)
    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text()
    conn.executescript(schema_sql)
    conn.commit()

    for name in ("cto", "security", "developer"):
        _agent(conn, name)

    # ---- Case 1: related_decisions_for_risk() regex matching ----
    opsdb.record_decision(
        conn, "Exact literal match", "decided", "cto",
        problem="Concerns risks.id=3 directly.",
    )
    opsdb.record_decision(
        conn, "Whitespace variant (Red Team's loosened-regex suggestion)",
        "See risks.id = 3 for context.", "cto",
    )
    opsdb.record_decision(
        conn, "Unrelated decision naming a different, longer risk id", "decided", "cto",
        reason="This references risks.id=30, not risk 3.",
    )
    opsdb.record_decision(
        conn, "Unrelated decision, no risks.id mention at all", "decided", "cto",
        tradeoffs="No risk reference here whatsoever.",
    )

    matches = ds.related_decisions_for_risk(conn, 3)
    match_titles = {m["title"] for m in matches}
    check("related_decisions_for_risk(3): matches the exact literal 'risks.id=3'",
          "Exact literal match" in match_titles, str(match_titles))
    check("related_decisions_for_risk(3): matches the whitespace variant 'risks.id = 3' "
          "(Red Team's non-blocking suggestion, folded in)",
          "Whitespace variant (Red Team's loosened-regex suggestion)" in match_titles, str(match_titles))
    check("related_decisions_for_risk(3): does NOT false-match 'risks.id=30' (word boundary)",
          "Unrelated decision naming a different, longer risk id" not in match_titles, str(match_titles))
    check("related_decisions_for_risk(3): excludes the decision with no risks.id mention",
          "Unrelated decision, no risks.id mention at all" not in match_titles, str(match_titles))
    check("related_decisions_for_risk(3): exactly 2 real matches, no more, no fewer",
          len(matches) == 2, str(matches))

    check("related_decisions_for_risk(999): [] for a risk no decision names — never fabricated",
          ds.related_decisions_for_risk(conn, 999) == [], str(ds.related_decisions_for_risk(conn, 999)))

    # ---- Case 2: risk_register_rows() grouping/ordering + task-title LEFT JOIN ----
    with conn:
        cur = conn.execute(
            "INSERT INTO tasks (title, current_owner) VALUES ('A real linked task', 'test')"
        )
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, "
            "changed_by_agent, note) VALUES (?, NULL, 'BACKLOG', 'test', 'created')",
            (task_id,),
        )

    r_open_high = _risk(conn, "company", None, "Open, high severity", "high", "open")
    r_open_medium = _risk(conn, "company", None, "Open, medium severity", "medium", "open")
    r_mitigated = _risk(conn, "task", task_id, "Mitigated, task-scoped", "medium", "mitigated")
    r_resolved = _risk(conn, "company", None, "Resolved, low severity", "low", "resolved", resolved=True)

    rows = ds.risk_register_rows(conn)
    ids_in_order = [r["id"] for r in rows]
    check("risk_register_rows(): open group comes before mitigated before resolved",
          ids_in_order.index(r_open_high) < ids_in_order.index(r_mitigated) < ids_in_order.index(r_resolved),
          str(ids_in_order))
    check("risk_register_rows(): within the open group, high severity sorts before medium",
          ids_in_order.index(r_open_high) < ids_in_order.index(r_open_medium), str(ids_in_order))

    by_id = {r["id"]: r for r in rows}
    check("risk_register_rows(): task-scoped risk resolves the real task title via LEFT JOIN",
          by_id[r_mitigated]["scope_task_title"] == "A real linked task",
          str(by_id[r_mitigated]["scope_task_title"]))
    check("risk_register_rows(): company-scoped risk has no scope_task_title (honest NULL, not fabricated)",
          by_id[r_open_high]["scope_task_title"] is None, str(by_id[r_open_high]["scope_task_title"]))
    check("risk_register_rows(): every real risks row is present (no silent drop)",
          len(rows) == 4, str(len(rows)))

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
