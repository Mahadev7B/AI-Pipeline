#!/usr/bin/env python3
"""ops/db/test_opsdb_broker.py — TASK-023 regression check for
ops/control-center/opsdb_broker.py.

Covers, against a scratch database (never the live one — see
ops/db/README.md):

1. The exhaustive five-verb allowlist: every one of the five real verbs
   works end-to-end; every excluded verb (query, plus a representative
   sample of other-role governance-write verbs) is rejected, not merely
   "not implemented" — rejected by the SAME allowlist check regardless of
   what a client claims.
2. Session-token task-id binding: a verb call with no token, an unknown
   token, and a token bound to a DIFFERENT task than the one a request
   tries to touch (task-step-status/task-progress) are all rejected.
3. Broker-injected identity: from_agent/by/agent are always "developer" on
   the wire, regardless of what a client would have supplied (there is no
   client-supplied identity field accepted for these verbs at all — this
   is checked structurally, by confirming the written rows are attributed
   to "developer" even though the test harness itself is not).
4. Target-value restrictions: handoff's to_agent allowlist (code-review
   only) and task-status's to allowlist (IN_DEVELOPMENT/CODE_REVIEW only,
   BACKLOG deliberately excluded per the module docstring's documented
   conclusion).
5. register_session/end_session peer-credential gating: accepted only
   from a trusted UID, never from an arbitrary one — the mechanism that
   makes task-id binding real enforcement, not a documentation
   convention.
6. One real end-to-end pass over an actual Unix domain socket (a temp
   path — a legitimate test fixture per this task's own testing note, not
   "OS provisioning"), exercising the wire protocol itself, not just
   handle_request() in-process.

Usage:
    python3 ops/db/test_opsdb_broker.py

(Sets its own scratch OPSDB_PATH under the process's tempdir if the
caller didn't — same convention as every other ops/db/test_*.py script.)
"""
from __future__ import annotations

import os
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

if not os.environ.get("OPSDB_PATH"):
    _scratch = Path(tempfile.mkdtemp(prefix="opsdb-test-broker-")) / "scratch.sqlite3"
    os.environ["OPSDB_PATH"] = str(_scratch)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import testing_guard  # noqa: F401,E402 — raises if OPSDB_PATH isn't a scratch path
import opsdb  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "control-center"))
import opsdb_broker  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


TRUSTED_UID = 1000
UNTRUSTED_UID = 2000


def _new_broker() -> opsdb_broker.OpsdbBroker:
    return opsdb_broker.OpsdbBroker(trusted_uids={TRUSTED_UID})


def _register(broker: opsdb_broker.OpsdbBroker, token: str, task_id: int, peer_uid: int = TRUSTED_UID) -> dict:
    return broker.handle_request(
        {"verb": "register_session", "args": {"token": token, "task_id": task_id, "agent": "developer"}},
        peer_uid,
    )


def _seed_task_and_step(conn) -> tuple[int, int]:
    with conn:
        cur = conn.execute("INSERT INTO tasks (title, status) VALUES ('scratch task', 'IN_DEVELOPMENT')")
        task_id = cur.lastrowid
        conn.execute(
            "INSERT INTO task_status_history (task_id, from_status, to_status, changed_by_agent, note) "
            "VALUES (?, NULL, 'IN_DEVELOPMENT', 'developer', 'created')",
            (task_id,),
        )
        step_cur = conn.execute("INSERT INTO task_steps (task_id, title) VALUES (?, 'a step')", (task_id,))
        step_id = step_cur.lastrowid
    return task_id, step_id


