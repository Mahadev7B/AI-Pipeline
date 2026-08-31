#!/usr/bin/env python3
"""ops/control-center/server.py — Phase 2, Milestones 2B1 + 2B2 + 2B3A + 2B4.

The one controlled application boundary between the browser and
operations.sqlite3 (writes) and the Agent Runtime (real model
invocation). See ops/reviews/cto-milestone2b1-architecture.md,
ops/reviews/cto-milestone2b2-architecture.md,
ops/reviews/cto-milestone2b3a-architecture.md, and
ops/reviews/cto-milestone2b4-architecture.md for the full design
reasoning; this file implements all four, nothing more.

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
  next server start via the existing _reconcile_orphaned_runs()
  path (which also covers meeting-participant runs — Milestone 2B3B
  conformance correction). A process-tracking registry was considered
  and rejected as
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

FOUNDER IDENTITY VERIFICATION (Milestone 2B4, TASK-013) — layered on top
of, not a replacement for, everything above. Full design:
ops/reviews/cto-milestone2b4-architecture.md,
ops/reviews/security-milestone2b4-threat-model.md,
ops/reviews/red-team-milestone2b4-architecture.md.

A single Founder passphrase (founder_auth.py; salted hashlib.scrypt,
N=2**17, stored outside git in .founder_credential.json, 0600, atomic
writes, never touching operations.sqlite3) now gates a server-side
session: POST /api/login verifies it (rate-limited — see
MAX_FAILED_ATTEMPTS/LOCKOUT_SECONDS below — and, per Security's required
fix C1, the entire check-verify-increment sequence is fully serialized
under _LOGIN_LOCK, closing both the stated brute-force cap and a
concurrent-scrypt memory-exhaustion DoS) and, on success, mints a fresh
in-memory session (SESSIONS dict; HttpOnly/SameSite=Strict cookie; 30-min
idle / 12-hour absolute timeout; wiped on restart, deliberately). EVERY
route — every GET page and every POST write, all 7 pre-2B4 write routes
plus the two new auth routes — now requires either a valid session or
membership in the small unauthenticated allowlist (/login, and the fixed
"setup required" 503 page shown when no credential file exists yet). This
closes risks.id=2 ("Founder approval is not identity-authenticated") for
any local actor that does NOT already share the Founder's own OS-user
filesystem/process principal.

It does NOT close, and cannot by construction close, the case where an
agent runs with Bash tool access under the Founder's own OS user
(risks.id=3, explicitly out of scope this milestone): such an agent can
read or overwrite .founder_credential.json directly (0600 restricts
other OS users, not the file's own owner's other processes), run
founder_auth.py itself, or attach to this running process
(PTRACE_ATTACH, default Linux ptrace_scope) and read SESSIONS/
SESSION_TOKEN out of memory directly — Security's independently-found,
strictly-easier second bypass, not requiring the credential file at all.
Also disclosed, not hidden: the brute-force lockout counter is global,
not per-caller (correctly so — there is exactly one Founder/credential
ever) — which means an attacker already inside this design's own assumed
threat class ("another local process/page reaches the Control Center,"
which can already read /login's CSRF token) can flood /api/login and win
most of each 30s lockout cycle's 5 real-verification slots, denying the
Founder's own genuine logins far more often than not for as long as the
flood runs (Red Team's Milestone 2B4 review, finding F1). No cheap
in-scope fix exists (per-IP limiting is theater on loopback; anything
better requires distinguishing "the real Founder" from a co-resident
process, i.e. risks.id=3's territory) — the remedy is the same one every
other same-OS-user gap in this design relies on: identify and stop the
flooding process, which the Founder can always do as the owning OS user.
See ops/SECURITY.md for the full disclosure.

Usage:
    python3 ops/control-center/server.py [port]   # default 8420
"""
from __future__ import annotations

import re
import secrets
import sqlite3
import sys
import threading
import time
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
import meeting_orchestrator  # noqa: E402 — Executive Meeting orchestration (Milestone 2B3B)
import chief_of_staff  # noqa: E402 — Chief of Staff Founder interface (Phase 3A Part A, TASK-015)
import automation  # noqa: E402 — the automation poller (Phase 3A Part B, TASK-015)
import reviewer_sync  # noqa: E402 — the three synchronous reviewer routes (TASK-017, risks.id=3 reduction milestone)
import founder_auth  # noqa: E402 — Founder credential load/verify (Milestone 2B4)
import generate_overview  # noqa: E402
import generate_pipeline  # noqa: E402
import generate_agents  # noqa: E402
import generate_decisions  # noqa: E402
import generate_meetings  # noqa: E402
import generate_inbox  # noqa: E402
import generate_reviews  # noqa: E402
import generate_releases  # noqa: E402
import generate_automation  # noqa: E402 — Phase 3A Part B (TASK-015)
import generate_active_work  # noqa: E402 — Milestone A (TASK-019)
import generate_task  # noqa: E402 — Milestone A (TASK-019)
from layout import page, e, login_page, setup_required_page  # noqa: E402

HOST = "127.0.0.1"
DEFAULT_PORT = 8420

