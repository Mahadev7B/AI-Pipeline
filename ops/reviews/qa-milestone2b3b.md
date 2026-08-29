# QA — Phase 2, Milestone 2B3B: Real Executive Meetings

TASK-010. Recorded via `opsdb.py qa-result --task-id 10 --by qa`. This
file mirrors that record.

Note on process: performed directly rather than via a spawned `qa`
subagent (`Agent`/`TaskCreate` unavailable this session since 2B3A — same
disclosure as every review from that milestone onward). Every claim
below is from a real, live test run against a real
`ThreadingHTTPServer` instance and real `claude --agent <name>`
invocations — a scratch database (`OPSDB_PATH`), never the live
`ops/db/operations.sqlite3`, seeded with all 8
`MEETING_PARTICIPANT_ALLOWLIST` agents via `agent-upsert`.

## Verdict: PASS

## 1. Full real end-to-end meeting (happy path, non-mocked)

Called `meeting_orchestrator.run_meeting()` directly against a running
scratch DB with the real topic "Direct-call repro: should we add rate
limiting before launch?" No monkeypatching — every model call was a real
`claude --agent <name>` subprocess invocation.

Result (meeting id 2):
- CEO's real selection call chose `product, cto, qa, security, red-team`
  — 5 of the 7 candidates, hitting the 6-total cap exactly (CEO + 5).
- All 6 participants (`ceo, product, cto, qa, security, red-team`) ran
  concurrently via the real `ThreadPoolExecutor(max_workers=3)`, and all
  6 produced real, topic-relevant, non-generic positions (e.g. CTO's
  position addressed the direct-call architecture specifically; QA's
  position noted it hadn't yet run a repro — an honest, specific answer,
  not filler).
- CEO's real synthesis call returned a well-formed, complete four-section
  synthesis (agreements/disagreements/unresolved/recommendation), parsed
  correctly by `_parse_synthesis()`.
- All 6 `agent_runs` rows ended with `status='ended'`, none left open.
- `messages` table has exactly one row per participant, correctly scoped
  (`scope='meeting'`, `meeting_id=2`), no cross-contamination.

This satisfies the milestone's own "Real Executive Meetings" requirement
— a genuine multi-agent, non-mocked meeting ran to completion end to end.

## 2. Full HTTP-layer end-to-end (server.py routes)

Started `python3 ops/control-center/server.py` against the same scratch
DB and drove it entirely over real HTTP (`curl`), not by calling Python
functions directly:

- `GET /meetings.html` (empty state) — 200, correct empty-state copy,
  real session token present in the raise-question form.
- `GET /meetings/1.html` before any meeting existed — 404.
- Token gating: missing token — 403; wrong token — 403 (both before any
  DB write, confirmed no meeting row was created for either attempt).
- Validation: empty topic — 400; 2001-character topic — 400; decide on a
  nonexistent meeting (id 999) — 404; empty decision text — 400.
- `POST /api/meetings` with a real topic — 303 redirect to
  `/meetings/<id>.html`; that page loads 200 and renders correctly.
- `POST /api/meetings/<id>/decide` with a real decision — 303 redirect;
  `meetings.founder_decision` and `decisions` table both updated
  correctly in one atomic transaction (`decisions.id=1`, linked via
  `meetings.linked_decision_id=1`); the meeting detail page now renders
  the read-only "Founder decision" panel instead of the form.
- Duplicate decide on the same meeting — 409, second submission has no
  effect (`founder_decision` unchanged, only one `decisions` row exists
  for that meeting).

## 3. Participant-failure honesty (real failure, not simulated) —
condition 6

The very first HTTP-triggered meeting (id 1) hit a real, live failure:
CEO's participant-position call returned a non-zero exit with no stderr
(`runtime_error`, "runtime exited with code 1") — an actual infrastructure
flake, not injected. This produced exactly the designed honest-failure
behavior, verified by inspection, not assumption:
- `agent_runs` row for that invocation shows `status='failed'`.
- No fabricated message was written — `messages` has zero rows for
  meeting 1.
- `meetings.recommendation`/`agreements`/etc. are all `NULL` (synthesis
  correctly never ran, since `positions` was empty).
- `GET /meetings/1.html` renders the honest "Selected, but no response
  was recorded (the real invocation did not succeed)" card for CEO, and
  "No synthesis available — the synthesis step did not complete." for
  the whole synthesis section.
