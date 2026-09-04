#!/usr/bin/env python3
"""ops/control-center/opsdb_broker.py — TASK-023 (risks.id=3 durable
closure: OS-level/process-separation sandboxing for Developer).

Closes the `operations.sqlite3` bind-mount gap named in
`ops/reviews/cto-task023-architecture.md` §3: the database file is never
present inside the sandboxed Developer process's filesystem namespace at
all. This daemon is the *only* thing the sandbox can reach that ever
touches the real database, over a fixed Unix domain socket
(`/run/ai-pipeline/opsdb.sock` by default), and it exposes an exhaustive,
hardcoded five-verb allowlist:

    handoff, task-status, task-step-status, task-progress, activity-log

and NO OTHER opsdb.py subcommand — no `query`, no raw SQL passthrough of
any kind, no other role's governance-write verbs. This is the corrected
design from the Correction section of
`ops/reviews/cto-task023-architecture.md` (after Red Team's
`review_results.id=73` REJECT, re-verified PASS in
`ops/reviews/red-team-task023-reverification.md`) — read that Correction
section in full before touching this file's verb table.

RUNS AS: the Founder's own user, or a dedicated trusted
`ai-pipeline-broker` system account — NEVER as `ai-developer`. See
`ops/reviews/task023-os-provisioning-runbook.md` for how this process is
actually started in production; this module only defines the daemon
itself, it is not started as a side effect of importing it (`if __name__
== "__main__":` guard at the bottom, same convention as opsdb.py).

--------------------------------------------------------------------------
THE `task-status` `to` ALLOWLIST — BACKLOG, RESOLVED (do not re-add
without new evidence)
--------------------------------------------------------------------------
The architecture document's corrected §3 table originally allowlisted
`task-status`'s `to` value as `{IN_DEVELOPMENT, CODE_REVIEW, BACKLOG}`,
citing `task_status_history` counts of `CODE_REVIEW` x11, `IN_DEVELOPMENT`
x5, `BACKLOG` x1 as "the only three statuses Developer has ever set."
Red Team's re-verification (`ops/reviews/red-team-task023-reverification.md`,
"New finding") traced that single `BACKLOG` row directly and found
`from_status=NULL, note='created'` — the exact signature of
`cmd_task_create`'s own automatic `task_status_history` insert
(opsdb.py's `cmd_task_create`), NOT a genuine `task-status` call. There is
zero historical evidence Developer has ever legitimately used
`task-status` itself to move a task to BACKLOG, and nothing in
`.claude/agents/developer.md` or the Developer role doc names a workflow
that would. Independently re-verified here, during Development
(TASK-023), against the same live database, before writing this table:
the finding holds.

**Conclusion: BACKLOG is dropped from this allowlist.** Red Team's
re-verification note offered two options — drop it, or correct the
citation and make an explicit non-evidence-free case for keeping it. No
such case exists (BACKLOG is the state a task starts in, before any real
work; a sandboxed Developer session already IN_DEVELOPMENT on a bound
task has no legitimate reason to push it backward to BACKLOG), so this
implementation takes the "drop it" branch. `to` is allowlisted to exactly
`{IN_DEVELOPMENT, CODE_REVIEW}`. If a real, evidenced need for BACKLOG (or
any other status) surfaces later, adding it is a new, separately-reviewed
decision — not something this comment pre-authorizes.

--------------------------------------------------------------------------
Session binding / identity pinning
--------------------------------------------------------------------------
`launch_developer_session.py` generates a random per-session token
(`secrets.token_hex(16)`) and registers `(token, task_id, agent)` with
this broker over the *same* socket, via the `register_session` verb —
BEFORE the sandboxed process is ever started. `register_session` (and its
counterpart, `end_session`) are gated on the connecting peer's real UID,
read via `SO_PEERCRED` (a kernel-verified Linux socket option, not
client-spoofable) — accepted only from a UID in this broker's own
"trusted registrar" set (by default just this process's own effective
UID; see `_default_trusted_uids()` for how to widen it when the broker
runs under a separate `ai-pipeline-broker` account than the launcher).
`ai-developer`'s UID is never in that set, so the sandboxed process
itself can never call `register_session`/`end_session` — it can only ever
use its own bound token on the five allowed verbs. Every one of those
five verbs resolves `task_id`/`agent` from this session table, keyed by
the token the client presents — NEVER from a client-supplied field.
`launch_developer_session.py` calls `end_session` when the sandboxed
process exits.

--------------------------------------------------------------------------
Wire protocol
--------------------------------------------------------------------------
One JSON request per connection, newline-terminated, e.g.:
    {"verb": "task-status", "token": "<hex>", "args": {"to": "CODE_REVIEW"}}
One JSON response, newline-terminated:
    {"ok": true, "result": {...}}   or   {"ok": false, "error": "..."}

Single-threaded accept loop — deliberate for a first implementation of
new, security-relevant code (this project's own convention: small,
reviewable, not cleverer than it needs to be). A single Developer
session's own CLI commands are already serialized (one `opsdb.py`
invocation at a time from one sandboxed shell); this is a known,
documented scaling limit, not a correctness gap, and is flagged here for
Code Review/QA rather than silently engineered around.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import struct
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402 — the refactored plain callables this broker calls directly

DEFAULT_SOCKET_PATH = "/run/ai-pipeline/opsdb.sock"

# Exhaustive, hardcoded — see module docstring. Never derived from
# opsdb.py's own subcommand list (that would silently grow this set every
# time a new, unrelated opsdb.py command is added).
ALLOWED_VERBS = ("handoff", "task-status", "task-step-status", "task-progress", "activity-log")

# See "THE task-status to ALLOWLIST" section of the module docstring —
# BACKLOG deliberately excluded.
TASK_STATUS_ALLOWED_TO = frozenset({"IN_DEVELOPMENT", "CODE_REVIEW"})
HANDOFF_ALLOWED_TO_AGENT = frozenset({"code-review"})
_TASK_STEP_STATUSES = frozenset({"pending", "in_progress", "done"})

# SO_PEERCRED on Linux: struct ucred { pid_t pid; uid_t uid; gid_t gid; } —
# three native ints.
_SO_PEERCRED_FMT = "3i"
_SO_PEERCRED_SIZE = struct.calcsize(_SO_PEERCRED_FMT)

_MAX_REQUEST_BYTES = 1_000_000  # generous ceiling against a misbehaving/compromised sandboxed client

# B1 (Code Review REJECT / addendum): a client that connects and holds the
# connection open (or never shuts down its write half) must not wedge the
# single-threaded accept loop for every other caller. An idle/slow client
# costs at most one timeout, never the daemon. Low-QPS, trusted-path broker,
# so a few seconds is ample; a hostile client can still serialize others up
# to this bound (documented, acceptable — see the module docstring).
_CONN_TIMEOUT_S = 10.0


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


def _ok(result: dict) -> dict:
    return {"ok": True, "result": result}


class OpsdbBroker:
    """The broker's request-handling logic, factored out from socket I/O
    so it can be unit-tested directly (`handle_request()`) without a real
    daemon process or a separate `ai-developer` account — per TASK-023's
    own testing note, a Unix socket over a temp path is a legitimate test
    fixture; only a *persistent, always-running* daemon under a real
    dedicated OS account is the thing this task's Development pass must
    not stand up."""

    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH, trusted_uids: set[int] | None = None):
        self.socket_path = socket_path
        self._sessions: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._trusted_uids = trusted_uids if trusted_uids is not None else self._default_trusted_uids()

    @staticmethod
    def _default_trusted_uids() -> set[int]:
        """This process's own effective UID is always trusted (the common
        case: broker and launcher both run as the Founder's own account).
        `OPSDB_BROKER_TRUSTED_UIDS` (comma-separated integers) widens this
        for the alternative shape named in the architecture doc — the
        broker running under a separate, dedicated `ai-pipeline-broker`
        system account, distinct from the Founder's own UID that
        `launch_developer_session.py` runs as. See the OS-provisioning
        runbook for how this is actually configured in that shape."""
        uids = {os.geteuid()}
        for token in os.environ.get("OPSDB_BROKER_TRUSTED_UIDS", "").split(","):
            token = token.strip()
            if token:
                uids.add(int(token))
        return uids

    # ------------------------------------------------------------ sessions --

    def _lookup_session(self, token) -> dict | None:
        if not isinstance(token, str) or not token:
            return None
        with self._lock:
            return self._sessions.get(token)

    def _handle_register_session(self, args: dict, peer_uid: int | None) -> dict:
        if peer_uid is None or peer_uid not in self._trusted_uids:
            return _err("register_session refused: connecting peer is not a trusted registrar")
        token = args.get("token")
        task_id = args.get("task_id")
        agent = args.get("agent")
        if not isinstance(token, str) or not token:
            return _err("register_session requires a non-empty string 'token'")
        if not isinstance(task_id, int) or isinstance(task_id, bool):
            return _err("register_session requires an integer 'task_id'")
        if agent != "developer":
            # TASK-023 scopes this broker to Developer sandboxes only
            # (ops/reviews/cto-task023-architecture.md §4.3 — no second
            # role warrants this treatment yet). A future extension to
            # another role is a new, separately-reviewed decision.
            return _err("register_session only supports agent='developer' in this milestone's scope")
        with self._lock:
            self._sessions[token] = {"task_id": task_id, "agent": agent}
        return _ok({"registered": True})

    def _handle_end_session(self, args: dict, peer_uid: int | None) -> dict:
        if peer_uid is None or peer_uid not in self._trusted_uids:
            return _err("end_session refused: connecting peer is not a trusted registrar")
        token = args.get("token")
        with self._lock:
            self._sessions.pop(token, None)
        return _ok({"ended": True})

    # --------------------------------------------------------- the 5 verbs --

    def _open_conn(self):
        return opsdb.connect()

    def _handle_handoff(self, session: dict, args: dict) -> dict:
        to_agent = args.get("to_agent")
        if to_agent not in HANDOFF_ALLOWED_TO_AGENT:
            return _err(f"to_agent must be one of {sorted(HANDOFF_ALLOWED_TO_AGENT)}")
        conn = self._open_conn()
        try:
            handoff_id = opsdb.record_handoff(
                conn,
                task_id=session["task_id"],
                from_agent="developer",
                to_agent=to_agent,
                work_completed=args.get("work_completed"),
                files=args.get("files"),
                tests_added=args.get("tests_added"),
                expected_behavior=args.get("expected_behavior"),
                known_limitations=args.get("known_limitations"),
                checklist=args.get("checklist"),
                base_commit_sha=args.get("base_commit_sha"),
                head_commit_sha=args.get("head_commit_sha"),
            )
        finally:
            conn.close()
        return _ok({"handoff_id": handoff_id, "from_agent": "developer", "to_agent": to_agent})

    def _handle_task_status(self, session: dict, args: dict) -> dict:
        to_status = args.get("to")
        if to_status not in TASK_STATUS_ALLOWED_TO:
            return _err(f"to must be one of {sorted(TASK_STATUS_ALLOWED_TO)}")
        conn = self._open_conn()
        try:
            from_status = opsdb.record_task_status(
                conn, session["task_id"], to_status, "developer",
                note=args.get("note"), owner=args.get("owner"),
            )
        finally:
            conn.close()
        return _ok({"from_status": from_status, "to_status": to_status})

    def _handle_task_step_status(self, session: dict, args: dict) -> dict:
        step_id = args.get("step_id")
        status = args.get("status")
        if not isinstance(step_id, int) or isinstance(step_id, bool):
            return _err("step_id must be an integer")
        if status not in _TASK_STEP_STATUSES:
            return _err(f"status must be one of {sorted(_TASK_STEP_STATUSES)}")
        conn = self._open_conn()
        try:
            owning_task_id = opsdb.task_step_owner(conn, step_id)
            if owning_task_id is None:
                return _err(f"no such task step id={step_id}")
            if owning_task_id != session["task_id"]:
                return _err("step_id does not belong to this session's bound task")
            opsdb.set_task_step_status(conn, step_id, status)
        finally:
            conn.close()
        return _ok({"step_id": step_id, "status": status})

    def _handle_task_progress(self, session: dict, args: dict) -> dict:
        task_id = args.get("task_id")
        if task_id != session["task_id"]:
            return _err("task_id must equal this session's bound task")
        conn = self._open_conn()
        try:
            progress = opsdb.compute_task_progress(conn, task_id)
        finally:
            conn.close()
        return _ok(progress)

    def _handle_activity_log(self, session: dict, args: dict) -> dict:
        # B1 (addendum): validate required arg presence/type BEFORE touching
        # the DB, so a schema-invalid request (e.g. a missing/empty summary)
        # is a clean rejection here, not a caught sqlite3.IntegrityError
        # (agent_activity.summary is NOT NULL) — the DB is never needlessly
        # opened, and the error message is about the actual problem.
        summary = args.get("summary")
        if not isinstance(summary, str) or not summary:
            return _err("activity-log requires a non-empty string 'summary'")
        detail = args.get("detail")
        if detail is not None and not isinstance(detail, str):
            return _err("activity-log 'detail' must be a string when present")
        conn = self._open_conn()
        try:
            activity_id = opsdb.record_activity(
                conn, "developer", session["task_id"], summary, detail,
            )
        finally:
            conn.close()
        return _ok({"activity_id": activity_id})

    _VERB_HANDLERS = {
        "handoff": _handle_handoff,
        "task-status": _handle_task_status,
        "task-step-status": _handle_task_step_status,
        "task-progress": _handle_task_progress,
        "activity-log": _handle_activity_log,
    }

    # ------------------------------------------------------------ dispatch --

    def handle_request(self, request, peer_uid: int | None) -> dict:
        """The full request-handling logic, given an already-parsed
        request dict and the caller's real peer UID (or None if it could
        not be determined). No socket I/O here — this is the unit-tested
        entry point."""
        if not isinstance(request, dict):
            return _err("request must be a JSON object")
        verb = request.get("verb")
        args = request.get("args")
        if args is None:
            args = {}
        if not isinstance(args, dict):
            return _err("args must be a JSON object")

        if verb == "register_session":
            return self._handle_register_session(args, peer_uid)
        if verb == "end_session":
            return self._handle_end_session(args, peer_uid)

        if verb not in ALLOWED_VERBS:
            # Exhaustive allowlist rejection — every other opsdb.py
            # subcommand (including query) has no path through this
            # broker at all, regardless of what a client claims. See the
            # module docstring's link to the Correction section.
            return _err(f"verb {verb!r} is not permitted on this socket")

        session = self._lookup_session(request.get("token"))
        if session is None:
            return _err("invalid or unknown session token")

        handler = self._VERB_HANDLERS[verb]
        try:
            return handler(self, session, args)
        except (LookupError, ValueError, SystemExit, sqlite3.Error) as exc:
            # SystemExit: opsdb.py's own _agent_id() (used by
            # record_activity()) raises SystemExit rather than a typed
            # exception for an unknown agent — a pre-existing,
            # narrower inconsistency in opsdb.py that predates this
            # broker.
            #
            # sqlite3.Error (B1, Code Review REJECT): the PARENT of
            # IntegrityError (a schema-invalid but verb-valid request),
            # OperationalError ("database is locked" past the busy
            # timeout), and InterfaceError (a non-string arg type slipping
            # past validation) — all caught here and returned as a clean
            # _err, so NO database exception can ever escape handle_request
            # and kill serve_forever(). Pre-DB validation (above, per
            # handler) turns the common cases into clean rejections before
            # the DB is touched at all; this catch is the backstop for
            # everything else.
            return _err(str(exc))

    # --------------------------------------------------------------- I/O ---

    def _accept_loop(self, server_sock: socket.socket) -> None:
        while True:
            conn, _ = server_sock.accept()
            # B1 (Code Review REJECT): NOTHING a single connection does may
            # escape and kill serve_forever(). handle_request() already
            # returns _err for every application-level failure, but a
            # broken/closed socket (BrokenPipeError/ConnectionResetError on
            # recv or sendall), a socket timeout, or any other unexpected
            # exception must also cost exactly one connection, never the
            # daemon. This catch-all is the outer backstop; _handle_connection
            # guards sendall itself as well.
            try:
                self._handle_connection(conn)
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _handle_connection(self, conn: socket.socket) -> None:
        # B1: a slow/held-open client cannot wedge this single-threaded loop
        # indefinitely — recv/sendall raise socket.timeout after this bound,
        # which the accept loop's catch-all turns into one dropped connection.
        conn.settimeout(_CONN_TIMEOUT_S)
        peer_uid = _get_peer_uid(conn)
        raw = _recv_request(conn)
        try:
            request = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            response = _err("malformed JSON request")
        else:
            response = self.handle_request(request, peer_uid)
        try:
            conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
        except OSError:
            # B1: a client that sent its request and closed without reading
            # the response (or died mid-write) must not crash the daemon —
            # the DB write, if any, already happened; the lost response is
            # the client's problem, not the broker's.
            pass

    def serve_forever(self) -> None:
        """Binds the socket and accepts connections forever. NOT called
        by anything in this Development pass — see the module docstring
        and ops/reviews/task023-os-provisioning-runbook.md for how a human
        actually starts this as a real, persistent process once
        `ai-developer` exists."""
        sock_path = Path(self.socket_path)
        if sock_path.exists():
            sock_path.unlink()
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server_sock.bind(str(sock_path))
            os.chmod(sock_path, 0o660)  # group ai-pipeline-db — see §3 point 4 of the architecture doc;
                                          # actual group ownership (chgrp) is a provisioning step, see runbook
            server_sock.listen(16)
            self._accept_loop(server_sock)
        finally:
            server_sock.close()


def _get_peer_uid(sock: socket.socket) -> int | None:
    try:
        creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _SO_PEERCRED_SIZE)
    except OSError:
        return None
    _pid, uid, _gid = struct.unpack(_SO_PEERCRED_FMT, creds)
    return uid


def send_request(sock_path: str, request: dict) -> dict:
    """A small, reusable client helper for talking to a running broker —
    used by launch_developer_session.py to call the trusted-only
    `register_session`/`end_session` verbs (never exposed to
    ops/db/opsdb.py's own broker-client mode, which only ever sends the
    five Developer-facing verbs and is meant to run as `ai-developer`, an
    untrusted peer for registration purposes). Kept here, not
    reimplemented a third time, since ops/db/test_opsdb_broker.py's own
    end-to-end test already exercises the identical low-level wire
    protocol this function implements."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.connect(sock_path)
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(65_536)
            if not chunk:
                break
            chunks.append(chunk)
    return json.loads(b"".join(chunks).decode("utf-8"))


def _recv_request(conn: socket.socket) -> bytes:
    chunks = []
    total = 0
    while True:
        chunk = conn.recv(65_536)
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > _MAX_REQUEST_BYTES:
            break
    return b"".join(chunks)


def main() -> None:
    socket_path = os.environ.get("OPSDB_BROKER_SOCKET_PATH", DEFAULT_SOCKET_PATH)
    broker = OpsdbBroker(socket_path=socket_path)
    print(f"opsdb_broker: listening on {socket_path}", file=sys.stderr)
    broker.serve_forever()


if __name__ == "__main__":
    main()
