#!/usr/bin/env python3
"""ops/db/test_cost_tracking.py — Milestone B (TASK-020) regression check.

Reproduces, against a scratch database (never the live one — see
ops/db/README.md), the real cases this milestone's architecture, Design,
and Red Team reviews all care about:

1. opsdb.end_run()'s new cost_usd parameter actually persists into
   agent_runs.cost_usd, for both the 'ended' and 'failed' statuses, and
   still defaults to NULL when omitted (backward-compatible contract).
2. derived_state.cost_coverage()/format_cost_coverage()'s three-way
   wording branch — the exact case matrix Design's review (item 3) and
   Red Team's review (§3, required fix) both specify:
     - n == 0                       -> "No ... recorded yet." (no $ sign)
     - n > 0, covered == 0          -> "not available" (no bare $0.00 —
       the Red Team required fix, distinct from Design's own n==0 case)
     - covered > 0, covered < n     -> "$X.XX across C of N ... (K
       recorded before cost tracking)"
     - covered == n (full coverage) -> "$X.XX across N ... ." (no
       parenthetical when nothing is missing)
3. derived_state.company_cost_digest() — by-path grouping (including the
   'Synchronous review' fifth path, Design's review item 6 / Red Team's
   §1), and that automation's own agent_runs rows are NOT double-counted
   into the headline total alongside automation_events (CTO's architecture
   doc §3.2 — automation_events stays the authoritative source for that
   one path).
4. derived_state.meeting_cost_usd() — a real per-meeting total built from
   agent_runs rows scoped to that meeting only (never a company-scoped
   agent_runs row, e.g. a hypothetical _select_participants() invocation
   for a DIFFERENT meeting, leaking into this one's total).
5. Historical-NULL rendering: an agent_runs row with cost_usd = NULL
   (the real shape SQLite's ALTER TABLE ADD COLUMN gives every
   pre-migration row) renders as "not available (recorded before cost
   tracking)" wording, never a crash, never a fabricated $0.00 — same
   discipline as case 2, exercised here via a realistic mixed-coverage
   meeting.
6. chief_of_staff._sum_costs() — the multi-invocation aggregation a
   Chief-of-Staff turn with a CONSULT: needs (CTO's architecture doc
   §2.2/§2.4): both None -> None (never a fabricated 0.0), one real +
   one None -> the real value alone, two reals -> their sum.

Usage:
    OPSDB_PATH=/tmp/test-cost-tracking.sqlite3 python3 ops/db/test_cost_tracking.py

(Or simply `python3 ops/db/test_cost_tracking.py` — it sets its own
scratch OPSDB_PATH under the process's tempdir if the caller didn't.)
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

if not os.environ.get("OPSDB_PATH"):
    _scratch = Path(tempfile.mkdtemp(prefix="opsdb-test-cost-")) / "scratch.sqlite3"
    os.environ["OPSDB_PATH"] = str(_scratch)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testing_guard  # noqa: F401,E402 — raises if OPSDB_PATH isn't a scratch path
import opsdb  # noqa: E402
import derived_state as ds  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "control-center"))
import chief_of_staff  # noqa: E402 — only _sum_costs() is exercised; no DB/network/subprocess call happens on import

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


class _FakeResult:
    """Stand-in for agent_runtime.RuntimeResult — _sum_costs() only ever
    reads .cost_usd, so a real invocation is not needed to test it."""
    def __init__(self, cost_usd):
        self.cost_usd = cost_usd


def main() -> int:
    conn = opsdb.connect(require_exists=False)
    schema_sql = (Path(__file__).resolve().parent / "schema.sql").read_text()
    conn.executescript(schema_sql)
    opsdb._apply_additive_column_migrations(conn)  # exercised directly, same call cmd_init makes
    conn.commit()

    for name in ("cto", "ceo", "financial", "security", "orchestrator", "code-review"):
        _agent(conn, name)
    conn.commit()

    # ---- Case 1: end_run()'s cost_usd parameter actually persists ----
    r1 = opsdb.start_run(conn, "cto", "company", "Ask-Agent: answering a Founder question")
    opsdb.end_run(conn, r1, "ended", cost_usd=1.23)
    row1 = conn.execute("SELECT status, cost_usd FROM agent_runs WHERE id = ?", (r1,)).fetchone()
    check("end_run(cost_usd=1.23): status is 'ended'", row1["status"] == "ended", row1["status"])
    check("end_run(cost_usd=1.23): cost_usd persisted exactly", row1["cost_usd"] == 1.23, str(row1["cost_usd"]))

    r2 = opsdb.start_run(conn, "cto", "company", "Ask-Agent: answering a Founder question")
    opsdb.end_run(conn, r2, "failed", cost_usd=0.02)
    row2 = conn.execute("SELECT status, cost_usd FROM agent_runs WHERE id = ?", (r2,)).fetchone()
    check("end_run('failed', cost_usd=0.02): cost_usd persisted even on failure",
          row2["cost_usd"] == 0.02, str(row2["cost_usd"]))

    r3 = opsdb.start_run(conn, "cto", "company", "Ask-Agent: answering a Founder question")
    opsdb.end_run(conn, r3, "failed")  # omitted — backward-compatible default
    row3 = conn.execute("SELECT cost_usd FROM agent_runs WHERE id = ?", (r3,)).fetchone()
    check("end_run() with cost_usd omitted: stays NULL (no fabricated 0.0)",
          row3["cost_usd"] is None, str(row3["cost_usd"]))

    # ---- Case 2: cost_coverage()/format_cost_coverage() three-way branch ----
    zero = ds.cost_coverage(0, 0, 0)
    check("cost_coverage(n=0): usd is None", zero["usd"] is None, str(zero))
    check("format_cost_coverage(n=0): no $ sign, 'recorded yet' wording",
          ds.format_cost_coverage(zero) == "No invocations recorded yet.",
          ds.format_cost_coverage(zero))

    uncosted = ds.cost_coverage(5, 0, 0)  # Red Team's required case: M>0, N=0
    check("cost_coverage(n=5, covered=0): usd is None (Red Team required fix)",
          uncosted["usd"] is None, str(uncosted))
    uncosted_text = ds.format_cost_coverage(uncosted)
    check("format_cost_coverage(n=5, covered=0): no bare $0.00 anywhere in the text",
          "$0.00" not in uncosted_text and "$" not in uncosted_text, uncosted_text)
    check("format_cost_coverage(n=5, covered=0): says 'not available'",
          "not available" in uncosted_text, uncosted_text)

    partial = ds.cost_coverage(5, 3, 1.50)
    partial_text = ds.format_cost_coverage(partial)
    check("format_cost_coverage(partial coverage): shows real $ and the coverage count",
          partial_text == "$1.50 across 3 of 5 invocations (2 recorded before cost tracking)", partial_text)

    full = ds.cost_coverage(3, 3, 4.20)
    full_text = ds.format_cost_coverage(full)
    check("format_cost_coverage(full coverage): no parenthetical when nothing is missing",
          full_text == "$4.20 across 3 of 3 invocations.", full_text)

    # ---- Case 3: company_cost_digest() — by-path grouping + no automation double-count ----
    with conn:
        conn.execute(
            "INSERT INTO tasks (title, current_owner) VALUES ('cost-test task', 'test')"
        )
        task_id = conn.execute("SELECT id FROM tasks WHERE title = 'cost-test task'").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, changed_by_agent, note) "
            "VALUES (?, NULL, 'CODE_REVIEW', 'test', 'trigger')",
            (task_id,),
        )
        trigger_id = cur.lastrowid
        conn.execute(
            "INSERT INTO automation_events (task_id, trigger_status_history_id, status, outcome, cost_usd, "
            "started_at, ended_at) VALUES (?, ?, 'completed', 'pass', 0.30, "
            "strftime('%Y-%m-%dT%H:%M:%fZ','now'), strftime('%Y-%m-%dT%H:%M:%fZ','now'))",
            (task_id, trigger_id),
        )
    r4 = opsdb.start_run(conn, "code-review", "task",
                          "Automated Code Review: reviewing a completed Developer handoff", scope_id=task_id)
    opsdb.end_run(conn, r4, "ended", cost_usd=999.0)  # deliberately absurd — must NOT reach the headline total

    digest = ds.company_cost_digest(conn)
    by_path_labels = [p["label"] for p in digest["by_path"]]
    check("company_cost_digest(): all five paths present, in order",
          by_path_labels == ["Ask-Agent", "Meetings", "Chief of Staff", "Automated Code Review", "Synchronous review"],
          str(by_path_labels))
    automated_row = next(p for p in digest["by_path"] if p["label"] == "Automated Code Review")
    check("company_cost_digest(): Automated Code Review bucket reads from automation_events (real $0.30, not $999)",
          automated_row["cov"]["usd"] == 0.30, str(automated_row["cov"]))
    check("company_cost_digest(): headline all_time total excludes the automation agent_runs row's own $999 "
          "(would otherwise double-count automation's real $0.30 spend)",
          digest["all_time"]["usd"] is not None and digest["all_time"]["usd"] < 900,
          str(digest["all_time"]))

    # ---- Case 4: meeting_cost_usd() — scoped strictly to its own meeting ----
    mid_a = opsdb.create_meeting(conn, "Meeting A", "founder", ["ceo"])
    mid_b = opsdb.create_meeting(conn, "Meeting B", "founder", ["ceo"])
    ra = opsdb.start_run(conn, "ceo", "meeting", "Meeting: contributing a position", scope_id=mid_a)
    opsdb.end_run(conn, ra, "ended", cost_usd=0.70)
    rb = opsdb.start_run(conn, "ceo", "meeting", "Meeting: contributing a position", scope_id=mid_b)
    opsdb.end_run(conn, rb, "ended", cost_usd=5.00)
    # A company-scoped run (e.g. CEO's own participant-selection call, per
    # meeting_orchestrator._select_participants()'s docstring) must NOT
    # leak into either meeting's own total.
    r_company = opsdb.start_run(conn, "ceo", "company", "Meeting: selecting participants")
    opsdb.end_run(conn, r_company, "ended", cost_usd=42.0)

    cov_a = ds.meeting_cost_usd(conn, mid_a)
    check("meeting_cost_usd(A): only A's own $0.70, not B's $5.00 or the company-scoped $42.00",
          cov_a == {"n": 1, "covered": 1, "usd": 0.70}, str(cov_a))
    cov_b = ds.meeting_cost_usd(conn, mid_b)
    check("meeting_cost_usd(B): only B's own $5.00", cov_b == {"n": 1, "covered": 1, "usd": 5.00}, str(cov_b))

    # ---- Case 5: historical-NULL rendering in a realistic mixed meeting ----
    r_null = opsdb.start_run(conn, "security", "meeting", "Meeting: contributing a position", scope_id=mid_a)
    opsdb.end_run(conn, r_null, "ended")  # pre-migration shape: no cost_usd ever passed
    cov_a_mixed = ds.meeting_cost_usd(conn, mid_a)
    check("meeting_cost_usd(A) after a NULL-cost row: n=2, covered=1, real $ still correct",
          cov_a_mixed == {"n": 2, "covered": 1, "usd": 0.70}, str(cov_a_mixed))
    check("format_cost_coverage(A, mixed): honest partial-coverage wording, no crash",
          ds.format_cost_coverage(cov_a_mixed) ==
          "$0.70 across 1 of 2 invocations (1 recorded before cost tracking)",
          ds.format_cost_coverage(cov_a_mixed))

    # ---- Case 6: chief_of_staff._sum_costs() ----
    check("_sum_costs(None, None): None (never a fabricated 0.0)",
          chief_of_staff._sum_costs(None, None) is None)
    check("_sum_costs(result-only, no consult): real value passes through",
          chief_of_staff._sum_costs(_FakeResult(0.11), None) == 0.11)
    summed = chief_of_staff._sum_costs(_FakeResult(0.11), _FakeResult(0.05))
    check("_sum_costs(result, narration_result): sums both real invocations",
          summed is not None and abs(summed - 0.16) < 1e-9, str(summed))
    check("_sum_costs(failed result with cost_usd=None, no consult): None, not 0.0",
          chief_of_staff._sum_costs(_FakeResult(None), None) is None)

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