MAX_BODY_BYTES = 64 * 1024  # a decision form is a handful of short fields; anything bigger is not legitimate
MAX_ASK_MESSAGE_CHARS = 8_000  # generous for a real question; small enough to reject a runtime-overflow attempt
MAX_DECISION_CHARS = 4_000  # a Founder decision on an approval/meeting — generous, still bounded
AGENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
APPROVAL_PATH_RE = re.compile(r"^/api/approvals/(\d{1,15})/decide$")  # 15 digits comfortably covers any real id, well under SQLite's 64-bit INTEGER range — rejects absurdly long digit strings up front instead of hitting an OverflowError at the DB layer
ASK_AGENT_PATH_RE = re.compile(r"^/api/agents/([a-z0-9][a-z0-9-]*)/ask$")
MEETING_CREATE_PATH = "/api/meetings"
MEETING_DECIDE_PATH_RE = re.compile(r"^/api/meetings/(\d{1,15})/decide$")
# Milestone 2B3B round 2 (TASK-011): items 2, 3, 5.
MEETING_REQUEST_PERSPECTIVE_PATH_RE = re.compile(r"^/api/meetings/(\d{1,15})/request-perspective$")
MEETING_FOLLOWUP_PATH_RE = re.compile(r"^/api/meetings/(\d{1,15})/followup$")
MEETING_RETRY_PATH_RE = re.compile(r"^/api/meetings/(\d{1,15})/retry$")
# Phase 3A Part A (TASK-015): a dedicated route, deliberately NOT a
# generalization of ASK_AGENT_PATH_RE — orchestrator stays out of
# ASK_AGENT_ALLOWLIST so there is exactly one way to talk to the Chief of
# Staff, not two. See ops/reviews/cto-phase3a-architecture.md §A.1.
CHIEF_OF_STAFF_ASK_PATH = "/api/chief-of-staff/ask"
# Phase 3A Part B (TASK-015): the kill-switch routes. Same CSRF+session
# gate as every other write route — no new authorization boundary.
AUTOMATION_STOP_PATH = "/api/automation/stop"
AUTOMATION_START_PATH = "/api/automation/start"
# TASK-017 (risks.id=3 reduction milestone), §1.3: the three new
# synchronous, zero-tool reviewer routes — same digit-bounded task-id
# convention as APPROVAL_PATH_RE/MEETING_DECIDE_PATH_RE, one combined
# regex capturing both the task id and which of the three review kinds,
# reusing the existing CSRF+session gate unchanged (§1.3's own framing:
# "reuse of an existing mechanism via a new route," not a new
# authorization boundary).
TASK_REVIEW_PATH_RE = re.compile(r"^/api/tasks/(\d{1,15})/review/(code|security|red-team)$")
# Milestone A (TASK-019): /tasks/<id>.html — same 15-digit bound as
# APPROVAL_PATH_RE/MEETING_DECIDE_PATH_RE (ops/reviews/cto-milestone-a-
# architecture.md §4.1). Read-only GET route, not a write path — no
# relation to TASK_REVIEW_PATH_RE above.
TASK_DETAIL_ID_RE = re.compile(r"^\d{1,15}$")

# Generated fresh every process start. In-memory only — see module docstring.
SESSION_TOKEN = secrets.token_urlsafe(32)

# ---- Milestone 2B4 (TASK-013): Founder session state ----
# All in-memory, wiped on restart — deliberate, same reasoning as
# SESSION_TOKEN itself (architecture doc §4).

SESSION_COOKIE_NAME = "fc_session"
IDLE_TIMEOUT_S = 1800       # 30 minutes since last_seen_at
ABSOLUTE_TIMEOUT_S = 43200  # 12 hours since created_at, regardless of activity

SESSIONS_LOCK = threading.Lock()
SESSIONS: dict[str, dict] = {}  # session id -> {"created_at": float, "last_seen_at": float} (time.monotonic())

# Brute-force lockout — one global counter/timestamp, not per-IP (every
# caller is 127.0.0.1 — per-IP limiting would be theater) and not
# per-identity (there is exactly one Founder/credential, ever).
_LOGIN_LOCK = threading.Lock()
_failed_count = 0
_locked_until = 0.0  # time.monotonic()
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 30

# Credential-file hot-reload + tamper-detection baseline (architecture doc
# §9's optional mtime warning; Red Team's Milestone 2B4 review non-blocking
# note: anchor the baseline at server startup, not only at first check —
# see _prime_credential_mtime_baseline()/_check_credential_gate() below).
_CREDENTIAL_MTIME_LOCK = threading.Lock()
_credential_mtime_baseline: float | None = None


def _error_page(status: int, title: str, message: str) -> bytes:
    body = f'''
<h1>{e(title)}</h1>
<div class="panel" style="border-color:var(--red);">
  <div style="font-size:12.5px; color:var(--text2);">{e(message)}</div>
</div>
<div style="margin-top:14px;"><a href="/inbox.html" style="color:var(--accent); font-size:12px;">&larr; Back to Inbox</a></div>'''
    return page(title, "inbox.html", body, token=SESSION_TOKEN).encode("utf-8")


def _prime_credential_mtime_baseline() -> None:
    """Called once at server startup (main(), before serve_forever) — sets
    the tamper-detection baseline silently (no WARNING logged for whatever
    state the file is in at process start; only a CHANGE detected on a
    later request is worth logging). Red Team's Milestone 2B4 review,
    non-blocking note: anchoring at startup rather than only at the first
    request closes the gap where a modification landing before the very
    first request would otherwise have no prior baseline to compare
    against."""
    global _credential_mtime_baseline
    try:
        _credential_mtime_baseline = founder_auth.CREDENTIAL_PATH.stat().st_mtime
    except OSError:
        _credential_mtime_baseline = None