def main() -> int:
    opsdb.cmd_init(None)
    conn = opsdb.connect()
    with conn:
        conn.execute("INSERT INTO agents (name, role) VALUES ('developer', 'implementation')")
    task_a, step_a = _seed_task_and_step(conn)
    task_b, step_b = _seed_task_and_step(conn)

    # ---- Case 1: exhaustive verb allowlist ----
    broker = _new_broker()
    _register(broker, "tok-a", task_a)

    # The allowlist is EXACTLY these five, no more, no fewer (Code Review
    # non-blocking item: the old loop checked membership of ALLOWED_VERBS in
    # itself, which is tautological — assert the exact tuple instead).
    check("ALLOWED_VERBS is exactly the five documented verbs",
          opsdb_broker.ALLOWED_VERBS
          == ("handoff", "task-status", "task-step-status", "task-progress", "activity-log"),
          str(opsdb_broker.ALLOWED_VERBS))

    # EXHAUSTIVE exclusion (Code Review non-blocking item: test ALL excluded
    # verbs, not a 13-of-24 sample). Derive the full opsdb.py subcommand set
    # straight from its source `add_parser("<name>"` declarations, so a new
    # subcommand added to opsdb.py in future is automatically covered here
    # and cannot silently gain a broker path. Every one of those NOT in
    # ALLOWED_VERBS must be rejected by the same allowlist check.
    all_subcommands = set(re.findall(r'add_parser\(\s*"([^"]+)"', Path(opsdb.__file__).read_text()))
    excluded_verbs = sorted(all_subcommands - set(opsdb_broker.ALLOWED_VERBS))
    check("derived the full opsdb.py subcommand set (sanity: >= 24 excluded)",
          len(excluded_verbs) >= 24, f"got {len(excluded_verbs)}: {excluded_verbs}")
    for verb in excluded_verbs:
        resp = broker.handle_request({"verb": verb, "token": "tok-a", "args": {}}, TRUSTED_UID)
        check(f"excluded verb '{verb}' is rejected", resp["ok"] is False and "not permitted" in resp["error"],
              str(resp))

    resp = broker.handle_request(
        {"verb": "query", "token": "tok-a", "args": {"sql": "SELECT * FROM decisions"}}, TRUSTED_UID,
    )
    check("query verb specifically has no schema-wide read path through the broker",
          resp["ok"] is False, str(resp))

    # ---- Case 2: session-token binding ----
    resp = broker.handle_request({"verb": "handoff", "args": {"to_agent": "code-review"}}, TRUSTED_UID)
    check("no token at all -> rejected", resp["ok"] is False and "token" in resp["error"], str(resp))

    resp = broker.handle_request(
        {"verb": "handoff", "token": "no-such-token", "args": {"to_agent": "code-review"}}, TRUSTED_UID,
    )
    check("unknown token -> rejected", resp["ok"] is False and "token" in resp["error"], str(resp))

    resp = broker.handle_request(
        {"verb": "task-progress", "token": "tok-a", "args": {"task_id": task_b}}, TRUSTED_UID,
    )
    check("task-progress against a task NOT bound to this token -> rejected",
          resp["ok"] is False, str(resp))

    resp = broker.handle_request(
        {"verb": "task-step-status", "token": "tok-a", "args": {"step_id": step_b, "status": "done"}}, TRUSTED_UID,
    )
    check("task-step-status against a step owned by a DIFFERENT task -> rejected",
          resp["ok"] is False and "bound task" in resp["error"], str(resp))

    resp = broker.handle_request(
        {"verb": "task-step-status", "token": "tok-a", "args": {"step_id": step_a, "status": "done"}}, TRUSTED_UID,
    )
    check("task-step-status against a step owned by THIS token's bound task -> accepted", resp["ok"] is True, str(resp))

    resp = broker.handle_request(
        {"verb": "task-progress", "token": "tok-a", "args": {"task_id": task_a}}, TRUSTED_UID,
    )
    check("task-progress against this token's own bound task -> accepted", resp["ok"] is True, str(resp))
    check("task-progress reflects the real step just marked done", resp["result"]["pct"] == 100, str(resp))

    # ---- Case 3: broker-injected identity, never client-supplied ----
    resp = broker.handle_request(
        {"verb": "handoff", "token": "tok-a",
         "args": {"to_agent": "code-review", "work_completed": "did the thing"}},
        TRUSTED_UID,
    )
    check("handoff accepted", resp["ok"] is True, str(resp))
    row = conn.execute(
        "SELECT from_agent, to_agent, task_id FROM handoffs WHERE id = ?", (resp["result"]["handoff_id"],)
    ).fetchone()
    check("handoff row's from_agent is broker-forced to 'developer'", row["from_agent"] == "developer", str(dict(row)))
    check("handoff row's task_id is broker-forced to the session's bound task", row["task_id"] == task_a, str(dict(row)))

    resp = broker.handle_request(
        {"verb": "activity-log", "token": "tok-a", "args": {"summary": "a note"}}, TRUSTED_UID,
    )
    check("activity-log accepted", resp["ok"] is True, str(resp))
    arow = conn.execute(
        "SELECT agent_id, task_id FROM agent_activity WHERE id = ?", (resp["result"]["activity_id"],)
    ).fetchone()
    dev_agent_id = conn.execute("SELECT id FROM agents WHERE name = 'developer'").fetchone()["id"]
    check("activity_log row's agent is broker-forced to 'developer'", arow["agent_id"] == dev_agent_id, str(dict(arow)))
    check("activity_log row's task_id is broker-forced to the session's bound task", arow["task_id"] == task_a, str(dict(arow)))

    resp = broker.handle_request(
        {"verb": "task-status", "token": "tok-a", "args": {"to": "CODE_REVIEW"}}, TRUSTED_UID,
    )
    check("task-status accepted", resp["ok"] is True, str(resp))
    trow = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_a,)).fetchone()
    check("task-status actually moved the bound task, not some other one",
          trow["status"] == "CODE_REVIEW", str(dict(trow)))

    # ---- Case 4: target-value restrictions ----
    resp = broker.handle_request(
        {"verb": "handoff", "token": "tok-a", "args": {"to_agent": "qa"}}, TRUSTED_UID,
    )
    check("handoff to_agent='qa' rejected (only code-review allowed)", resp["ok"] is False, str(resp))

    resp = broker.handle_request(
        {"verb": "handoff", "token": "tok-a", "args": {"to_agent": "security"}}, TRUSTED_UID,
    )
    check("handoff to_agent='security' rejected", resp["ok"] is False, str(resp))

    for bad_status in ("BACKLOG", "RED_TEAM_REVIEW", "QA", "SECURITY_REVIEW", "DEPLOYED", "DONE"):
        resp = broker.handle_request(
            {"verb": "task-status", "token": "tok-a", "args": {"to": bad_status}}, TRUSTED_UID,
        )
        check(f"task-status to='{bad_status}' rejected", resp["ok"] is False, str(resp))
    check("BACKLOG is not in TASK_STATUS_ALLOWED_TO",
          "BACKLOG" not in opsdb_broker.TASK_STATUS_ALLOWED_TO)

    # ---- Case 5: register_session/end_session peer-credential gating ----
    resp = _register(broker, "tok-untrusted", task_a, peer_uid=UNTRUSTED_UID)
    check("register_session from an untrusted peer UID is refused", resp["ok"] is False, str(resp))
    resp = broker.handle_request(
        {"verb": "task-progress", "token": "tok-untrusted", "args": {"task_id": task_a}}, TRUSTED_UID,
    )
    check("a token that failed registration cannot be used at all", resp["ok"] is False, str(resp))

    resp = _register(broker, "tok-none-uid", task_a, peer_uid=None)
    check("register_session with no resolvable peer UID (SO_PEERCRED unavailable) is refused",
          resp["ok"] is False, str(resp))

    resp = broker.handle_request(
        {"verb": "end_session", "args": {"token": "tok-a"}}, UNTRUSTED_UID,
    )
    check("end_session from an untrusted peer UID is refused", resp["ok"] is False, str(resp))
    resp = broker.handle_request(
        {"verb": "task-progress", "token": "tok-a", "args": {"task_id": task_a}}, TRUSTED_UID,
    )
    check("session survives an untrusted end_session attempt", resp["ok"] is True, str(resp))

    resp = broker.handle_request({"verb": "end_session", "args": {"token": "tok-a"}}, TRUSTED_UID)
    check("end_session from a trusted peer UID succeeds", resp["ok"] is True, str(resp))
    resp = broker.handle_request(
        {"verb": "task-progress", "token": "tok-a", "args": {"task_id": task_a}}, TRUSTED_UID,
    )
    check("token is unusable after a real end_session", resp["ok"] is False, str(resp))

    # ---- Case 6: B1 robustness — a bad request never crashes/wedges ----
    # (Code Review REJECT finding B1, reproduced here so it stays fixed.)
    broker_b1 = _new_broker()
    _register(broker_b1, "tok-b1", task_a)

    # (1) A verb-valid but schema-invalid request (missing required summary)
    # must be a clean _err, NOT an escaped sqlite3.IntegrityError. Validated
    # before the DB is even touched.
    resp = broker_b1.handle_request({"verb": "activity-log", "token": "tok-b1", "args": {}}, TRUSTED_UID)
    check("activity-log with no summary -> clean _err (no sqlite3.IntegrityError escapes)",
          resp["ok"] is False and "summary" in resp["error"], str(resp))
    # An empty-string and a non-string summary are likewise clean rejections.
    resp = broker_b1.handle_request(
        {"verb": "activity-log", "token": "tok-b1", "args": {"summary": ""}}, TRUSTED_UID)
    check("activity-log with empty summary -> clean _err", resp["ok"] is False, str(resp))
    resp = broker_b1.handle_request(
        {"verb": "activity-log", "token": "tok-b1", "args": {"summary": 123}}, TRUSTED_UID)
    check("activity-log with non-string summary -> clean _err", resp["ok"] is False, str(resp))
    # The broker still works right after those rejections (no wedged state).
    resp = broker_b1.handle_request(
        {"verb": "activity-log", "token": "tok-b1", "args": {"summary": "fine now"}}, TRUSTED_UID)
    check("broker still serves a valid request after schema-invalid ones", resp["ok"] is True, str(resp))

    # (2) Fail-closed on lost sessions: a fresh broker (simulating a restart
    # that dropped the in-memory _sessions) rejects a previously-valid token.
    restarted = _new_broker()
    resp = restarted.handle_request(
        {"verb": "activity-log", "token": "tok-b1", "args": {"summary": "x"}}, TRUSTED_UID)
    check("a token from before a broker 'restart' is rejected (fail closed)",
          resp["ok"] is False and "token" in resp["error"], str(resp))

    # ---- Case 7: a real Unix domain socket, end to end (incl. B1 sendall guard) ----
    check("wire-protocol test", _run_socket_test(task_a=task_b))

    conn.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


