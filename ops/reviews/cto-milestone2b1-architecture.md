# CTO architecture proposal — Phase 2, Milestone 2B1

TASK-006. Scope: introduce the first real write interaction (Founder Inbox
→ Approve / Reject / Discuss) behind one controlled application boundary.
Everything else (Ask-Agent, meeting creation, orchestration, auth beyond
this milestone's stated bar) stays out per the Founder's scope boundary.

## The core problem

Up to Milestone 2A, the Control Center was pure static-site generation:
Python scripts read `operations.sqlite3` read-only and write `.html`
files; there is no process that ever writes to the database on the
Founder's behalf. `opsdb.py` is the only writer, invoked by hand or by an
agent. `approval-decide`'s only gate is a CLI flag
(`--confirm-founder-decision`) that anyone invoking the CLI can pass —
explicitly documented in its own error message as "no real identity
check." The Founder now wants to click Approve/Reject/Discuss in the
browser, which means something has to translate a browser action into a
database write. That "something" is the entire scope of this milestone.

## Requirement recap (from the Founder's brief)

- Browser must never write SQLite directly, never execute `opsdb.py`
  directly.
- Exactly one controlled application boundary: validates the action,
  enforces allowed operations, writes through the approved
  operational-state layer, records audit history, returns updated state.
- `operations.sqlite3` stays the operational source of truth.
- Materially improve on the CLI-flag "authorization." Document precisely
  what's technically enforced vs. what still relies on local/single-user
  trust — no claiming this is solved.
- No arbitrary SQL/shell endpoint. No client-supplied
  `founder_authorized=1` blindly trusted. Concurrency/double-submit must
  be handled and tested.

## Proposed architecture

### 1. One local, loopback-only HTTP server: `ops/control-center/server.py`

Python stdlib only (`http.server.HTTPServer` + a single
`BaseHTTPRequestHandler` subclass, `secrets`, `urllib.parse` — no new
dependency). Started manually by the Founder:
`python3 ops/control-center/server.py` — not auto-started, not a daemon,
not part of any script that runs unattended. Binds explicitly to
`("127.0.0.1", 8420)` — never `0.0.0.0` — so the only way to reach it is
from a process running on this same machine. That is the *first* line of
defense: there is no network exposure to reason about, by construction,
not by firewall configuration someone could forget.

It serves two kinds of routes:

- **GET routes** for all six screens (`/`, `/overview.html`,
  `/pipeline.html`, `/agents.html`, `/agents/<name>.html`,
  `/decisions.html`, `/meetings.html`, `/inbox.html`) — each one calls
  the *exact same* `build_*_html()` function the static generator already
  uses (`generate_overview.build_html()`, etc.), just returning the
  string over HTTP instead of writing it to a file. **Zero duplicate
  rendering logic.** Static generation (`main()` in each script, `git
  commit`-able snapshots) is untouched and still works standalone without
  the server running — the server is an additional way to view the same
  build output live, not a replacement.
- **One POST route**: `POST /api/approvals/<id>/decide` — the entire
  write surface. No other POST route exists. No generic `/query`, no
  `/exec`, no file-write endpoint. This is the "controlled application
  boundary" the Founder asked for, and it is singular by construction —
  there's nowhere else in the codebase a browser request can turn into a
  database write.

### 2. The write boundary itself: `decide_approval()` moves into `opsdb.py`

Today `cmd_approval_decide` (the CLI entry point) does the `UPDATE`
inline, with a real, previously-undetected bug: it never checks that
`decision` is still `'pending'` first, so calling it twice — or calling
it once someone already decided — silently overwrites `decision` and
`decided_at`. That's exactly the "re-decide a resolved approval" failure
mode the Founder's QA list calls out.

Fix: extract a plain function,
`decide_approval(conn, approval_id, decision) -> dict`, that does the
write **atomically and conditionally** —

```sql
-- discuss: only from pending
UPDATE approvals SET decision='discuss', decided_at=<now>
WHERE id=? AND decision='pending'

-- approve / reject: from pending OR discuss (discuss is a checkpoint,
-- not a terminal state — see "Decision states" below)
UPDATE approvals SET decision=?, decided_at=<now>
WHERE id=? AND decision IN ('pending','discuss')
```

then checks `cursor.rowcount`. Zero rows updated means either the
approval doesn't exist (`LookupError`) or it's already in a terminal
state / already in `discuss` (`ValueError`, message states the current
decision so the caller can show something honest, not a generic
"failed"). This one function becomes the **only** code path that ever
writes `approvals.decision` — both the CLI command and the new server
call it, so there is no drift between "decide via terminal" and "decide
via browser." `cmd_approval_decide` becomes a thin wrapper that still
requires `--confirm-founder-decision` (unchanged — that friction gate for
direct CLI/agent use stays exactly as documented) and translates
`ValueError`/`LookupError` into a clean CLI error instead of a traceback.

Using SQLite's own transactional `UPDATE ... WHERE` as the concurrency
control means double-submit and true concurrent requests are handled the
same way, by the database, not by server-side locking we'd have to get
right ourselves. `server.py` additionally runs as a single-threaded
`HTTPServer` (not `ThreadingHTTPServer`) — requests are handled one at a
time, so there is no in-process race to reason about either. That is a
deliberate "smallest appropriate" choice: threading would add real
complexity (shared connection handling, lock discipline) to solve a
problem the atomic `UPDATE` already solves at the data layer. Red Team
should still make QA prove the atomic `UPDATE` is what's doing the work
(via concurrent requests from a test harness), not just rely on
single-threading as an accident of implementation.

### 3. Decision states: `pending → {approve, reject, discuss}`, `discuss → {approve, reject}`

The schema already allows `decision IN ('approve','reject','discuss','pending')`
— `discuss` was anticipated but never wired to real behavior. Per the
Founder's brief ("DISCUSS should... persist the Founder's decision state
as discuss and leave the approval visibly requiring follow-up"), `discuss`
is **not** a fourth terminal outcome — it's a checkpoint that keeps the
approval out of the "still fully open" bucket but visibly distinct from
resolved. Inbox queries `WHERE decision IN ('pending','discuss')` (not
just `'pending'`) so a discussed item never silently vanishes from view;
it renders in a separate "Needs follow-up" section instead of the
"Awaiting decision" section. `approve` and `reject` are terminal — no
transition out of them exists in `decide_approval()`, by construction.
Re-clicking Discuss on an already-discussed item is rejected the same
clean way as any other re-decision (rowcount 0) — one flag is enough,
repeat clicks are inert, not silently accepted as new state.

This is explicitly **not** Ask-Agent or a live conversation, per the
Founder's scope boundary — it's one bit of state (`discuss`) plus the
timestamp already on the row. No new table, no message thread. If a
future milestone builds Ask-Agent, `discuss` is the natural trigger for
"this approval has a Founder note pending an agent response" — that's a
2B2+ decision, not made here.

### 4. Founder-session token — the real, honest improvement over the CLI flag

On every server start, `server.py` generates a fresh
`secrets.token_urlsafe(32)`, held only in the running process's memory —
**never written to disk, never committed, never logged**. Every page the
server renders embeds that token as a hidden field in each
Approve/Reject/Discuss `<form>`. `POST /api/approvals/<id>/decide` checks
the submitted `token` field against the in-memory value *before* touching
the database; a mismatch or missing token gets `403` and no write occurs,
full stop — that's the "no client-provided value blindly trusted" bar,
now technically enforced at the boundary instead of asserted by a CLI
flag's honor system.

**What this proves:** the POST came from a form that was rendered by
*this specific server process, this run* — not a replayed request, not a
request built from a stale cached page, not an old bookmark, not a
request to a URL nobody who loaded the live page would even know exists
without reading page source or docs.

**What this does not prove — stated plainly, because the Founder was
explicit not to overclaim:** it does not distinguish a human Founder from
any other local process. Anything with the ability to make an HTTP
request to `127.0.0.1:8420` and first read the served page (to extract
the token) can forge the same POST — and per the still-open Phase 1 risk
(`risks.id=3`, "Bash permissions cannot be scoped below the tool-category
level"), an agent invoked with Bash tool access already has exactly that
ability on this machine today. So this milestone narrows the attack
surface (no network exposure; no replay of an old request; no blind
trust of a client-asserted flag) but does **not** close the
human-vs-agent distinction — that remains local/single-user trust,
identical in kind to Phase 1's, just smaller in scope. Security's review
must test this directly (see gate list below) and the write-up must state
this without softening it.

### 5. Audit trail — reuse what already exists, don't invent a new table

`approvals.decision` + `approvals.decided_at` **is** the audit record —
it's already a single append-once-effectively field (the atomic `UPDATE`
makes it truly write-once per terminal state) with a timestamp. No new
audit table. I looked at whether a Founder decision should also appear in
`agent_activity` (the "Just Happened" feed on Overview) — that table is
keyed to `agent_id` (`NOT NULL REFERENCES agents(id)`) and represents
*agent* activity; a Founder action forced into it would be a data-model
inconsistency (a human action wearing an agent's column) and is not even
structurally possible without a schema change. A real "Founder + agent
unified activity
timeline" is a reasonable future ask but is out of scope for 2B1 — noting
it here rather than silently doing nothing or silently hacking it in.

### 6. Where the Inbox lives

Founder Inbox gets promoted to its own screen, `inbox.html`, added as a
6th nav link (`layout.py`'s `NAV_LINKS`) — the same treatment Meetings got
in 2A. The full field set the Founder specified (request, requesting
agent, why, recommendation, alternatives, expected cost, risks,
consequence-if-not-approved) needs real layout room; Overview's existing
compact "Founder Inbox" panel becomes a *summary* (count + the two/three
most recent, linking out to `inbox.html`), the same pattern already used
for "Active Now" linking out to Agent Detail. `generate_inbox.py` is new,
following the same module shape as the other four 2A generators
(`build_html(conn)`, imports `layout`/`dbutil`).

`inbox.html` still gets a static-generated snapshot via
`generate_inbox.py`'s own `main()`, for consistency with every other
screen and so `git log` still shows real state over time — but its
Approve/Reject/Discuss forms point at `/api/approvals/<id>/decide`,
which only resolves if `server.py` is currently running. The static
snapshot carries a visible, honest banner: "Actions on this page require
`python3 ops/control-center/server.py` running — this file is a
point-in-time snapshot." That is not "a control that appears interactive
but doesn't work" — the form *does* work, contingent on the same backend
any served page depends on; the banner exists so opening the file
straight from disk doesn't create false expectations.

### 7. What is explicitly NOT built here

No JavaScript (forms are plain HTML `method="POST"`, server responds with
an HTTP 303 redirect back to `inbox.html` after a successful decision —
standard POST/redirect/GET, so refreshing the result page never
re-submits). No session/cookie system, no login form, no user table —
those would be real identity infrastructure and the Founder was explicit
this milestone should not claim identity is solved. No TLS (loopback-only
traffic never leaves the machine's kernel, so there is no network
attacker positioned to intercept it — adding TLS here would be complexity
solving a threat that doesn't exist at this network boundary). No
threading. No new tables, no new columns, no schema migration.

## Why this is "smallest appropriate," not smaller

Could this be even smaller — e.g., a "confirm" link with a token in the
URL query string instead of a full HTTP server? Considered and rejected:
a GET-based confirm link would put the decision in server logs and
browser history as an idempotent-looking GET (semantically wrong — a GET
should never mutate state) and offers no natural place to render the
Inbox screen itself. The chosen design is the smallest thing that
actually satisfies "the browser must not write SQLite directly / must
not run opsdb.py directly, and there must be one controlled boundary" —
anything smaller stops being a real boundary.

## Files touched

- `ops/db/opsdb.py` — extract `decide_approval()`, fix the pending-check
  bug, `cmd_approval_decide` becomes a thin wrapper (bug fix + refactor,
  no behavior change to the CLI's flag requirement).
- `ops/control-center/server.py` — new.
- `ops/control-center/generate_inbox.py` — new.
- `ops/control-center/layout.py` — add `inbox.html` to `NAV_LINKS`.
- `ops/control-center/generate_overview.py` — `render_inbox()` becomes a
  summary-plus-link instead of the full list (no write forms move here).
- `ops/DATA_MODEL.md` — document the `discuss` state transition rule
  under "Rules," since it was previously unspecified.
- `ops/SECURITY.md` — add the token-boundary model and its explicit
  limitation under "Open items," so it isn't only findable in a review
  doc.

## Open questions for Red Team

1. Is `pending/discuss → approve/reject`, `pending → discuss`,
   `discuss → discuss` rejected, the right state machine, or should
   `discuss` be allowed to revert to `pending`?
2. Is the loopback-only bind + per-run in-memory token sufficient, or
   does Red Team want an additional gate (e.g., requiring the Founder to
   copy a startup-printed code once) given this is the first real write
   path in the whole system?
3. Any objection to reusing `opsdb.py`'s writable `connect()` (not a
   read-only connection) inside `server.py`, given `server.py` now
   becomes the second process (after the CLI) allowed to hold a writable
   handle to `operations.sqlite3`?
