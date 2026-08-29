#!/usr/bin/env python3
"""ops/control-center/server.py — Phase 2, Milestones 2B1 + 2B2 + 2B3A.

The one controlled application boundary between the browser and
operations.sqlite3 (writes) and the Agent Runtime (real model
invocation). See ops/reviews/cto-milestone2b1-architecture.md,
ops/reviews/cto-milestone2b2-architecture.md, and
ops/reviews/cto-milestone2b3a-architecture.md for the full design
reasoning; this file implements all three, nothing more.

- Loopback-only (127.0.0.1) — never binds 0.0.0.0. There is no network
  exposure to reason about; the only way to reach this server is from a
  process already running on this machine.
- Multi-threaded (http.server.ThreadingHTTPServer, Milestone 2B3A — was
  strictly single-threaded through 2B2). GET/read traffic is never
  bounded (SQLite handles concurrent readers cheaply; a single trusted
  local Founder can't generate enough of it to matter). Only the
  expensive resource — real, costed `claude` subprocess invocations — is
  bounded, by agent_runtime.MAX_CONCURRENT_INVOCATIONS (a non-blocking
  semaphore; a caller that can't get a slot gets an immediate, honest
  "at capacity" result, never a silent wait). Threading alone does not
  make this safe — see "Concurrency correctness" below for what else
  changed and why.
- Exactly two write routes, both POST, both token-gated the same way:
  /api/approvals/<id>/decide (Milestone 2B1) and
  /api/agents/<name>/ask (Milestone 2B2). Every other route is GET-only
  and read-only. There is no SQL endpoint, no shell endpoint, no other
  way for an HTTP request to become a database write or a model
  invocation.
- Every GET route renders through the SAME build_html()/build_roster_html()
  functions the static generators use — no second rendering
  implementation, no drift between a `git commit`-able snapshot and what
  this server shows live.
- /api/approvals/<id>/decide always goes through opsdb.decide_approval().
  /api/agents/<name>/ask always goes through agent_runtime.invoke_agent()
  for the model call and opsdb.start_ask_agent_run()/send_message()/
  end_run() for persistence. These are the only functions in the
  codebase permitted to write approvals.decision, agent_runs, or
  messages respectively.

CONCURRENCY CORRECTNESS (Milestone 2B3A) — read this before assuming a
ThreadingHTTPServer swap alone made anything safe, because it didn't:
- Every sqlite3.Connection is opened fresh per request and closed before
  the request ends (dbutil.connect()/opsdb.connect(), unchanged since
  2B1) — this was already true for an unrelated reason (closing
  promptly) and turns out to be a REQUIRED property for threading, since
  a Python sqlite3.Connection is not safe to share across threads.
- The "one open Ask-Agent run per agent" guard used to be a plain
  SELECT-then-INSERT in this file — correct only by accident, since
  nothing could interleave under the old strictly-sequential server.
  Under real threads it's a genuine check-then-act race. Fixed by moving
  the whole check+insert into one BEGIN IMMEDIATE transaction,
  opsdb.start_ask_agent_run() — verified empirically (5 real concurrent
  threads, zero lost writes) and by finding and fixing a real bug in the
  transaction's own exception handling (see that function's docstring
  and ops/reviews/red-team-milestone2b3a-architecture.md).
- No lock is ever held across invoke_agent()'s multi-second subprocess
  call — every opsdb.py write is a single, brief, individually-committed
  statement. This is what actually makes "another page stays responsive
  during a model call" true, not the threading swap by itself.
- Ctrl+C during an in-flight Ask-Agent call may leave that one `claude`
  subprocess running briefly on its own (bounded by the existing
  timeout/--max-budget-usd caps) — a deliberately accepted limitation,
  not a bug: the resulting agent_runs row reconciles to 'failed' on the
  next server start via the existing _reconcile_orphaned_ask_agent_runs()
  path. A process-tracking registry was considered and rejected as
  unnecessary complexity for what it would buy (Red Team's Milestone
  2B3A review).

FOUNDER AUTHORIZATION — read this before assuming more than it claims:
On every server start a fresh secrets.token_urlsafe(32) is generated,
held only in this process's memory (never written to disk, never
logged, never committed), and embedded as a hidden field in every
Approve/Reject/Discuss/Ask-Agent form this server renders. A POST
without the current token is rejected (403) before the database is
touched — the SAME token gates both write routes; there is one
authorization boundary, not two.

What this proves: the POST came from a page this exact server process
rendered, this run — not a replayed request, not a stale cached page, not
a client-asserted "trust me" flag.

What this does NOT prove: that a human, specifically the Founder, sent
it. Anything on this machine that can make an HTTP request to
127.0.0.1 and first read the served page (to extract the token) can
forge the same POST — including an agent invoked with Bash tool access,
per the still-open Phase 1 risk (risks.id=3: Bash permissions cannot be
scoped below the tool-category level). Milestone 2B2 raises the stakes
of this same limitation: a forged Ask-Agent request doesn't just flip a
decision flag, it triggers a real (though zero-tool, sandboxed) model
invocation. This remains local/single-user trust, narrower in scope than
Phase 1's CLI-flag "authorization" but not a different category of
guarantee. See ops/SECURITY.md.

Usage:
    python3 ops/control-center/server.py [port]   # default 8420
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402 — the only writer; server.py runs its own read-only SELECTs
               # (via dbutil's mode=ro connection) but every write goes through an
               # opsdb.py function. `sqlite3` is imported only for the exception type
               # (sqlite3.OperationalError) a write can raise on lock contention.
import dbutil  # noqa: E402
import agent_runtime  # noqa: E402 — the Agent Runtime boundary (Milestone 2B2)
import generate_overview  # noqa: E402
import generate_pipeline  # noqa: E402
import generate_agents  # noqa: E402
import generate_decisions  # noqa: E402
import generate_meetings  # noqa: E402
import generate_inbox  # noqa: E402
from layout import page, e  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8420

MAX_BODY_BYTES = 64 * 1024  # a decision form is a handful of short fields; anything bigger is not legitimate
MAX_ASK_MESSAGE_CHARS = 8_000  # generous for a real question; small enough to reject a runtime-overflow attempt
AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
APPROVAL_PATH_RE = re.compile(r"^/api/approvals/(\d{1,15})/decide$")  # 15 digits comfortably covers any real id, well under SQLite's 64-bit INTEGER range — rejects absurdly long digit strings up front instead of hitting an OverflowError at the DB layer
ASK_AGENT_PATH_RE = re.compile(r"^/api/agents/([a-z0-9][a-z0-9-]*)/ask$")

# Generated fresh every process start. In-memory only — see module docstring.
SESSION_TOKEN = secrets.token_urlsafe(32)


def _error_page(status: int, title: str, message: str) -> bytes:
    body = f'''
<h1>{e(title)}</h1>
<div class="panel" style="border-color:var(--red);">
  <div style="font-size:12.5px; color:var(--text2);">{e(message)}</div>
</div>
<div style="margin-top:14px;"><a href="/inbox.html" style="color:var(--accent); font-size:12px;">&larr; Back to Inbox</a></div>'''
    return page(title, "inbox.html", body).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "ControlCenter/2B3A"
    timeout = 10  # socket read/write timeout — a stalled client must not hang its request thread
                  # (and, before Milestone 2B3A's ThreadingHTTPServer, the whole server) indefinitely

    def log_message(self, fmt: str, *args) -> None:  # keep default stderr logging, just quieter
        sys.stderr.write(f"[control-center] {self.address_string()} {fmt % args}\n")

    def _send_html(self, status: int, content: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---- GET: read-only rendering, identical build functions to the static generators ----

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        try:
            if path in ("/", "/overview.html"):
                self._send_html(200, generate_overview.build_html().encode("utf-8"))
                return
            if path == "/pipeline.html":
                self._send_html(200, generate_pipeline.build_html().encode("utf-8"))
                return
            if path == "/agents.html":
                conn = dbutil.connect()
                try:
                    self._send_html(200, generate_agents.build_roster_html(conn).encode("utf-8"))
                finally:
                    conn.close()
                return
            if path.startswith("/agents/") and path.endswith(".html"):
                name = path[len("/agents/"):-len(".html")]
                if not AGENT_NAME_RE.match(name):
                    self._send_html(404, _error_page(404, "Not found", "No such agent."))
                    return
                conn = dbutil.connect()
                try:
                    agent_row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
                    if agent_row is None:
                        self._send_html(404, _error_page(404, "Not found", f"No agent named '{name}'."))
                        return
                    self._send_html(200, generate_agents.build_agent_detail(conn, agent_row, token=SESSION_TOKEN).encode("utf-8"))
                finally:
                    conn.close()
                return
            if path == "/decisions.html":
                self._send_html(200, generate_decisions.build_html().encode("utf-8"))
                return
            if path == "/meetings.html":
                self._send_html(200, generate_meetings.build_html().encode("utf-8"))
                return
            if path == "/inbox.html":
                conn = dbutil.connect()
                try:
                    self._send_html(200, generate_inbox.build_html(conn, token=SESSION_TOKEN).encode("utf-8"))
                finally:
                    conn.close()
                return
            self._send_html(404, _error_page(404, "Not found", "No such page."))
        except SystemExit as exc:
            # dbutil.connect() raises SystemExit if the DB file is missing — surface it as a page, not a crash.
            self._send_html(500, _error_page(500, "Database unavailable", str(exc)))
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled GET error on {self.path}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong rendering this page. See the server's terminal output for detail."))

    # ---- POST: the only two write routes in the whole application ----

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        m_decide = APPROVAL_PATH_RE.match(path)
        m_ask = None if m_decide else ASK_AGENT_PATH_RE.match(path)
        if not m_decide and not m_ask:
            self._send_html(404, _error_page(404, "Not found", "No such endpoint."))
            return

        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
            self._send_html(400, _error_page(400, "Bad request", "Missing or oversized request body."))
            return
        body = self.rfile.read(int(length)).decode("utf-8", errors="replace")
        fields = parse_qs(body)

        token = fields.get("token", [""])[0]
        if not secrets.compare_digest(token, SESSION_TOKEN):
            self._send_html(403, _error_page(
                403, "Forbidden",
                "Missing or invalid session token. This form was not served by the currently running "
                "Control Center server — reload the page and try again."))
            return

        if m_decide:
            self._handle_decide(int(m_decide.group(1)), fields)
        else:
            self._handle_ask(m_ask.group(1), fields)

    def _handle_decide(self, approval_id: int, fields: dict) -> None:
        decision = fields.get("decision", [""])[0]
        if decision not in opsdb.DECIDABLE_DECISIONS:
            self._send_html(400, _error_page(400, "Bad request", "decision must be approve, reject, or discuss."))
            return

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001 — e.g. DB file missing/unreadable
            sys.stderr.write(f"[control-center] could not open database for write: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            opsdb.decide_approval(conn, approval_id, decision)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Already decided", str(exc)))
            return
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled write error on approval {approval_id}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong recording this decision. See the server's terminal output for detail."))
            return
        finally:
            conn.close()

        self._redirect("/inbox.html")

    def _handle_ask(self, agent_name: str, fields: dict) -> None:
        redirect_to = f"/agents/{agent_name}.html"

        if agent_name not in agent_runtime.ASK_AGENT_ALLOWLIST:
            self._send_html(404, _error_page(404, "Not enabled",
                                              f"'{agent_name}' is not enabled for Ask-Agent conversation in this milestone."))
            return

        message = fields.get("message", [""])[0].strip()
        if not message:
            self._send_html(400, _error_page(400, "Bad request", "Message must not be empty."))
            return
        if len(message) > MAX_ASK_MESSAGE_CHARS:
            self._send_html(400, _error_page(400, "Bad request",
                                              f"Message exceeds the {MAX_ASK_MESSAGE_CHARS:,}-character limit."))
            return

        thread_id = f"agent-{agent_name}-company"

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for write: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return

        try:
            # Milestone 2B3A: server.py is now multi-threaded
            # (ThreadingHTTPServer), so this can no longer be a plain
            # SELECT-then-INSERT — that was only race-free by accident
            # under the old strictly single-threaded server. One atomic
            # BEGIN IMMEDIATE transaction now does the "no open run
            # exists" check and the row creation together; see
            # opsdb.start_ask_agent_run()'s docstring and
            # ops/reviews/red-team-milestone2b3a-architecture.md for the
            # real race this closes and the exception-handling bug found
            # and fixed while building it. Scoped to Ask-Agent-created
            # runs only (current_activity prefix) — this project's own
            # review-gate workflow uses run-start against these exact
            # agent names (cto/qa) for unrelated task-scoped work, so an
            # unscoped check would 409 a real Founder request behind an
            # unrelated, legitimate open run (Code Review finding,
            # TASK-007).
            try:
                run_id = opsdb.start_ask_agent_run(
                    conn, agent_name, agent_runtime.ASK_AGENT_ACTIVITY_LABEL, agent_runtime.ASK_AGENT_ACTIVITY_LIKE)
            except LookupError as exc:
                self._send_html(404, _error_page(404, "Not found", str(exc)))
                return
            except ValueError as exc:
                self._send_html(409, _error_page(409, "Already in progress", str(exc)))
                return
            except sqlite3.OperationalError as exc:
                # Genuine write-lock contention (the busy timeout expired
                # waiting for BEGIN IMMEDIATE) — a different, honest
                # "busy" case from capacity_exceeded (that's the
                # subprocess semaphore; this is SQLite itself), same
                # clean non-crashing treatment.
                sys.stderr.write(f"[control-center] lock contention starting an Ask-Agent run for {agent_name}: {exc}\n")
                self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
                return

            opsdb.send_message(conn, thread_id, "agent", "founder", message, to_agent=agent_name)

            transcript = self._build_transcript(conn, thread_id, agent_name)
            result = agent_runtime.invoke_agent(agent_name, transcript)

            if result.ok:
                opsdb.send_message(conn, thread_id, "agent", agent_name, result.response_text, to_agent="founder")
                opsdb.end_run(conn, run_id, "ended")
            else:
                # No response message on failure — never fabricate an
                # agent answer. The failed run itself is the honest record.
                sys.stderr.write(f"[control-center] Ask-Agent invocation failed ({result.error_kind}): {result.error}\n")
                opsdb.end_run(conn, run_id, "failed")
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled Ask-Agent error for {agent_name}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong processing this request. See the server's terminal output for detail."))
            return
        finally:
            conn.close()

        self._redirect(redirect_to)

    @staticmethod
    def _build_transcript(conn, thread_id: str, agent_name: str) -> str:
        rows = conn.execute(
            "SELECT from_agent, to_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
            (thread_id,),
        ).fetchall()
        lines = []
        for r in rows:
            speaker = "Founder" if r["from_agent"] == "founder" else agent_name
            lines.append(f"{speaker}: {r['body']}")
        return "\n".join(lines)


def _reconcile_orphaned_ask_agent_runs() -> None:
    """Startup reconciliation (Red Team's Milestone 2B2 review, condition
    6): if a prior server process died mid-request, the agent_runs row it
    created is left open (ended_at IS NULL) forever, and the "one open
    run per agent" guard in _handle_ask would then permanently block all
    future Ask-Agent requests to that agent. Scoped specifically to
    Ask-Agent-created runs via opsdb.reconcile_orphaned_runs() — never
    touches an open run created some other way (e.g. this project's own
    review-gate tracking via run-start), which would be a much broader,
    wrong fix. Goes through opsdb.py like every other write in this
    codebase (CTO's Milestone 2B2 post-implementation review — server.py
    must never hold a raw UPDATE of its own, startup-only or not)."""
    try:
        conn = opsdb.connect()
    except SystemExit:
        return  # DB doesn't exist yet — nothing to reconcile, opsdb.connect() will raise the same on first real use
    try:
        count = opsdb.reconcile_orphaned_runs(conn, agent_runtime.ASK_AGENT_ACTIVITY_LIKE, status="failed")
        if count:
            print(f"reconciled {count} orphaned Ask-Agent run(s) from a prior server process.")
    finally:
        conn.close()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    _reconcile_orphaned_ask_agent_runs()
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    httpd.daemon_threads = True  # explicit — a lingering in-flight request thread must
                                 # never block process exit (default is True in this
                                 # Python version, but stated here rather than relied on)
    print(f"Control Center running at http://{HOST}:{port}/ (loopback only, up to "
          f"{agent_runtime.MAX_CONCURRENT_INVOCATIONS} concurrent agent invocation(s)). "
          f"Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