def _run_socket_test(task_a: int) -> bool:
    """Spins up a real OpsdbBroker.serve_forever() on a temp Unix socket
    path in a background thread, sends real requests over a real socket
    connection, and tears it down. A temp-path Unix socket is a test
    fixture, not persistent OS provisioning — see this file's own module
    docstring and the task's own testing instructions."""
    ok = True
    sock_dir = tempfile.mkdtemp(prefix="opsdb-broker-socket-test-")
    sock_path = os.path.join(sock_dir, "opsdb.sock")
    broker = opsdb_broker.OpsdbBroker(socket_path=sock_path, trusted_uids={os.geteuid()})

    thread = threading.Thread(target=broker.serve_forever, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 5.0
        while not os.path.exists(sock_path) and time.time() < deadline:
            time.sleep(0.02)
        if not os.path.exists(sock_path):
            print("[FAIL] socket test: broker never created its socket file")
            return False

        # Register a session — this connection's own peer UID is our real
        # UID (os.geteuid()), which we put in trusted_uids above. Uses the
        # real wire client `opsdb_broker.send_request` (Code Review
        # non-blocking item: do NOT reimplement a third copy of the client).
        reg = opsdb_broker.send_request(sock_path, {"verb": "register_session",
                                        "args": {"token": "sock-tok", "task_id": task_a, "agent": "developer"}})
        if not reg.get("ok"):
            print(f"[FAIL] socket test: register_session over the real socket failed: {reg}")
            return False

        resp = opsdb_broker.send_request(sock_path, {"verb": "activity-log", "token": "sock-tok",
                                         "args": {"summary": "socket test"}})
        if not resp.get("ok"):
            print(f"[FAIL] socket test: activity-log over the real socket failed: {resp}")
            return False

        resp = opsdb_broker.send_request(sock_path, {"verb": "query", "token": "sock-tok",
                                                     "args": {"sql": "SELECT 1"}})
        if resp.get("ok"):
            print("[FAIL] socket test: excluded verb 'query' was NOT rejected over the real socket")
            return False

        # B1: a client that sends a request and closes WITHOUT reading the
        # response must not crash the daemon (the old code raised
        # BrokenPipeError in sendall and killed serve_forever). Do exactly
        # that, then confirm the broker still serves the next connection.
        _send_and_abandon(sock_path, {"verb": "activity-log", "token": "sock-tok",
                                      "args": {"summary": "client will not read the reply"}})
        resp = opsdb_broker.send_request(sock_path, {"verb": "activity-log", "token": "sock-tok",
                                         "args": {"summary": "daemon survived the abandoned client"}})
        if not resp.get("ok"):
            print(f"[FAIL] socket test: daemon did not survive a close-before-read client: {resp}")
            return False

        print("[PASS] socket test: register_session, an allowed verb, an excluded verb, and a "
              "close-before-read client all behave correctly over a real Unix domain socket")
        return ok
    finally:
        try:
            os.unlink(sock_path)
        except OSError:
            pass


def _send_and_abandon(sock_path: str, request: dict) -> None:
    """Send one request then immediately close, never reading the reply —
    the B1 'client that disconnects before the broker's sendall' repro."""
    import json as _json
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(sock_path)
        sock.sendall((_json.dumps(request) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        # deliberately do NOT recv — close on __exit__
    # Give the broker a moment to attempt its (guarded) sendall and loop back.
    time.sleep(0.1)


if __name__ == "__main__":
    raise SystemExit(main())
