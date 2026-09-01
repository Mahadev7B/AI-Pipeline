# Security Review — Milestone D (TASK-022): Project/Phase Progress

Scope: focused review, mirroring the Milestone A/B/C security review pattern
in this DEC-009 sequence — not a full-application audit. Reviewed against
`ops/reviews/cto-milestone-d-architecture.md` and `ops/reviews/design-review-milestone-d.md`.

## Files reviewed
- `ops/db/schema.sql` (`phases` table definition, lines ~392-420)
- `ops/db/opsdb.py` (`_phase_row_exists`, `cmd_phase_add`, `cmd_phase_set_status`, and their
  argparse subcommand wiring, lines ~548-602, ~1626-1649)
- `ops/db/derived_state.py` (`phase_progress_rows()`, `founder_readiness_summary()`,
  lines ~1022-1087)
- `ops/control-center/generate_progress.py` (full file — new `/progress.html` page)
- `ops/control-center/server.py` (route registration for `/progress.html`, auth-gate
  placement, `do_POST` route table for any new write route)
- `ops/control-center/layout.py` (`e()` escape helper, nav wiring)

## Findings

### 1. Auth boundary — PASS
`/progress.html` is registered inside `do_GET()`'s route dispatch (server.py:482-489),
which sits *after* the `_authenticated_session()` check at line 421-423 (redirects to
`/login` if no valid session) and *after* the fail-closed credential-gate check at
line 409. This is byte-for-byte the same placement/pattern as `/risks.html`,
`/decisions.html`, and every other authenticated GET route — no bypass path, no new
auth code introduced.

### 2. Write surface — PASS
Grepped `do_POST()`'s entire route table (all `/api/*` regex/path constants and their
handlers) — there is no `/api/phases/*` or any other route that writes to the `phases`
table. The only two writers are the CLI subcommands `phase-add`/`phase-set-status` in
`opsdb.py`, exactly as claimed. Both use fully parameterized `?`-placeholder SQL (no
string-built/f-string SQL anywhere in either function) — no SQL injection surface.
`cmd_phase_add` explicitly pre-checks `--parent-id` existence via `_phase_row_exists()`
before insert (raising a clean `SystemExit` rather than relying solely on the FK
constraint); `opened_decision_id`/`closed_decision_id`/`task_id` rely on SQLite's own
FK enforcement (`PRAGMA foreign_keys=ON` at `connect()`), which is an acceptable,
consistent-with-precedent choice given these are CLI-only, operator-trusted inputs,
not web-exposed. `status` is constrained at both the argparse (`choices=[...]`) and
DB (`CHECK` constraint) layers.

### 3. Injection/XSS — PASS
Every free-text field pulled from the DB and rendered into HTML in
`generate_progress.py` — `row["name"]` (including when lower-cased/space-replaced to
build the `id="tree-..."` anchor attribute), `row["note"]`, `t["title"]` (task title),
decision dates — is passed through `layout.e()`, which calls `html.escape()`. This is
the same escaping helper/pattern used throughout the rest of the app (`generate_risks.py`,
`generate_costs.py`, etc.) per the Milestone-1 rule referenced in `layout.py`'s
docstring. A phase `name` or `note` containing `<script>` or similar cannot inject,
since it's DB-sourced text always routed through `e()` before interpolation, with no
raw f-string field left unescaped in the file.

### 4. Path traversal / route handling — PASS
`/progress.html` is a fixed literal-string route match (`if path == "/progress.html":`)
with a single static call to `generate_progress.build_html(token=SESSION_TOKEN)` — no
templating, no filesystem path built from user input, identical shape to every other
static-page route on this server. No new route-parsing logic introduced.

### 5. New-risk-specific check — PASS, no material new exposure
- `phases.note` and the phase tree only surface *decision references* (id + date,
  already public/authenticated content matching `decisions.html`), status, and
  milestone counts — no new category of sensitive data (no secrets, no unresolved-risk
  detail beyond what `risks.html` already exposes) is introduced by this page.
- The "Right now" panel and readiness booleans (`ui_100pct_complete`,
  `exploratory_testing_ready`) are pure GET-time, read-only derived computations from
  `founder_readiness_summary()`/`phase_progress_rows()` — both plain parameterized
  SELECTs with no external input. Nothing about these values can be manipulated from
  the web side; they can only be changed by the CLI path (`phase-set-status`), which is
  out of scope for a web-exposed attacker. `founder_readiness_summary()`'s design (deriving
  from named child rows rather than trusting a parent row's own status) is a sound
  correctness/integrity choice, not a security gap.

## Not covered in this review (per focused scope)
- No re-audit of session/CSRF mechanics, credential-gate architecture, or general
  auth infrastructure — inherited unchanged from prior milestones/TASK-017 and already
  reviewed there; this milestone was confirmed not to weaken any of it.
- No live server testing was performed for this review — static code reading
  (route registration ordering, escaping call sites, parameterized-query verification,
  do_POST route-table grep) was sufficient to reach a confident verdict for this
  narrow, read-only, CLI-write-only milestone. If the human wants a live confirmation
  (e.g. unauthenticated-probe / tampered-session / stored-XSS-payload-via-CLI-insert
  testing) it can be run as a separate interactive session per the established
  scratch-clone convention.

## Verdict: PASS

No security or privacy issues found. This milestone adds zero new HTTP write surface,
reuses the existing, unmodified auth gate correctly, and consistently escapes all
DB-sourced free text before HTML interpolation.
