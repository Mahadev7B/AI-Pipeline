#!/usr/bin/env python3
"""ops/idea-desk/server.py — the Idea Desk.

Its own program, on its own port, so opening it shows your ideas and nothing
else. That separateness is the Founder's own instruction (DEC-018): the factory
Control Center is a different thing you open separately.

What is deliberately NOT duplicated, because duplicating it would quietly
weaken the security posture the rest of the system rests on:

  * the credential — founder_auth is imported from ops/control-center, so there
    is one passphrase and one scrypt verification path, not two;
  * the database writer — every write shells out to ops/db/opsdb.py, which
    remains the sole writer. This process opens the database read-only and
    could not write to it even if a bug tried to.

Run it:  python3 ops/idea-desk/server.py
Then:    http://127.0.0.1:8421/
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
CONTROL_CENTER = REPO / "ops" / "control-center"
OPSDB = REPO / "ops" / "db" / "opsdb.py"

# This directory first, the Control Center appended after it: both contain a
# server.py, so ordering decides which one `import server` would find.
sys.path.insert(0, str(HERE))
if str(CONTROL_CENTER) not in sys.path:
    sys.path.append(str(CONTROL_CENTER))
import founder_auth  # noqa: E402  — the one credential, shared not copied
import evaluator  # noqa: E402
import pages  # noqa: E402

DB_PATH = (Path(os.environ["OPSDB_PATH"]) if os.environ.get("OPSDB_PATH")
           else REPO / "ops" / "db" / "operations.sqlite3")

HOST = "127.0.0.1"          # loopback only, same as the Control Center
DEFAULT_PORT = 8421         # the Control Center is 8420; this is its own door
MAX_BODY_BYTES = 64 * 1024
IDLE_TIMEOUT_S = 60 * 60
ABSOLUTE_TIMEOUT_S = 12 * 60 * 60
SESSION_COOKIE = "idea_desk_session"

# Bumped whenever what works changes. Shown in the footer and printed on start,
# so "did my pull actually take effect" is a question you can answer by looking
# rather than by guessing.
BUILD = "slice 2 — evaluation is live"

# Per-process, regenerated on every start. A form rendered by a previous run of
# this server is refused by the next one — same reasoning as the Control Center.
SESSION_TOKEN = secrets.token_urlsafe(32)
SESSIONS: dict[str, dict] = {}
SESSIONS_LOCK = threading.Lock()


# ------------------------------------------------------------- reading ------

def _connect() -> sqlite3.Connection:
    """Read-only, always. This process never writes; opsdb.py does."""
    conn = sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _current_text(conn, idea_id: int, row) -> dict:
    """The current wording is the newest edit, or the original when there are
    none. ideas.raw_idea itself is never rewritten — that is what lets the page
    say 'you said, never edited' and be telling the truth."""
    latest = conn.execute(
        "SELECT * FROM idea_edits WHERE idea_id = ? ORDER BY id DESC LIMIT 1", (idea_id,)).fetchone()
    if latest is None:
        return {"current_raw": row["raw_idea"], "current_audience": row["audience"],
                "current_trigger": row["trigger_note"]}
    return {"current_raw": latest["raw_idea"], "current_audience": latest["audience"],
            "current_trigger": latest["trigger_note"]}


def load_ideas() -> list[dict]:
    conn = _connect()
    try:
        out = []
        for row in conn.execute("SELECT * FROM ideas ORDER BY updated_at DESC, id DESC").fetchall():
            item = dict(row)
            item.update(_current_text(conn, row["id"], row))
            last = conn.execute(
                "SELECT recommendation FROM idea_rounds WHERE idea_id = ? ORDER BY round_no DESC LIMIT 1",
                (row["id"],)).fetchone()
            item["recommendation"] = last["recommendation"] if last else None
            out.append(item)
        return out
    finally:
        conn.close()


def load_idea(idea_id: int):
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
        if row is None:
            return None, []
        idea = dict(row)
        idea.update(_current_text(conn, idea_id, row))
        idea["edits"] = [dict(r) for r in conn.execute(
            "SELECT * FROM idea_edits WHERE idea_id = ? ORDER BY id", (idea_id,)).fetchall()]
        rounds = [dict(r) for r in conn.execute(
            "SELECT * FROM idea_rounds WHERE idea_id = ? ORDER BY round_no", (idea_id,)).fetchall()]
        return idea, rounds
    finally:
        conn.close()


# ------------------------------------------------------------- writing ------

class WriteError(Exception):
    """opsdb.py refused the write. Its message is written for the Founder, so
    it is shown as-is rather than replaced with something vaguer."""


def opsdb(*args: str) -> str:
    """Every write in this program goes through here. opsdb.py stays the sole
    database writer; this process never opens the database for writing."""
    env = dict(os.environ)
    proc = subprocess.run([sys.executable, str(OPSDB), *args],
                          capture_output=True, text=True, env=env, timeout=30)
    if proc.returncode != 0:
        message = (proc.stderr or proc.stdout).strip()
        raise WriteError(message.removeprefix("error: ") or "The database refused that.")
    return proc.stdout.strip()


# ------------------------------------------------------------- handler ------

class Handler(BaseHTTPRequestHandler):
    server_version = "IdeaDesk"

    def log_message(self, fmt, *args):
        sys.stderr.write("[idea-desk] %s\n" % (fmt % args))

    # ---- plumbing ----
    def _send(self, status: int, body: bytes, extra_headers: list | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, extra_headers: list | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        for name, value in (extra_headers or []):
            self.send_header(name, value)
        self.end_headers()

    def _session(self) -> dict | None:
        cookie = self.headers.get("Cookie") or ""
        sid = None
        for part in cookie.split(";"):
            part = part.strip()
            if part.startswith(SESSION_COOKIE + "="):
                sid = part[len(SESSION_COOKIE) + 1:]
        if not sid:
            return None
        now = time.monotonic()
        with SESSIONS_LOCK:
            session = SESSIONS.get(sid)
            if session is None:
                return None
            if (now - session["last_seen_at"] > IDLE_TIMEOUT_S
                    or now - session["created_at"] > ABSOLUTE_TIMEOUT_S):
                del SESSIONS[sid]
                return None
            session["last_seen_at"] = now
            return session

    def _read_form(self) -> dict | None:
        length = self.headers.get("Content-Length")
        if length is None or not length.isdigit() or int(length) > MAX_BODY_BYTES:
            self._send(400, pages.error_page(400, "Bad request", "Missing or oversized form."))
            return None
        body = self.rfile.read(int(length)).decode("utf-8", errors="replace")
        fields = parse_qs(body)
        if not secrets.compare_digest(fields.get("token", [""])[0], SESSION_TOKEN):
            self._send(403, pages.error_page(
                403, "Forbidden",
                "This form was not served by the running Idea Desk. Reload the page and try again."))
            return None
        return fields

    @staticmethod
    def _one(fields: dict, name: str) -> str:
        return (fields.get(name, [""])[0] or "").strip()

    # ---- GET ----
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]

        if not founder_auth.credential_exists():
            self._send(503, pages.setup_required_page())
            return
        if path == "/login":
            self._send(200, pages.login_page(SESSION_TOKEN))
            return
        if self._session() is None:
            self._redirect("/login")
            return
        if not DB_PATH.exists():
            self._send(503, pages.error_page(
                503, "No database yet",
                "Run <code>python3 ops/db/opsdb.py init</code> first."))
            return

        try:
            if path == "/":
                self._send(200, pages.list_page(load_ideas(), build=BUILD))
                return
            if path == "/new":
                self._send(200, pages.new_page(SESSION_TOKEN))
                return

            for prefix, render in (("/idea/", "view"), ("/edit/", "edit"), ("/correct/", "correct"),
                                   ("/close/", "close"), ("/approve/", "approve"),
                                   ("/evaluate/", "evaluate")):
                if path.startswith(prefix):
                    rest = path[len(prefix):]
                    if not rest.isdigit():
                        self._send(404, pages.error_page(404, "Not found", "No such idea."))
                        return
                    idea, rounds = load_idea(int(rest))
                    if idea is None:
                        self._send(404, pages.error_page(404, "Not found", "No such idea."))
                        return
                    if render == "edit":
                        self._send(200, pages.new_page(SESSION_TOKEN, idea))
                    elif render in ("correct", "evaluate"):
                        # Both go through the same disclosure: this is the one
                        # action in the Idea Desk that spends real money.
                        self._send(200, pages.idea_page(
                            idea, rounds, SESSION_TOKEN,
                            panel=pages.evaluate_panel(idea, SESSION_TOKEN,
                                                       correcting=(render == "correct"))))
                    elif render == "close":
                        self._send(200, pages.idea_page(idea, rounds, SESSION_TOKEN,
                                                        panel=pages.close_panel(idea, SESSION_TOKEN)))
                    elif render == "approve":
                        if not rounds:
                            self._redirect(f"/idea/{rest}")
                            return
                        self._send(200, pages.idea_page(
                            idea, rounds, SESSION_TOKEN,
                            panel=pages.approve_panel(idea, rounds, SESSION_TOKEN)))
                    else:
                        self._send(200, pages.idea_page(
                            idea, rounds, SESSION_TOKEN,
                            steps=evaluator.progress_for(int(rest))))
                    return

            self._send(404, pages.error_page(404, "Not found", "No such page."))
        except Exception:
            self.log_error("unhandled error rendering %s", path)
            import traceback
            traceback.print_exc(file=sys.stderr)
            self._send(500, pages.error_page(500, "Something broke",
                                             "That is a bug in the Idea Desk, not something you did."))

    # ---- POST ----
    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]

        if not founder_auth.credential_exists():
            self._send(503, pages.setup_required_page())
            return

        fields = self._read_form()
        if fields is None:
            return

        if path == "/api/login":
            passphrase = fields.get("passphrase", [""])[0]
            if not passphrase or not founder_auth.verify_passphrase(passphrase):
                self.log_message("failed sign-in attempt")
                self._send(401, pages.login_page(SESSION_TOKEN, "That passphrase was not recognised."))
                return
            sid = secrets.token_urlsafe(32)
            now = time.monotonic()
            with SESSIONS_LOCK:
                SESSIONS[sid] = {"created_at": now, "last_seen_at": now}
            self._redirect("/", [("Set-Cookie",
                                  f"{SESSION_COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/")])
            return

        if self._session() is None:
            self._send(401, pages.error_page(
                401, "Sign-in required",
                'Your session expired. <a href="/login">Sign in</a>.'))
            return

        try:
            self._dispatch_write(path, fields)
        except WriteError as exc:
            self._send(409, pages.error_page(409, "That was refused", pages.e(str(exc))))
        except Exception:
            import traceback
            traceback.print_exc(file=sys.stderr)
            self._send(500, pages.error_page(500, "Something broke",
                                             "That is a bug in the Idea Desk, not something you did."))

    def _dispatch_write(self, path: str, fields: dict) -> None:
        if path == "/api/create":
            raw = self._one(fields, "raw")
            if not raw:
                self._send(400, pages.error_page(400, "Nothing to save",
                                                 "Write the idea in your own words first."))
                return
            args = ["idea-create", "--raw", raw]
            for flag, name in (("--audience", "audience"), ("--trigger", "trigger")):
                if self._one(fields, name):
                    args += [flag, self._one(fields, name)]
            out = opsdb(*args)
            new_id = out.rsplit("id=", 1)[-1].strip()
            self._redirect(f"/idea/{new_id}")
            return

        prefix, _, rest = path[len("/api/"):].partition("/")
        if not rest.isdigit():
            self._send(404, pages.error_page(404, "Not found", "No such endpoint."))
            return
        idea_id = int(rest)

        if prefix == "edit":
            raw = self._one(fields, "raw")
            if not raw:
                self._send(400, pages.error_page(400, "Nothing to save", "The idea cannot be empty."))
                return
            args = ["idea-edit", "--idea-id", str(idea_id), "--raw", raw]
            for flag, name in (("--audience", "audience"), ("--trigger", "trigger")):
                if self._one(fields, name):
                    args += [flag, self._one(fields, name)]
            opsdb(*args)
            self._redirect(f"/idea/{idea_id}")

        elif prefix == "close":
            how = self._one(fields, "how")
            if how not in ("parked", "dropped"):
                self._send(400, pages.error_page(400, "Bad request", "Park or drop, not something else."))
                return
            args = ["idea-close", "--idea-id", str(idea_id), "--how", how]
            if self._one(fields, "reason"):
                args += ["--reason", self._one(fields, "reason")]
            opsdb(*args)
            self._redirect(f"/idea/{idea_id}")

        elif prefix == "reopen":
            opsdb("idea-reopen", "--idea-id", str(idea_id))
            self._redirect(f"/idea/{idea_id}")

        elif prefix == "approve":
            round_id = self._one(fields, "round_id")
            if not round_id.isdigit():
                self._send(400, pages.error_page(400, "Bad request", "Which round?"))
                return
            opsdb("idea-approve", "--idea-id", str(idea_id), "--round-id", round_id,
                  "--confirm-founder-decision")
            self._redirect(f"/idea/{idea_id}")

        elif prefix in ("evaluate", "correct"):
            idea, rounds = load_idea(idea_id)
            if idea is None:
                self._send(404, pages.error_page(404, "Not found", "No such idea."))
                return
            note = self._one(fields, "note") or None
            if prefix == "correct" and not note:
                self._send(400, pages.error_page(
                    400, "Nothing to correct",
                    "Say what the company got wrong first, in a line or two."))
                return
            try:
                evaluator.start(idea_id, idea, rounds, note)
            except evaluator.EvaluationError as exc:
                self._send(409, pages.error_page(409, "Could not start", pages.e(str(exc))))
                return
            self._redirect(f"/idea/{idea_id}")

        elif prefix == "start":
            # Deliberately NOT titled the same as any other unbuilt thing: when
            # two walls share a title you cannot tell which one you hit, which
            # is exactly how a stale server gets mistaken for a missing feature.
            self._send(200, pages.error_page(
                501, "Start work is not built yet",
                "This is the last piece: handing your approved brief to the factory so it actually "
                "gets built. Your approved brief is stored and stays exactly as you approved it. "
                "<br><br>Evaluating an idea, correcting the company and approving a brief all work "
                "&mdash; this one button does not, yet."))

        else:
            self._send(404, pages.error_page(404, "Not found", "No such endpoint."))


def _ensure_database() -> None:
    """The database is deliberately not in git (it is live state, not source),
    so a fresh clone has none. Create it rather than making the Founder read an
    error and run a command to get an empty file."""
    if DB_PATH.exists():
        return
    sys.stderr.write(f"[idea-desk] No database yet — creating {DB_PATH}\n")
    try:
        subprocess.run([sys.executable, str(OPSDB), "init"], check=True,
                       capture_output=True, text=True, timeout=60)
    except Exception as exc:
        sys.stderr.write(f"[idea-desk] Could not create it: {exc}\n"
                         f"[idea-desk] Run this yourself:  python3 {OPSDB} init\n")


def main() -> None:
    port = int(os.environ.get("IDEA_DESK_PORT", DEFAULT_PORT))
    _ensure_database()
    if not founder_auth.credential_exists():
        sys.stderr.write(
            "[idea-desk] No Founder credential yet. Create one first:\n"
            "            python3 ops/control-center/founder_auth.py setup\n")
    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as exc:
        # Without this the failure is a raw traceback, and the browser keeps
        # talking to whatever is already on the port — so a restart LOOKS like
        # it worked while the old code keeps serving. That exact confusion cost
        # a whole debugging session; say it plainly instead.
        sys.stderr.write(
            f"\n[idea-desk] Could not start: port {port} is already in use.\n"
            f"[idea-desk] {exc}\n\n"
            "  An Idea Desk is ALREADY RUNNING, and it is still serving the code it\n"
            "  started with. Your browser is reaching that one, not this one, which is\n"
            "  why a pull can look like it changed nothing.\n\n"
            "  Stop every running copy first:\n"
            "    Windows      :  Get-Process python | Stop-Process\n"
            "    macOS/Linux  :  pkill -f idea-desk/server.py\n\n"
            "  Then start it again. Or run it on another port to compare:\n"
            "    Windows      :  $env:IDEA_DESK_PORT=8431; python ops\\idea-desk\\server.py\n"
            "    macOS/Linux  :  IDEA_DESK_PORT=8431 python3 ops/idea-desk/server.py\n\n"
            "  Not sure what is going on? Run:  python ops\\idea-desk\\doctor.py\n\n")
        raise SystemExit(1)
    sys.stderr.write(f"[idea-desk] Idea Desk ({BUILD}) on http://{HOST}:{port}/\n")
    sys.stderr.write(f"[idea-desk] reading {DB_PATH} (read-only; opsdb.py does every write)\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[idea-desk] stopped\n")


if __name__ == "__main__":
    main()