def _check_credential_gate() -> bool:
    """Fail-closed setup-required check (architecture doc §3), combined
    with the optional mtime tamper-detection warning (§9, open question
    4 — judged cheap enough to build: it's one extra stat-result
    comparison layered on a stat() call this function already has to make
    for the fail-closed check itself). Called as the very first thing in
    both do_GET() and do_POST(), before any other logic — returns False
    (credential file absent -> caller must respond 503) or True (present;
    also updates/logs the tamper baseline as a side effect)."""
    global _credential_mtime_baseline
    try:
        current_mtime = founder_auth.CREDENTIAL_PATH.stat().st_mtime
    except OSError:
        return False
    with _CREDENTIAL_MTIME_LOCK:
        if _credential_mtime_baseline != current_mtime:
            sys.stderr.write(
                "[control-center] WARNING: founder credential file was created or modified while "
                "this server is running — if you did not just run founder_auth.py, treat this as a "
                "real incident.\n")
            _credential_mtime_baseline = current_mtime
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "ControlCenter/2B4"
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

    # ---- Milestone 2B4 (TASK-013): Founder session cookie helpers ----

    def _read_session_cookie(self) -> str | None:
        """Manual, minimal Cookie-header parsing — this app only ever
        sets one cookie, so http.cookies.SimpleCookie's full RFC-6265
        machinery buys nothing here. Never trusts a client-supplied
        session id as anything but a lookup key into the server's own
        SESSIONS dict — see _authenticated_session()."""
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(SESSION_COOKIE_NAME + "="):
                return part[len(SESSION_COOKIE_NAME) + 1:]
        return None

    def _authenticated_session(self) -> dict | None:
        """Cookie lookup + expiry check + last_seen_at bump, all under
        SESSIONS_LOCK (architecture doc §5/§10). An expired session is
        removed and treated exactly like "never logged in" — never a
        silent partial-trust state. Session-fixation-proof by
        construction: the ONLY place a SESSIONS key is ever created is
        _handle_login()'s own secrets.token_urlsafe(32) call; this method
        never inserts anything, it only ever looks up or deletes."""
        session_id = self._read_session_cookie()
        if not session_id:
            return None
        now = time.monotonic()
        with SESSIONS_LOCK:
            session = SESSIONS.get(session_id)
            if session is None:
                return None
            if now - session["last_seen_at"] > IDLE_TIMEOUT_S:
                del SESSIONS[session_id]
                sys.stderr.write("[control-center] session expired (idle)\n")
                return None
            if now - session["created_at"] > ABSOLUTE_TIMEOUT_S:
                del SESSIONS[session_id]
                sys.stderr.write("[control-center] session expired (absolute)\n")
                return None
            session["last_seen_at"] = now
            return session

    def _set_session_cookie(self, session_id: str) -> None:
        # No Secure (plain HTTP over loopback, same justification as the
        # rest of this codebase's loopback-only TLS decision), no
        # Max-Age/Expires (session cookie — disappears when the browser
        # process closes). HttpOnly + SameSite=Strict per architecture
        # doc §4.
        self.send_header("Set-Cookie", f"{SESSION_COOKIE_NAME}={session_id}; HttpOnly; SameSite=Strict; Path=/")

    def _clear_session_cookie(self) -> None:
        self.send_header("Set-Cookie", f"{SESSION_COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")

    def _require_csrf_token(self, fields: dict) -> bool:
        """The SAME check every write route already performs (§6: kept,
        not replaced) — factored out here only because /api/login and
        /api/logout now need it applied identically to the other 7
        routes (Security's Milestone 2B4 threat-model review, condition
        C2), still via do_POST()'s single existing call site, not a
        second parsing path."""
        token = fields.get("token", [""])[0]
        if not secrets.compare_digest(token, SESSION_TOKEN):
            self._send_html(403, _error_page(
                403, "Forbidden",
                "Missing or invalid session token. This form was not served by the currently running "
                "Control Center server — reload the page and try again."))
            return False
        return True

    # ---- GET: read-only rendering, identical build functions to the static generators ----

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        # Milestone 2B4 (TASK-013): fail-closed setup-required check FIRST,
        # before any other logic — architecture doc §3. Applies to every
        # path, including /login itself.
        if not _check_credential_gate():
            self._send_html(503, setup_required_page().encode("utf-8"))
            return

        # Unauthenticated allowlist: /login only (architecture doc §5/§7 —
        # every other GET route, read or write-adjacent, requires a valid
        # Founder session; the "read-only UX while locked" option was
        # deliberately rejected — see §7).
        if path == "/login":
            self._send_html(200, login_page(SESSION_TOKEN).encode("utf-8"))
            return

        if self._authenticated_session() is None:
            self._redirect("/login")
            return

        try:
            if path in ("/", "/overview.html"):
                self._send_html(200, generate_overview.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path == "/active-work.html":
                self._send_html(200, generate_active_work.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path.startswith("/tasks/") and path.endswith(".html"):
                id_part = path[len("/tasks/"):-len(".html")]
                if not TASK_DETAIL_ID_RE.match(id_part):
                    self._send_html(404, _error_page(404, "Not found", "No such task."))
                    return
                conn = dbutil.connect()
                try:
                    task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (int(id_part),)).fetchone()
                    if task_row is None:
                        self._send_html(404, _error_page(404, "Not found", f"No task #{id_part}."))
                        return
                    self._send_html(200, generate_task.build_task_detail(conn, task_row, token=SESSION_TOKEN).encode("utf-8"))
                finally:
                    conn.close()
                return
            if path == "/pipeline.html":
                self._send_html(200, generate_pipeline.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path == "/agents.html":
                conn = dbutil.connect()
                try:
                    self._send_html(200, generate_agents.build_roster_html(conn, token=SESSION_TOKEN).encode("utf-8"))
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
                self._send_html(200, generate_decisions.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path == "/reviews.html":
                self._send_html(200, generate_reviews.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path == "/releases.html":
                self._send_html(200, generate_releases.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path == "/meetings.html":
                self._send_html(200, generate_meetings.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            if path.startswith("/meetings/") and path.endswith(".html"):
                id_part = path[len("/meetings/"):-len(".html")]
                if not id_part.isdigit():
                    self._send_html(404, _error_page(404, "Not found", "No such meeting."))
                    return
                conn = dbutil.connect()
                try:
                    meeting_row = conn.execute("SELECT * FROM meetings WHERE id = ?", (int(id_part),)).fetchone()
                    if meeting_row is None:
                        self._send_html(404, _error_page(404, "Not found", f"No meeting #{id_part}."))
                        return
                    self._send_html(200, generate_meetings.build_meeting_detail(conn, meeting_row, token=SESSION_TOKEN).encode("utf-8"))
                finally:
                    conn.close()
                return
            if path == "/inbox.html":
                conn = dbutil.connect()
                try:
                    self._send_html(200, generate_inbox.build_html(conn, token=SESSION_TOKEN).encode("utf-8"))
                finally:
                    conn.close()
                return
            if path == "/automation.html":
                self._send_html(200, generate_automation.build_html(token=SESSION_TOKEN).encode("utf-8"))
                return
            self._send_html(404, _error_page(404, "Not found", "No such page."))
        except SystemExit as exc:
            # dbutil.connect() raises SystemExit if the DB file is missing — surface it as a page, not a crash.
            self._send_html(500, _error_page(500, "Database unavailable", str(exc)))
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled GET error on {self.path}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong rendering this page. See the server's terminal output for detail."))

    # ---- POST: the write routes in the whole application ----
    # (Milestone 2B3B round 2, TASK-011, added three more — request-perspective,
    # followup, retry — to the four that existed before it. Milestone 2B4,
    # TASK-013, adds two Founder-session routes — /api/login, /api/logout —
    # that ride through the SAME body-parsing + CSRF-token gate as every
    # other route (Security's Milestone 2B4 threat-model review, condition
    # C2/C3) but are exempt from the NEW Founder-session check below, for
    # the reasons given at each check.)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        # Milestone 2B4: fail-closed setup-required check FIRST, before any
        # other logic — architecture doc §3. Applies to every path,
        # including /api/login and /api/logout.
        if not _check_credential_gate():
            self._send_html(503, setup_required_page().encode("utf-8"))
            return

        is_login = path == "/api/login"
        is_logout = path == "/api/logout"
        m_decide = None if (is_login or is_logout) else APPROVAL_PATH_RE.match(path)
        m_ask = None if (is_login or is_logout or m_decide) else ASK_AGENT_PATH_RE.match(path)
        m_meeting_decide = None if (is_login or is_logout or m_decide or m_ask) else MEETING_DECIDE_PATH_RE.match(path)
        m_meeting_request = None if (is_login or is_logout or m_decide or m_ask or m_meeting_decide) else MEETING_REQUEST_PERSPECTIVE_PATH_RE.match(path)
        m_meeting_followup = None if (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request) else MEETING_FOLLOWUP_PATH_RE.match(path)
        m_meeting_retry = None if (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup) else MEETING_RETRY_PATH_RE.match(path)
        is_chief_of_staff_ask = not (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry) and path == CHIEF_OF_STAFF_ASK_PATH
        is_meeting_create = not (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry or is_chief_of_staff_ask) and path == MEETING_CREATE_PATH
        is_automation_stop = not (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry or is_chief_of_staff_ask or is_meeting_create) and path == AUTOMATION_STOP_PATH
        is_automation_start = not (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry or is_chief_of_staff_ask or is_meeting_create or is_automation_stop) and path == AUTOMATION_START_PATH
        m_task_review = None if (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry or is_chief_of_staff_ask or is_meeting_create or is_automation_stop or is_automation_start) else TASK_REVIEW_PATH_RE.match(path)
        if not (is_login or is_logout or m_decide or m_ask or m_meeting_decide or m_meeting_request or m_meeting_followup or m_meeting_retry or is_chief_of_staff_ask or is_meeting_create or is_automation_stop or is_automation_start or m_task_review):
            self._send_html(404, _error_page(404, "Not found", "No such endpoint."))
            return

        # Same existing MAX_BODY_BYTES / utf-8-replace / parse_qs pattern
        # for every route, /api/login and /api/logout included — no new
        # parsing logic (Security's Milestone 2B4 threat-model review,
        # condition C3).
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
            self._send_html(400, _error_page(400, "Bad request", "Missing or oversized request body."))
            return
        body = self.rfile.read(int(length)).decode("utf-8", errors="replace")
        fields = parse_qs(body)

        # Same CSRF token check as every route, now including /api/login
        # (Security's Milestone 2B4 threat-model review, condition C2 —
        # §4 originally stated this only for /api/logout) — verified
        # BEFORE the passphrase is ever touched.
        if not self._require_csrf_token(fields):
            return

        if is_login:
            self._handle_login(fields)
            return
        if is_logout:
            self._handle_logout(fields)
            return

        # Milestone 2B4: centralized Founder-session check, added
        # immediately after the existing CSRF token check, before any
        # _handle_* dispatch (architecture doc §5) — applies to every
        # pre-2B4 write route. Not applied to /api/login (that's the
        # route that CREATES a session) or /api/logout (architecture doc
        # §4: logout must work even from an already-expired/stale
        # session, handled above before reaching here).
        if self._authenticated_session() is None:
            self.log_message(f"rejected {self.command} {path} — no authenticated Founder session")
            self._send_html(401, _error_page(
                401, "Sign-in required",
                'Your Founder session has expired or was never started. <a href="/login">Sign in</a>.'))
            return

        if m_decide:
            self._handle_decide(int(m_decide.group(1)), fields)
        elif m_ask:
            self._handle_ask(m_ask.group(1), fields)
        elif m_meeting_decide:
            self._handle_meeting_decide(int(m_meeting_decide.group(1)), fields)
        elif m_meeting_request:
            self._handle_meeting_request_perspective(int(m_meeting_request.group(1)), fields)
        elif m_meeting_followup:
            self._handle_meeting_followup(int(m_meeting_followup.group(1)), fields)
        elif m_meeting_retry:
            self._handle_meeting_retry(int(m_meeting_retry.group(1)), fields)
        elif is_chief_of_staff_ask:
            self._handle_chief_of_staff_ask(fields)
        elif is_automation_stop:
            self._handle_automation_toggle(False, fields)
        elif is_automation_start:
            self._handle_automation_toggle(True, fields)
        elif m_task_review:
            self._handle_task_review(int(m_task_review.group(1)), m_task_review.group(2), fields)
        else:
            self._handle_meeting_create(fields)

    def _handle_login(self, fields: dict) -> None:
        """POST /api/login. Security's Milestone 2B4 threat-model review,
        condition C1 (non-negotiable): _LOGIN_LOCK is held across the
        ENTIRE check-lockout -> verify -> increment-or-reset critical
        section below, not just the counter update — full serialization
        of /api/login against itself. This is what actually closes both
        the stated 5-attempt brute-force cap (a concurrent flood can no
        longer race past the lockout check before any one request
        registers a failure) and the concurrent-scrypt memory-exhaustion
        DoS (N simultaneous ~128 MiB scrypt calls can no longer run at
        once). hashlib.scrypt releases the GIL during computation
        (independently verified, Red Team's Milestone 2B4 review) so this
        only serializes /api/login against itself — every other route
        stays fully concurrent while a login's scrypt call runs."""
        global _failed_count, _locked_until
        passphrase = fields.get("passphrase", [""])[0]

        with _LOGIN_LOCK:
            now = time.monotonic()
            if now < _locked_until:
                self.log_message("login attempt rejected — currently locked")
                remaining = max(1, int(_locked_until - now) + 1)
                self._send_html(429, login_page(
                    SESSION_TOKEN,
                    error=f"Too many failed attempts. Try again in about {remaining}s.").encode("utf-8"))
                return

            try:
                ok = founder_auth.verify_passphrase(passphrase)
            except founder_auth.CredentialError as exc:
                # Narrow TOCTOU window between _check_credential_gate()'s
                # exists() check and this read (Red Team's Milestone 2B4
                # review, non-blocking note) — treat identically to
                # "setup required," never an unhandled 500.
                sys.stderr.write(f"[control-center] could not read Founder credential during login: {type(exc).__name__}: {exc}\n")
                self._send_html(503, setup_required_page().encode("utf-8"))
                return

            if ok:
                _failed_count = 0
                session_id = secrets.token_urlsafe(32)
                now_m = time.monotonic()
                with SESSIONS_LOCK:
                    SESSIONS[session_id] = {"created_at": now_m, "last_seen_at": now_m}
                self.log_message("founder login succeeded")
                self.send_response(303)
                self._set_session_cookie(session_id)
                self.send_header("Location", "/overview.html")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            _failed_count += 1
            self.log_message(f"founder login FAILED ({_failed_count}/{MAX_FAILED_ATTEMPTS})")
            if _failed_count >= MAX_FAILED_ATTEMPTS:
                _locked_until = time.monotonic() + LOCKOUT_SECONDS
                _failed_count = 0
                self.log_message(f"login lockout triggered — locked for {LOCKOUT_SECONDS}s")
            self._send_html(401, login_page(SESSION_TOKEN, error="Incorrect passphrase.").encode("utf-8"))

    def _handle_logout(self, fields: dict) -> None:
        """POST /api/logout. Deliberately does NOT call
        _authenticated_session() first — architecture doc §4: "I want to
        make sure I'm logged out" must work even from a stale/expired
        session's own still-open tab. Idempotent: logging out twice, or
        with no session cookie at all, is not an error."""
        session_id = self._read_session_cookie()
        if session_id:
            with SESSIONS_LOCK:
                SESSIONS.pop(session_id, None)
        self.log_message("founder session ended (logout)")
        self.send_response(303)
        self._clear_session_cookie()
        self.send_header("Location", "/login")
        self.send_header("Content-Length", "0")
        self.end_headers()

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

            # Everything from here on operates on an ALREADY-CREATED run
            # row (run_id) — Code Review, TASK-009: an unhandled exception
            # anywhere in this block (a send_message() failure, a bug in
            # _build_transcript, anything unexpected) must still end that
            # run as 'failed' before returning an error, or it stays open
            # (ended_at IS NULL) until the next server restart's
            # reconciliation pass — silently blocking every future
            # Ask-Agent request to this same agent in the meantime. That
            # would violate this milestone's own acceptance bar
            # ("failures... in one invocation do not corrupt or block
            # another") just as surely as the race this milestone fixed.
            try:
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
            except Exception:
                try:
                    opsdb.end_run(conn, run_id, "failed")
                except (LookupError, ValueError):
                    pass  # already ended somehow (e.g. by the branch that raised) — nothing more to reconcile
                raise
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

    def _handle_meeting_create(self, fields: dict) -> None:
        """Milestone 2B3B. The entire synchronous flow (select → gather
        positions, bounded-concurrent → synthesize) lives in
        meeting_orchestrator.run_meeting() — this handler only validates
        the HTTP-facing input and maps outcomes to responses, the same
        separation _handle_ask keeps from agent_runtime.invoke_agent()."""
        topic = fields.get("topic", [""])[0].strip()
        if not topic:
            self._send_html(400, _error_page(400, "Bad request", "Topic must not be empty."))
            return
        if len(topic) > meeting_orchestrator.MAX_TOPIC_CHARS:
            self._send_html(400, _error_page(
                400, "Bad request", f"Topic exceeds the {meeting_orchestrator.MAX_TOPIC_CHARS:,}-character limit."))
            return

        try:
            meeting_id = meeting_orchestrator.run_meeting(topic)
        except ValueError as exc:
            self._send_html(400, _error_page(400, "Bad request", str(exc)))
            return
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled meeting-creation error: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong running this meeting. See the server's terminal output for detail."))
            return

        self._redirect(f"/meetings/{meeting_id}.html")

    def _handle_meeting_decide(self, meeting_id: int, fields: dict) -> None:
        decision = fields.get("decision", [""])[0].strip()
        if not decision:
            self._send_html(400, _error_page(400, "Bad request", "Decision must not be empty."))
            return
        if len(decision) > MAX_DECISION_CHARS:
            self._send_html(400, _error_page(400, "Bad request", f"Decision exceeds the {MAX_DECISION_CHARS:,}-character limit."))
            return

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for write: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            opsdb.decide_meeting(conn, meeting_id, decision)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Already decided", str(exc)))
            return
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention deciding meeting {meeting_id}: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] unhandled error deciding meeting {meeting_id}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong recording this decision. See the server's terminal output for detail."))
            return
        finally:
            conn.close()

        self._redirect(f"/meetings/{meeting_id}.html")

    # ---- Milestone 2B3B round 2 (TASK-011): items 2, 3, 5 ----

    def _load_meeting(self, conn, meeting_id: int) -> sqlite3.Row | None:
        """Shared by the three handlers below: fetch a meeting row (every
        column any of them needs — topic, participating_agents) or send a
        404 and return None, so each handler's "does this meeting exist"
        check is one line, not a repeated four. Never used by
        _handle_meeting_decide above — that predates this round and isn't
        part of this diff."""
        row = conn.execute("SELECT topic, participating_agents FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            self._send_html(404, _error_page(404, "Not found", f"No meeting #{meeting_id}."))
        return row

    def _handle_meeting_request_perspective(self, meeting_id: int, fields: dict) -> None:
        """Item 2. Eligibility (allowlisted role, not already a
        participant, meeting not already at the cap) is checked here
        first, as a cheap read-only pre-check against an already-open
        connection — meeting_orchestrator.gather_requested_position()'s
        own opsdb.add_meeting_participant() call is the atomic,
        authoritative re-check of the same conditions (a real, if rare,
        TOCTOU window exists between this pre-check and that one; it is
        closed correctly there, not here — this pre-check only avoids
        spending a real invocation on an obviously-ineligible request)."""
        agent_name = fields.get("agent_name", [""])[0].strip()
        redirect_to = f"/meetings/{meeting_id}.html"

        if agent_name not in agent_runtime.MEETING_PARTICIPANT_ALLOWLIST:
            self._send_html(404, _error_page(
                404, "Not enabled", f"'{agent_name}' is not enabled for Executive Meeting participation."))
            return

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for read: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            meeting_row = self._load_meeting(conn, meeting_id)
            if meeting_row is None:
                return
            participants = opsdb.normalized_participants(meeting_row["participating_agents"])
            if any(p["name"] == agent_name for p in participants):
                self._send_html(409, _error_page(409, "Already a participant", f"'{agent_name}' is already a participant in this meeting."))
                return
            if len(participants) >= agent_runtime.MAX_MEETING_PARTICIPANTS:
                self._send_html(409, _error_page(
                    409, "Meeting full",
                    f"This meeting already has {agent_runtime.MAX_MEETING_PARTICIPANTS} participants — the cap "
                    "(selected + requested combined). No further perspectives can be requested."))
                return
            topic = meeting_row["topic"]
        finally:
            conn.close()

        try:
            ok, error = meeting_orchestrator.gather_requested_position(meeting_id, agent_name, topic)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Cannot add participant", str(exc)))
            return
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention adding a participant to meeting {meeting_id}: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled error requesting a perspective for meeting {meeting_id}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong requesting this perspective. See the server's terminal output for detail."))
            return

        if not ok:
            self._send_html(502, _error_page(
                502, "Perspective request failed",
                f"'{agent_name}' did not provide a real position: {error}. Nothing was added — you may try again."))
            return

        self._redirect(redirect_to)

    def _handle_meeting_followup(self, meeting_id: int, fields: dict) -> None:
        """Item 3. Eligibility is stricter than plain participant
        membership — Red Team's Milestone 2B3B round 2 review, finding 7 /
        condition 6: the agent must have a REAL recorded position in the
        shared `meeting-{id}` positions thread already, not merely be
        listed in `participating_agents` (which stays "present" even for
        a participant whose real invocation failed — that's exactly what
        Retry's own eligibility depends on from the opposite direction)."""
        agent_name = fields.get("agent_name", [""])[0].strip()
        message = fields.get("message", [""])[0].strip()
        redirect_to = f"/meetings/{meeting_id}.html"

        if agent_name not in agent_runtime.MEETING_PARTICIPANT_ALLOWLIST:
            self._send_html(404, _error_page(
                404, "Not enabled", f"'{agent_name}' is not enabled for Executive Meeting participation."))
            return
        if not message:
            self._send_html(400, _error_page(400, "Bad request", "Message must not be empty."))
            return
        if len(message) > MAX_ASK_MESSAGE_CHARS:
            self._send_html(400, _error_page(400, "Bad request", f"Message exceeds the {MAX_ASK_MESSAGE_CHARS:,}-character limit."))
            return

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for read: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            meeting_row = self._load_meeting(conn, meeting_id)
            if meeting_row is None:
                return
            participants = opsdb.normalized_participants(meeting_row["participating_agents"])
            if not any(p["name"] == agent_name for p in participants):
                self._send_html(409, _error_page(409, "Not a participant", f"'{agent_name}' is not a participant in this meeting."))
                return
            has_position = conn.execute(
                "SELECT 1 FROM messages WHERE thread_id = ? AND from_agent = ? LIMIT 1",
                (f"meeting-{meeting_id}", agent_name),
            ).fetchone()
            if has_position is None:
                self._send_html(409, _error_page(
                    409, "No position recorded",
                    f"'{agent_name}' was selected or requested but never produced a real position in this "
                    "meeting (the invocation did not succeed) — there is nothing to follow up on. Try Retry instead."))
                return
            topic = meeting_row["topic"]
        finally:
            conn.close()

        try:
            ok, error = meeting_orchestrator.gather_followup_reply(meeting_id, agent_name, topic, message)
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention on a follow-up in meeting {meeting_id}: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] unhandled follow-up error for meeting {meeting_id}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong sending this follow-up. See the server's terminal output for detail."))
            return

        if not ok:
            self._send_html(502, _error_page(502, "Follow-up failed", f"'{agent_name}' did not respond: {error}. Your message was still recorded — you may try again."))
            return

        self._redirect(redirect_to)

    def _handle_meeting_retry(self, meeting_id: int, fields: dict) -> None:
        """Item 5. All eligibility (agent is a current participant, has no
        recorded position yet, no retry already in progress, retry cap
        not reached) is enforced atomically inside
        opsdb.start_meeting_retry_run() — not duplicated here, unlike the
        other two handlers above, since this route's whole reason for
        being is that exact atomic check (closing a double-click race a
        plain read-then-act pre-check cannot close)."""
        agent_name = fields.get("agent_name", [""])[0].strip()
        redirect_to = f"/meetings/{meeting_id}.html"

        if agent_name not in agent_runtime.MEETING_PARTICIPANT_ALLOWLIST:
            self._send_html(404, _error_page(
                404, "Not enabled", f"'{agent_name}' is not enabled for Executive Meeting participation."))
            return

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for read: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            meeting_row = self._load_meeting(conn, meeting_id)
            if meeting_row is None:
                return
            topic = meeting_row["topic"]
        finally:
            conn.close()

        try:
            ok, error = meeting_orchestrator.retry_position(meeting_id, agent_name, topic)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Cannot retry", str(exc)))
            return
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention starting a retry for meeting {meeting_id}: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] unhandled retry error for meeting {meeting_id}: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong retrying this participant. See the server's terminal output for detail."))
            return

        if not ok:
            self._send_html(502, _error_page(502, "Retry failed", f"'{agent_name}' still did not respond: {error}. You may retry again, up to the retry limit."))
            return

        self._redirect(redirect_to)

    # ---- Phase 3A Part A (TASK-015): Chief of Staff Founder interface ----

    def _handle_chief_of_staff_ask(self, fields: dict) -> None:
        """POST /api/chief-of-staff/ask. Not a generalization of
        /api/agents/<name>/ask — orchestrator deliberately stays out of
        ASK_AGENT_ALLOWLIST (ops/reviews/cto-phase3a-architecture.md
        §A.1): this is the one, dedicated route for talking to the Chief
        of Staff. Mirrors _handle_meeting_create()'s own separation from
        meeting_orchestrator.py — chief_of_staff.py owns the whole
        exchange (state-digest assembly, CONSULT: parsing, consult-
        meeting triggering, persistence); this handler only validates the
        HTTP-facing input and maps outcomes to responses.

        The message-length cap here is meeting_orchestrator.MAX_TOPIC_CHARS
        (2,000), not the larger MAX_ASK_MESSAGE_CHARS (8,000) Ask-Agent
        uses — deliberately: any Founder message to the Chief of Staff may
        become a real Executive Meeting topic if it triggers a CONSULT:
        line, and run_consult_meeting() enforces that same limit on
        `topic`. Capping the Founder's own input here, up front, avoids a
        confusing failure deep inside the consult flow for an otherwise
        well-formed, merely-long message."""
        redirect_to = "/agents/orchestrator.html"

        message = fields.get("message", [""])[0].strip()
        if not message:
            self._send_html(400, _error_page(400, "Bad request", "Message must not be empty."))
            return
        if len(message) > meeting_orchestrator.MAX_TOPIC_CHARS:
            self._send_html(400, _error_page(
                400, "Bad request",
                f"Message exceeds the {meeting_orchestrator.MAX_TOPIC_CHARS:,}-character limit — any message "
                "to the Chief of Staff may become a real Executive Meeting topic, so the same limit applies here."))
            return

        try:
            chief_of_staff.ask_chief_of_staff(message)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Already in progress", str(exc)))
            return
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention starting a Chief of Staff exchange: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled Chief of Staff error: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong processing this request. See the server's terminal output for detail."))
            return

        self._redirect(redirect_to)

    # ---- Phase 3A Part B (TASK-015): the kill switch ----

    def _handle_automation_toggle(self, enabled: bool, fields: dict) -> None:
        """POST /api/automation/stop or /start. Same CSRF+session gate as
        every other write route (do_POST()'s existing dispatch already
        applied both before this is ever called) — the only function
        permitted to write automation_state is
        opsdb.set_automation_enabled(), called only from here. §B.5:
        stopping prevents any NEW automatic action from starting on the
        poller's next check of the flag; it does not forcibly kill an
        already-in-flight invocation — disclosed on /automation.html
        itself, not just here."""
        reason = fields.get("reason", [""])[0].strip() or None

        try:
            conn = opsdb.connect()
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] could not open database for write: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Database unavailable", "Could not open the operational database. See the server's terminal output for detail."))
            return
        try:
            opsdb.set_automation_enabled(conn, enabled, reason=reason, by="founder")
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention toggling automation: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(f"[control-center] unhandled error toggling automation: {type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong changing the automation kill switch. See the server's terminal output for detail."))
            return
        finally:
            conn.close()

        self._redirect("/automation.html")

    def _handle_task_review(self, task_id: int, kind: str, fields: dict) -> None:
        """POST /api/tasks/<id>/review/{code,security,red-team} (TASK-017,
        risks.id=3 reduction milestone, §1.3). Same CSRF+session gate as
        every other write route (do_POST()'s existing dispatch already
        applied both before this is ever called). The whole synchronous
        flow (eligibility checks -> transcript assembly -> the real,
        zero-tool invocation -> verdict handling) lives in
        reviewer_sync.py — this handler only validates the HTTP-facing
        input (the red-team-only `artifact_paths` field) and maps outcomes
        to responses, the same separation _handle_meeting_create/
        _handle_chief_of_staff_ask already keep from their own
        orchestration modules."""
        redirect_to = f"/pipeline.html#task-{task_id}"

        try:
            if kind == "red-team":
                raw = fields.get("artifact_paths", [""])[0]
                artifact_paths = [p.strip() for p in raw.split(",") if p.strip()]
                if len(artifact_paths) > reviewer_sync.MAX_ARTIFACT_PATHS:
                    self._send_html(400, _error_page(
                        400, "Bad request",
                        f"At most {reviewer_sync.MAX_ARTIFACT_PATHS} artifact_paths entries are allowed."))
                    return
                reviewer_sync.run_red_team_review_sync(task_id, artifact_paths)
            elif kind == "code":
                reviewer_sync.run_code_review_sync(task_id)
            else:
                reviewer_sync.run_security_review_sync(task_id)
        except LookupError as exc:
            self._send_html(404, _error_page(404, "Not found", str(exc)))
            return
        except reviewer_sync.ReviewNotEligible as exc:
            self._send_html(400, _error_page(400, "Not eligible", str(exc)))
            return
        except ValueError as exc:
            self._send_html(409, _error_page(409, "Already in progress", str(exc)))
            return
        except sqlite3.OperationalError as exc:
            sys.stderr.write(f"[control-center] lock contention starting a {kind} sync review "
                              f"for task {task_id}: {exc}\n")
            self._send_html(503, _error_page(503, "Busy", "The database is busy right now — please try again in a moment."))
            return
        except Exception as exc:  # noqa: BLE001 — last resort: never let a bug leak a traceback to the client
            sys.stderr.write(f"[control-center] unhandled {kind} sync review error for task {task_id}: "
                              f"{type(exc).__name__}: {exc}\n")
            self._send_html(500, _error_page(500, "Unexpected error", "Something went wrong running this review. See the server's terminal output for detail."))
            return

        self._redirect(redirect_to)


def _reconcile_orphaned_runs() -> None:
    """Startup reconciliation (Red Team's Milestone 2B2 review, condition
    6; extended in Milestone 2B3B's Founder conformance correction — see
    ops/reviews/cto-milestone2b3b-correction-architecture.md): if a prior
    server process died mid-request, the agent_runs row it created is
    left open (ended_at IS NULL) forever. For Ask-Agent, that also
    permanently blocks the "one open run per agent" guard in
    _handle_ask; for a meeting participant there's no such guard, but the
    row still corrupts that agent's derived status ("Working" on a
    meeting that no longer exists) forever with no other code path that
    ever corrects it. Originally scoped to Ask-Agent runs only — the
    Founder's own 2B3B conformance review found this had not been
    extended to meeting-participant runs when 2B3B introduced them,
    despite the identical failure mode. Both patterns are reconciled
    here, via the same generic opsdb.reconcile_orphaned_runs() function —
    never a blanket "close every open run" (that would also incorrectly
    touch this project's own review-gate run-start tracking). Goes
    through opsdb.py like every other write in this codebase (CTO's
    Milestone 2B2 post-implementation review — server.py must never hold
    a raw UPDATE of its own, startup-only or not)."""
    try:
        conn = opsdb.connect()
    except SystemExit:
        return  # DB doesn't exist yet — nothing to reconcile, opsdb.connect() will raise the same on first real use
    try:
        ask_count = opsdb.reconcile_orphaned_runs(conn, agent_runtime.ASK_AGENT_ACTIVITY_LIKE, status="failed")
        if ask_count:
            print(f"reconciled {ask_count} orphaned Ask-Agent run(s) from a prior server process.")
        meeting_count = opsdb.reconcile_orphaned_runs(conn, agent_runtime.MEETING_ACTIVITY_LIKE, status="failed")
        if meeting_count:
            print(f"reconciled {meeting_count} orphaned meeting-participant run(s) from a prior server process.")
        # TASK-011 QA round 2, defect 1: Milestone 2B3B round 2 added a
        # third run type (Orchestrator's participant-selection validation
        # step) with its own current_activity prefix ("Orchestrator:%"),
        # which neither pattern above matches — QA reproduced it staying
        # open=NULL forever (Orchestrator permanently "Working" on
        # /agents.html) even after a restart. Same generic
        # reconcile_orphaned_runs() call, just a third LIKE pattern.
        orchestrator_count = opsdb.reconcile_orphaned_runs(
            conn, agent_runtime.ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE, status="failed")
        if orchestrator_count:
            print(f"reconciled {orchestrator_count} orphaned orchestrator-validation run(s) from a prior server process.")
        # Phase 3A Part A (TASK-015): a fourth run type, a real Chief of
        # Staff invocation ("Chief of Staff:%") — same generic
        # opsdb.reconcile_orphaned_runs() call, distinct LIKE pattern from
        # ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE above so a crash mid-
        # exchange doesn't get mislabeled as an orphaned validation step
        # (or vice versa) even though both are attributed to the same
        # agents.name = "orchestrator" row.
        chief_of_staff_count = opsdb.reconcile_orphaned_runs(
            conn, agent_runtime.CHIEF_OF_STAFF_ACTIVITY_LIKE, status="failed")
        if chief_of_staff_count:
            print(f"reconciled {chief_of_staff_count} orphaned Chief of Staff exchange(s) from a prior server process.")
        # Phase 3A Part B (TASK-015), §B.11: a fifth run type, an automated
        # Code Review invocation ("Automated Code Review:%") — same generic
        # opsdb.reconcile_orphaned_runs() call, distinct LIKE pattern from
        # every existing one so a crash mid-review isn't mislabeled as an
        # orphaned human-supervised code-review-agent run (or vice versa),
        # even though both are attributed to the same agents.name =
        # "code-review" row.
        automated_review_count = opsdb.reconcile_orphaned_runs(
            conn, agent_runtime.AUTOMATED_CODE_REVIEW_ACTIVITY_LIKE, status="failed")
        if automated_review_count:
            print(f"reconciled {automated_review_count} orphaned automated Code Review run(s) from a prior server process.")
        # TASK-017 (risks.id=3 reduction milestone), §1.4: a sixth run
        # type, a synchronous reviewer invocation ("Synchronous review:%")
        # — same generic opsdb.reconcile_orphaned_runs() call, distinct
        # LIKE pattern from every existing one so a crash mid-review isn't
        # mislabeled as an orphaned automated or human-supervised run (or
        # vice versa), even though a synchronous code-review invocation is
        # attributed to the same agents.name = "code-review" row as both
        # of those. Omitting this would reproduce the exact defect
        # TASK-011 QA round 2 already found and fixed once for
        # Orchestrator's validation runs.
        reviewer_sync_count = opsdb.reconcile_orphaned_runs(
            conn, agent_runtime.REVIEWER_SYNC_ACTIVITY_LIKE, status="failed")
        if reviewer_sync_count:
            print(f"reconciled {reviewer_sync_count} orphaned synchronous reviewer run(s) from a prior server process.")
        # §B.11: the new automation_events table's own crash-recovery
        # counterpart — any status='running' row here means the prior
        # process crashed mid-cycle; marked failed/interrupted once, never
        # silently resumed or marked complete, and (per the UNIQUE
        # constraint) its trigger event is never automatically retried.
        stuck_events_count = opsdb.reconcile_stuck_automation_events(conn)
        if stuck_events_count:
            print(f"reconciled {stuck_events_count} stuck automation_events row(s) from a prior server process.")
    finally:
        conn.close()


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    _reconcile_orphaned_runs()  # includes reconcile_stuck_automation_events() — must run before the poller starts
    _prime_credential_mtime_baseline()  # Milestone 2B4: anchor the tamper-detection baseline at startup, not only at the first request (Red Team's Milestone 2B4 review, non-blocking note)
    httpd = ThreadingHTTPServer((HOST, port), Handler)
    httpd.daemon_threads = True  # explicit — a lingering in-flight request thread must
                                 # never block process exit (default is True in this
                                 # Python version, but stated here rather than relied on)

    # Phase 3A Part B (TASK-015), §B.2: the automation poller — a
    # threading.Thread(daemon=True) inside this same process, started
    # right after startup reconciliation, before serve_forever(). Stopped
    # via automation._stop_event.set() below, with a short join() so the
    # process doesn't exit mid-cycle in the common case — belt-and-
    # suspenders on top of daemon_threads=True/thread daemon=True, which
    # already guarantee this thread can't block process exit even if not
    # joined.
    automation_thread = threading.Thread(target=automation.run_poll_loop, name="automation-poller", daemon=True)
    automation_thread.start()

    if founder_auth.credential_exists():
        print(f"Control Center running at http://{HOST}:{port}/ (loopback only, up to "
              f"{agent_runtime.MAX_CONCURRENT_INVOCATIONS} concurrent agent invocation(s)). "
              f"Press Ctrl+C to stop.")
    else:
        print(f"Control Center running at http://{HOST}:{port}/ — Founder setup required: run "
              f"'python3 ops/control-center/founder_auth.py setup' before any route will work.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping.")
    finally:
        automation._stop_event.set()
        automation_thread.join(timeout=5.0)
        httpd.server_close()


if __name__ == "__main__":
    main()
