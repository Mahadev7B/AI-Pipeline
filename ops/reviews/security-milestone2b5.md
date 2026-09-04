# Security Review — TASK-014, Phase 2 Milestone 2B5 ("Review/QA Failure History & Release Readiness Visibility")

**Verdict: PASS**

**Reviewed:** `git show 6763b7d` (implementation commit); new files
`ops/control-center/generate_reviews.py`, `ops/control-center/generate_releases.py`;
edits to `ops/control-center/generate_pipeline.py`, `layout.py`, `server.py`,
`ops/db/derived_state.py`.

## 1. Auth boundary
Traced `Handler.do_GET()` in `server.py` directly. The new branches
(`if path == "/reviews.html"` / `"/releases.html"`, lines 426-431) sit
after the single shared gate — `_check_credential_gate()` (line 378) then
`if self._authenticated_session() is None: redirect("/login")` (line 390-392)
— identically to every pre-existing GET route (`/decisions.html`,
`/meetings.html`, `/inbox.html`, etc.). Zero new/parallel/weaker auth code;
the diff to `server.py` is exactly two `import` lines and two dispatch
branches, both inside the existing `try` block with the existing generic
exception handler (no traceback leakage). No touches to `founder_auth.py`,
`SESSIONS`, `SESSION_COOKIE_NAME`, or any credential file anywhere in the
diff — confirmed via `git show 6763b7d --name-only`.

## 2. XSS / injection into rendered HTML
Every new render site uses `layout.e()` (`html.escape`) before
interpolation: task titles, `display_name()` output (agent names),
`review_type`, `result`, `created_at`, `returned_to_agent`, `scenario`,
`defect_summary`, `version`, `environment`, `release_notes`,
`rollback_plan`, `deployed_at`, and task `status`/`title` in the gap list.

`findings` (JSON array, `review_results.findings`, `NOT NULL DEFAULT '[]'`)
is rendered in `generate_reviews.py::_render_row` as
`f'Findings: {e(row["findings"])}'` — the raw JSON-array *string* passed
straight through `e()`. This is not pretty-printed per-element (a cosmetic
gap, not a security one): `html.escape()` on the whole string neutralizes
`<`, `>`, `&`, `"`, `'` regardless of whether the content is parsed first,
so no XSS vector exists whether or not an individual array element
contained markup. Confirmed `findings` is always written via
`json.dumps(args.findings or [])` in `opsdb.py`'s `review-result` command
(line 884), never raw-interpolated SQL/HTML text.

## 3. Data exposure
`defect_summary`, `reproduction_steps`, `findings`, `release_notes`, and
`rollback_plan` are internal agent-authored process narrative (same data
class already shown elsewhere, e.g. `blockers` on `pipeline.html`), visible
only to an already-authenticated Founder session. No field in this diff
introduces a new category of sensitive data beyond what Milestone 1/2B
already exposes to that same audience. No indication any of these fields
routinely capture out-of-repo file paths or other operationally sensitive
detail beyond ordinary QA/review narrative — did not manufacture a finding
here.

## 4. SQL injection surface
Both `generate_reviews.py` and `generate_releases.py` use only static,
parameterized queries (`conn.execute(sql, (task_id, task_id))` in
`_task_rows`; all other queries take no external input at all — no
f-string/`.format()` SQL construction anywhere in either file. Consistent
with the codebase-wide convention.

## 5. Data integrity / read-only guarantee
Both generators import `connect` from the shared `ops/control-center/dbutil.py`,
which opens `sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True)`
— the same enforced read-only mode used by every other generator (verified
by a real write-refusal test per Milestone 1, per the module's own
docstring). `derived_state.release_readiness_gap()` is a single `SELECT`
with no side effects, matching `company_health()`'s existing pattern.
Neither new generator opens any other connection or write path.

## 6. Credentials / secrets
No diff to `founder_auth.py`, the credential file, `SESSIONS`, or session
cookie logic. Clean no-op on the auth/credential surface, as expected for
a purely additive read-only feature.

## 7. `id="task-{id}"` anchor in `generate_pipeline.py`
`tasks.id` is `INTEGER PRIMARY KEY AUTOINCREMENT` (`ops/db/schema.sql` line 34)
— confirmed by reading the schema directly, not assumed. It can never hold
attacker-controlled or non-numeric content, so unescaped f-string
interpolation into the `id="task-{id}"` attribute carries no injection
risk. Consistent with existing unescaped integer-id interpolation
elsewhere in the same file (e.g. `TASK-{t["id"]:03d}`).

## Conclusion
No new authentication logic, no new write surface, no unescaped
user/agent-controlled text reaching HTML output, no SQL injection surface,
no credential-path changes. Findings above are informational only; none
rise to a rejectable issue.