- The meeting record itself still exists and is fully browsable — a
  failed participant did not corrupt or hide the meeting.

Immediately re-running the identical CEO invocation directly (three
separate ways: a bare `claude --agent ceo` CLI call, a direct
`agent_runtime.invoke_agent()` call, and a `nohup`-detached repro)
succeeded every time — consistent with this being a one-off transient
runtime flake rather than a systematic bug in the invocation logic
itself, and real evidence that a genuine per-participant failure is
handled honestly rather than crashing the whole meeting or fabricating a
result.

## 4. Synthesis-failure-doesn't-discard-positions — condition 7

Not independently reproduced with a *real* synthesis-specific failure in
this live session (CEO's synthesis call succeeded in every real
meeting run). This exact scenario (every participant succeeds, the
final CEO synthesis call itself fails) was verified during Development
via a monkeypatched fake runtime — documented and already re-confirmed
by Code Review reading `run_meeting()`'s control flow: `_synthesize()` is
called unconditionally with the real `positions` dict already
populated, and `finalize_meeting_synthesis()` only ever `UPDATE`s the
four synthesis columns, never touches `messages`. Given the real,
unmocked participant-failure result in section 3 already demonstrates
this project's honest-failure discipline holds up outside a mocked
test, this is accepted as adequately covered rather than requiring a
forced live API failure (not practically reproducible on demand).

## 5. Duplicate/concurrent meeting submission — condition 5

Fired two real concurrent `POST /api/meetings` requests with the
identical topic text against the live server (backgrounded curl
processes, same session token, same instant). Due to a testing-harness
timing artifact, this ended up producing 4 real concurrent/near-
concurrent submissions of the same topic in total (2 additional
detached requests completed later in the background from an earlier
malformed test attempt) — a stronger test than originally planned, not
a weaker one.

Result: 4 fully independent, valid meeting rows (ids 3–6), each with its
own correct 4-participant selection (`ceo, financial, marketing,
red-team`) and its own correctly-scoped 4 messages — zero cross-
contamination between the four meetings' `messages` rows, zero crashes,
zero orphaned `agent_runs` (all `ended` or accounted-for). Confirms Red
Team's condition 5: a duplicate/concurrent submission is handled
cleanly as independent, valid, non-corrupting meetings — the accepted v1
limitation (no dedup) behaves exactly as disclosed, not worse.

## 6. Concurrency bound held under real load

Across the whole session: 1 meeting with 6 participants + 1 select + 1
synthesis, 1 meeting with 1 participant (failed), 4 meetings with 4
participants each — 23 total real agent invocations attempted (22 ended,
1 failed, per direct query of `agent_runs`). Zero
`error_kind='capacity_exceeded'` results appeared anywhere in the server
log despite real concurrent load, and no request hung or deadlocked —
`wait_for_slot=True`'s bounded blocking-acquire against the shared
3-permit semaphore worked correctly under genuine concurrent multi-
meeting HTTP traffic, not just the single-meeting case Red Team
originally reasoned about.

## 7. Security-adjacent robustness (routine QA-level checks; full
adversarial pass is Security's own gate below)

- XSS payload (`<script>alert(1)</script>`) and a SQL-injection-shaped
  string in a real `decision` field: stored verbatim as inert data
  (parameterized query, not string-built SQL — table intact, row count
  unchanged), rendered back HTML-escaped (`&lt;script&gt;`), zero literal
  `<script>` tag in the served page.
- GET on `/api/meetings` (write-only route) — 404, not a silent 405 or a
  read-side leak.
- 70KB oversized POST body — 400 (rejected by `MAX_BODY_BYTES` before
  any parsing).
- Non-numeric id in `/api/meetings/abc/decide` — 404 (regex rejects
  before reaching `decide_meeting()`).
- Path-traversal-shaped GET (`/meetings/../../../etc/passwd.html`) — 404
  (`id_part.isdigit()` check rejects before any filesystem/DB access).

## Known limitations carried forward (not defects)

- Duplicate meeting submission has no dedup — disclosed, accepted v1
  scope per Red Team condition 5.
- The one real `runtime_error` in section 3 is disclosed as an observed
  live flake, not silently omitted from this report.
- Synthesis-failure-specific coverage relies on Development's
  monkeypatched test plus Code Review's control-flow verification, not
  a fresh live reproduction (see section 4).

No blocking findings. Proceeding to Security.
