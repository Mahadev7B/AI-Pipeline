#!/usr/bin/env python3
"""ops/control-center/server.py — Phase 2, Milestone 2B1.

The one controlled application boundary between the browser and
operations.sqlite3. See ops/reviews/cto-milestone2b1-architecture.md for
the full design reasoning; this file implements it, nothing more.

- Loopback-only (127.0.0.1) — never binds 0.0.0.0. There is no network
  exposure to reason about; the only way to reach this server is from a
  process already running on this machine.
- Single-threaded (http.server.HTTPServer, not Threading...) — requests
  are handled one at a time, by construction, not as an accident.
- Exactly one write route: POST /api/approvals/<id>/decide. Every other
  route is GET-only and read-only. There is no SQL endpoint, no shell
  endpoint, no other way for an HTTP request to become a database write.
- Every GET route renders through the SAME build_html()/build_roster_html()
  functions the static generators use — no second rendering
  implementation, no drift between a `git commit`-able snapshot and what
  this server shows live.
- The one write route always goes through opsdb.decide_approval() — the
  same function the CLI's `approval-decide` command calls. There is
  exactly one function in the whole codebase permitted to write
  approvals.decision.

FOUNDER AUTHORIZATION — read this before assuming more than it claims:
On every server start a fresh secrets.token_urlsafe(32) is generated,
held only in this process's memory (never written to disk, never
logged, never committed), and embedded as a hidden field in every
Approve/Reject/Discuss form this server renders. A POST without the
current token is rejected (403) before the database is touched.

What this proves: the POST came from a page this exact server process
rendered, this run — not a replayed request, not a stale cached page, not
a client-asserted "trust me" flag.

What this does NOT prove: that a human, specifically the Founder, sent
it. Anything on this machine that can make an HTTP request to
127.0.0.1 and first read the served page (to extract the token) can
forge the same POST — including an agent invoked with Bash tool access,
per the still-open Phase 1 risk (risks.id=3: Bash permissions cannot be
scoped below the tool-category level). This remains local/single-user
trust, narrower in scope than Phase 1's CLI-flag "authorization" but not
a different category of guarantee. See ops/SECURITY.md.

Usage:
    python3 ops/control-center/server.py [port]   # default 8420
"""
from __future__ import annotations

import re
import secrets
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402 — the only writer; server.py never touches sqlite3 directly
import dbutil  # noqa: E402
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
AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
APPROVAL_PATH_RE = re.compile(r"^/api/approvals/(\d+)/decide$")

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
    server_version = "ControlCenter/2B1"
    timeout = 10  # socket read/write timeout — a stalled client must not hang this single-threaded server indefinitely

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
                    self._send_html(200, generate_agents.build_agent_detail(conn, agent_row).encode("utf-8"))
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

    # ---- POST: the one write route ----

    def do_POST(self) -> None:
        m = APPROVAL_PATH_RE.match(self.path.split("?", 1)[0])
        if not m:
            self._send_html(404, _error_page(404, "Not found", "No such endpoint."))
            return
        approval_id = int(m.group(1))

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
                "Control Center server — reload /inbox.html and try again."))
            return

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


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    httpd = HTTPServer((HOST, port), Handler)
    print(f"Control Center running at http://{HOST}:{port}/ (loopback only). Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
