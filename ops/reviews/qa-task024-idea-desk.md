# QA — TASK-024, the Idea Desk (slices 1 and 2)

**Tested by:** QA agent, 2026-09-02
**Commit under test:** `562e3c1` ("Fix pass 1 against the catch-up gate reviews (4 of 5 in, all REJECT)")
**Files:** `ops/idea-desk/{server,pages,evaluator,seed_founder_idea,doctor}.py`, TASK-024 sections of `ops/db/opsdb.py`
**Verified hashes at the time of testing:** `server.py a7bafec63e548fc886eed77e49d449da`, `opsdb.py 251367e050d5b0d432a1f0183979f75f`

> **Note on a moving target.** Testing began against `044a4ad`. Half way through, `562e3c1` landed
> and changed all five files. Every defect below was **re-run and re-confirmed against `562e3c1`**
> from a `git archive` snapshot of that commit; findings that `562e3c1` fixed have been moved out of
> the defect list and into "What already works". If the tree has moved again, re-check the hashes above.

## How this was tested

- Never against the live database. Every run used `OPSDB_PATH=<scratch>.sqlite3`.
- No credential file was read, created, moved or modified. The two auth functions were stubbed in
  memory in the launcher process (`founder_auth.credential_exists`, `founder_auth.verify_passphrase`);
  `verify_passphrase_guarded` was left real, so the lockout was exercised for real.
- The Idea Desk `server.py` was loaded by explicit path with `importlib.util`, never by `import server`.
- **One** real evaluation was run (real `claude`, real money). Everything else used a stub for
  `agent_runtime.invoke_agent` returning `RuntimeResult(ok=…, response_text=…)`.
- The server was driven over HTTP as a browser would (`http.client`): login, cookies, form posts,
  deep links, back-button re-submits, concurrent clicks, restarts.

---

## Verdict summary

Slices 1 and 2 do what they say for the normal path, and the parts that were built to hold a line —
the approve gate, the sanitiser, the failure handling, the "nothing was saved" honesty — hold. What
fails is the money and the record: a double click pays twice, a second desk pays twice and lies about
it, and a Founder decision to park an idea is silently reversed by a round arriving behind it.

---

## Defects

Severity: **A** = Founder loses money, data or a decision · **B** = Founder is blocked or misled ·
**C** = rough edge, real but survivable.

### 1. (A) A double-clicked "Yes, evaluate it" starts two evaluations and pays twice

`evaluator.start()`'s docstring claims "the marker is written BEFORE the thread starts, so a
double-clicked button is refused by the database rather than racing." It is not. `cmd_idea_evaluation_start`
reads `evaluating_since` and then writes it in a separate statement, with no `BEGIN IMMEDIATE` and no
`UPDATE … WHERE evaluating_since IS NULL`, so two concurrent processes both read NULL and both proceed.

**Repro (HTTP, the real button):** sign in; create an idea; fire two `POST /api/evaluate/<id>`
requests from two threads released off a `threading.Barrier`. Repeat 8 times.

**Expected:** exactly one 303 and one 409 "an evaluation of idea id=N is already running", every time.

**Actual:** on `562e3c1`, 1 of 8 trials returned `[303, 303]` — two evaluations, two sets of model
calls, and **two rounds written for one click**:

```
trial 6 idea 10: [303, 303] -> 2 evaluation(s) started
SELECT idea_id, COUNT(*) FROM idea_rounds …  ->  idea 10 | 2 rounds
```

On `044a4ad` the same test hit it 5 times out of 10 (3 concurrent clicks), and 45 stub agent calls were
made where 30 were asked for. **Repro at the database layer, which is where the bug is** — 8 processes
that pre-import `opsdb` and wait on a file gate, then each call `cmd_idea_evaluation_start` on the same
idea: two printed `STARTED` in 2 of 3 rounds.

### 2. (A) Starting a second Idea Desk clears markers for evaluations that are actually running, tells the Founder nothing was charged, and lets the same idea be evaluated twice

`_recover_stranded_evaluations()` clears **every** non-null `evaluating_since` at startup. It cannot
tell "left behind by a dead process" from "running right now in the other process". The program's own
port-in-use message and `doctor.py` both actively recommend the situation that triggers it:
`IDEA_DESK_PORT=8431 python3 ops/idea-desk/server.py` "to compare".

**Repro:** desk A on 8471; start an evaluation on an idea (a stub with a 25 s per-call delay makes the
window comfortable); while it is genuinely running, start desk B on 8472 against the same
`OPSDB_PATH`.

**Expected:** B leaves a live evaluation alone, or at minimum does not claim it was not charged.

**Actual:**

```
[idea-desk] idea 13 was left mid-evaluation by a previous run — clearing it so you can try again
```

Both desks then show the red banner *"The Idea Desk was stopped while the company was reading this.
Nothing was saved, and nothing was charged for a round that never finished."* Both statements are
false — it is still running and still being charged. Evaluating again from B is accepted (303), and
when both land the idea has two rounds:

```
id | idea_id | round_no | created_at
14 | 13      | 1        | 14:22:04.965Z
15 | 13      | 2        | 14:22:10.150Z
```

Related, same run: whichever evaluation finishes first calls `idea-evaluation-end`, which clears the
marker unconditionally, so the UI announces "done" while the second one is still spending.

### 3. (A) Parking or dropping an idea mid-evaluation is accepted, then silently reversed

`562e3c1` closed this in one direction (evaluating a parked idea is now refused, because it "silently
un-parked it and erased that record"). The other direction is open: `idea-close` has no
`evaluating_since` guard, and `idea-round-add` sets `status = 'evaluated'` unconditionally.

**Repro:** open `/close/<id>` in a tab (this is legal — nothing is running yet); start an evaluation
of that idea from another tab; submit the parked form from the first tab; wait for the round to land.

**Expected:** either the park is refused while a reading is in flight, or the park survives and the
arriving round does not overwrite it.

**Actual:** the park is accepted (303, `status=parked, close_reason='changed my mind, do not build this'`).
When the round arrives, `status` flips to `evaluated`, the page offers **Approve brief**, and the
"You parked it" entry disappears from *What is stored* (it only renders for `status in (parked,dropped)`).
`close_reason` and `closed_at` are left behind in the row as orphaned data:

```
after the evaluation finishes:  status=evaluated | close_reason='changed my mind, do not build this' | closed_at set
```

The Founder's explicit "not building this" is gone from the screen without anyone telling them.

### 4. (B) A marker stranded while the desk stays up locks the idea until a restart

Startup recovery fixed the killed-process case (good — see "What already works"). The case where the
worker's final `idea-evaluation-end` cannot be written (the database busy for longer than the 5 s
timeout — defect 11 — or any other failure of that one call) leaves the marker set with the server
still running, and there is no in-process recovery and no UI escape.

**Repro:** with the desk running, set the marker out of band the way a failed end-write leaves it:
`opsdb.py idea-evaluation-start --idea-id N`. Then use the UI.

**Expected:** some way back from the Founder's chair.

**Actual:** `/idea/N`, `/close/N`, `/correct/N`, `/evaluate/N` all show or redirect to the
self-refreshing "The company is considering your idea" screen with **no progress lines at all** (the
in-memory `PROGRESS` is empty), forever. `POST /api/close/N` succeeds (303) but the page still shows
the wait screen. The only exit is restarting the Idea Desk — which nothing on the page says.

### 5. (B) `/edit/` and `/close/` still offer forms for actions the database always refuses

`562e3c1` added `_why_not_evaluate` / `_why_not_approve` and wired them into `/evaluate/`, `/correct/`
and `/approve/`. `/edit/` and `/close/` were not given the same treatment.

**Repro:** approve an idea, then open `/edit/<id>` and `/close/<id>`.

**Expected:** the same "Not right now" refusal the other three doors now give.

**Actual:**

```
GET /edit/3   -> 200 'Edit your idea'   (full form, "Save the edit")
GET /close/3  -> 200 (Not building this panel, Park it / Drop it)
POST /api/edit/3  -> 409 "this idea's brief is approved — the approved brief is frozen"
POST /api/close/3 -> 409 "approved briefs are not parked or dropped"
```

The Founder types a whole re-write, submits, and gets an error page with one link back to the list.
What they typed is gone (see defect 6).

### 6. (B) Every refused POST throws away what the Founder typed, and the size limit is invisible and much smaller than it looks

`error_page()` is a dead end: heading, sentence, "Back to your ideas". No form is ever re-rendered
with the submitted content. The most costly instance is the body-size limit.

**Repro:** paste a 100,000-character idea into "In your own words" and save.

**Expected:** either it is saved, or the form comes back with the text still in it and a message
naming the limit.

**Actual:** `400 Bad request — "Missing or oversized form."` The text is gone. Nothing on the form
mentions a limit; the textarea has no `maxlength`; the message does not say which of "missing" or
"oversized" happened, nor what the limit is.

The limit is `MAX_BODY_BYTES = 64 KiB` measured on the **URL-encoded** body, so it depends on the
script the Founder writes in. Measured:

| what they write | characters accepted |
|---|---|
| plain ASCII prose | 65,482 |
| prose with newlines | 59,246 |
| Cyrillic | 12,387 |
| emoji | 5,456 |

A Founder writing in Russian is cut off at ~12k characters, and told only "Missing or oversized form."

### 7. (B) The correction stored "durably" is never shown back, and is destroyed by the next evaluate

`562e3c1` added `ideas.pending_note` so "a failed run cannot lose" a correction. Nothing reads it:
`grep -rn "pending_note" ops --include=*.py` matches only `opsdb.py` and one test. `pages.py` and
`server.py` never mention it.

**Repro:** evaluate an idea; click **Correct us** and send a real note; make the round fail (stub a
`runtime_error`); look at the page.

**Expected:** the note comes back — in the failure banner, or pre-filled in the correction box.

**Actual:** the red banner says only *"The last evaluation did not finish. Chief of Staff could not
answer — the model fell over."* The note is nowhere on the page, and `/correct/<id>` re-opens an empty
textarea. The text is in `ideas.pending_note`, reachable only by SQL. Worse, it is then **erased**:
clicking plain "Ask the company to evaluate it" calls `idea-evaluation-start` with no `--note`, which
writes `pending_note = NULL`.

```
before: "You completely missed that this is only for my own team of three…"
plain evaluate → 303
after:  None
```

### 8. (C) An out-of-range idea id gives "Something broke" on GET and a raw Python traceback on POST

`562e3c1` fixed unicode digits (`/idea/²` → 404, confirmed). Large ASCII digit strings still pass
`isascii() and isdigit()`, and SQLite refuses them.

**Repro:** `GET /idea/99999999999999999999999999` and `POST /api/close/999999999999999999999999999999`.

**Expected:** 404 "No such idea", the same as `/idea/abc`.

**Actual:** GET → `500 "Something broke — That is a bug in the Idea Desk, not something you did."`
(server stderr: `OverflowError: Python int too large to convert to SQLite INTEGER`). POST → `409 "That
was refused"` whose body is a Python traceback, complete with absolute paths, rendered on the page:

```
Traceback (most recent call last):
  File "…/ops/db/opsdb.py", line 2258, in <module>
    main()
  …
  File "…/ops/db/opsdb.py", line 1731, in _idea_row
    row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
OverflowError: Python int too large to convert to SQLite INTEGER
```

### 9. (C) A NUL byte in the idea text is a 500

**Repro:** `POST /api/create` with body `token=<t>&raw=hello%00world` (a paste from some editors and
PDF viewers carries one).

**Expected:** saved, or refused with a sentence.

**Actual:** `500 "Something broke"`; server stderr `ValueError: embedded null byte` from
`subprocess.run`. Nothing is saved and the text is gone.

### 10. (C) A one-word idea starting with `--` shows the Founder an argparse usage dump

Every write shells out with the Founder's text as an argv value. A value containing a space is safe;
a bare `--word` is taken as an option.

**Repro:** save an idea whose entire text is `--dark-mode`.

**Expected:** it saves. It is a legitimate thing to type.

**Actual:**

```
409 That was refused
usage: opsdb.py idea-create [-h] --raw RAW [--audience AUDIENCE] [--trigger TRIGGER]
opsdb.py idea-create: error: argument --raw: expected one argument
```

Same for a one-word `--…` in "Who is it for?", "What made you think of it?" and the park/drop reason.
(`-- the UI is verbose`, `-1 star`, `--- rethink this` all save correctly — only a single token.)

### 11. (C) When the database is held by another writer, reads are "a bug in the Idea Desk" and writes print a traceback

The Idea Desk shares `operations.sqlite3` with the Control Center on 8420, and journal mode is
`delete`, so a writer excludes readers. 12 parallel ordinary writes were all absorbed by the 5 s busy
timeout, so this needs a lock held longer than that (a long transaction, a backup, a slow disk).

**Repro:** hold `BEGIN EXCLUSIVE` on the database from another process for 25 s; browse the desk.

**Expected:** "the database is busy for a moment, try again".

**Actual:** `GET /` and `GET /idea/N` hang 5 s then `500 "Something broke — That is a bug in the Idea
Desk, not something you did."` `POST /api/create` returns `409` whose visible body is
`Traceback (most recent call last): … sqlite3.OperationalError: database is locked`. `opsdb.py main()`
catches `IntegrityError` only, and `server.opsdb()` passes stderr through verbatim.

### 12. (C) The list never shows that an evaluation is running

**Repro:** start an evaluation, go to `/`.

**Expected:** the one screen that shows every idea says which one is currently costing money.

**Actual:** the row reads `draft · just now · Saved. Not evaluated yet.` — the same as an idea nobody
has ever touched. `list_page()` reads `status` and the last recommendation and never looks at
`evaluating_since`.

### 13. (C) Unusual model output reaches the ten-question page as "None", as blank, or as a Python dict

`_validate()` checks that all ten keys are present, never that they say anything.

**Repro:** stub a synthesis whose `answers` contain `"1": [null, null]`, `"2": ["", ""]`,
`"3": [{"nested":"obj"}, ["x","y"]]`, `"4": ["   ", ""]`.

**Expected:** rejected the way a missing question is ("nothing was saved"), or shown as the existing
"Not answered in this round." fallback — which is unreachable today, because it only fires on a
missing key.

**Actual, rendered as the company's answer:**

```
Q1: None
Q2: (empty card)
Q3: {&#x27;nested&#x27;: &#x27;obj&#x27;}
Q4: (three spaces)
```

### 14. (C) "already approved (round 3)" names the round id, not the round the page shows

**Repro:** approve an idea's only round, then re-submit the approve form (back button).

**Expected:** "already approved (round 1)", matching the page's own "Idea · round 1 of 1".

**Actual:** `error: idea id=3 is already approved (round 3); an approved brief is frozen` — `3` is
`idea_rounds.id`. (`cmd_idea_approve` prints `row['approved_round_id']` where every other message in
the same function uses `round_no`.)

### 15. (C) `seed_founder_idea.py` checks one database and writes to another; on a fresh clone it dies with a traceback

`DB = REPO/"ops"/"db"/"operations.sqlite3"` is hardcoded for the "already seeded?" read, while every
write goes through `opsdb.py`, which honours `OPSDB_PATH`.

**Repro A:** `OPSDB_PATH=/tmp/fresh.sqlite3 python3 ops/db/opsdb.py init` then
`OPSDB_PATH=/tmp/fresh.sqlite3 python3 ops/idea-desk/seed_founder_idea.py`.
**Expected:** seeds `/tmp/fresh.sqlite3`. **Actual:** `Already seeded as idea id=1 — nothing to do.`
— read from the live database. `/tmp/fresh.sqlite3` still has 0 ideas. (Symmetrically, if the live
database lacks the idea and the target has it, it seeds a duplicate; the file's own docstring promises
"Safe to run more than once: it refuses if the idea is already there.")

**Repro B:** run it in a clone that has never started the desk (`operations.sqlite3` stopped being
tracked in `a2ed57d`, so this is every fresh clone).
**Expected:** a sentence telling them to run `opsdb.py init`, the way the server does.
**Actual:** `sqlite3.OperationalError: unable to open database file`, as a raw traceback.

### 16. (C) The build stamp was not bumped by a fix pass that changed everything

`BUILD = "slice 2 — evaluation is live"` is unchanged across `044a4ad → 562e3c1`, a commit that
rewrote the approve gate, the login lock, the sanitiser, startup recovery and correction storage. The
stamp's own comment says "Bumped whenever what works changes", the footer prints it, and `doctor.py`
reports it as the answer to "did my pull take effect". Today it answers wrongly.

---

## What already works (tested, not assumed)

- **Normal journey.** New idea → evaluate → ten answers + Company View → Correct us → round 2 with a
  "What changed since round 1" banner → Approve → the approved-brief banner and a frozen brief.
  Park / drop / reopen all behave, including from a draft and from an evaluated idea.
- **One real evaluation** (real `claude`, ~2 minutes): Chief of Staff chose Product + CTO at **Light**
  depth, all ten answers arrived with expansions, the Company View said **Opportunity: Low** and
  **Investigate first**, and the action bar correctly offered no Approve — "No Approve on this round…"
  The gate did the job it exists for on a real, unscripted answer, and the answer did not flatter the
  idea. `agent_run_id` on the round is NULL and no cost is shown anywhere (see observations).
- **Sign-in, session, CSRF.** No-session GET redirects to `/login`; no-session POST is 401; forged,
  empty and missing tokens are 403; a token minted by a previous process is refused after a restart;
  a garbage cookie is treated as no session; a lying `Content-Length` is refused; chunked bodies are
  refused. Five wrong passphrases produce a 429 lockout, and the *correct* passphrase is refused
  during it. Cookie is `HttpOnly; SameSite=Strict`.
- **Escaping and sanitising.** `<script>`, `<img onerror>`, `<style>`, `<a href>`, `onclick=` and
  `onmouseover=` are all inert both in the Founder's own text and in agent-authored answers. Emoji,
  CJK, Cyrillic, RTL overrides, quotes, ampersands and newlines round-trip and display correctly.
  The new `safe_html` balancing closes an unclosed `<b>` and drops a stray `</div>`; page div balance
  stayed 0 under deliberate tag soup.
- **Evaluation failure handling is genuinely good.** Non-JSON prose, JSON in fences and prose, a
  missing question, an invented recommendation, an invalid opportunity value, an agent timeout and
  `runtime_unavailable` were each handled: red banner in the Founder's words, nothing written, marker
  cleared. Fenced JSON is parsed; a bad `opp` degrades to "Unclear" rather than failing.
- **Approve gate.** No Approve button when the recommendation is `Reconsider` / `Investigate first`;
  `/approve/<id>` now refuses with "Nothing to approve" instead of rendering a doomed green button
  (fixed in `562e3c1`); approving a superseded round 1 after a worse round 2 is refused; approving
  twice is refused; approving mid-evaluation is refused.
- **Missing note on Correct us**: empty and whitespace-only are both refused with "Say what the
  company got wrong first", nothing is started and nothing is spent.
- **Ids**: `abc`, `-5`, `0`, `1.5`, `²`, `١٢٣`, `1%20` and a non-existent id all give 404 "No such idea".
- **Old database.** A database missing `evaluating_since` / `last_error` is migrated on every start
  (`044a4ad`), verified by `PRAGMA table_info` before and after. If one is restored *under* a running
  desk, reads still work and every write says: *"this database is older than the code — the ideas
  table is missing evaluating_since, last_error, pending_note. Bring it up to date with: python3
  ops/db/opsdb.py init"*. A deleted database gives "No database yet — run opsdb.py init first".
- **Killed process.** After `kill -9` mid-evaluation, the next start clears the marker and the idea
  is usable again, with an honest banner. (This was a hard failure before `562e3c1`: on `044a4ad` the
  idea was stuck on the wait screen forever, and even a successful park POST could not change the page.)
- **Port already in use** prints the long, correct explanation instead of a traceback, and `doctor.py`
  reports branch, commit, files, port, `claude`, credential and database accurately.
- **Rapid repeated actions**: ten interleaved park/reopen posts ended in a consistent state with
  graceful 409s. `HEAD/PUT/DELETE/OPTIONS/TRACE` → 501. `/../etc/passwd` → 404.
- The developer's own `ops/idea-desk/test_idea_desk.py` — 23 tests — passes.

## Observations (not defects; judgement calls, not breakage)

- **Cost is still invisible to the Founder.** `562e3c1`'s message says "evaluations now record what
  each call cost". `_SPEND` is a per-process in-memory dict, `spend_for()` has no caller anywhere,
  and `idea_rounds.agent_run_id` was NULL after the real run. The one action the UI headlines as
  spending money still shows no amount anywhere, before or after.
- **Q9 asks the Founder for decisions and there is nowhere to answer them.** The real evaluation ended
  with two questions and "Investigate first". The only reply channel is a box headed *"Correct us:
  what did the company get wrong?"* with the placeholder *"almost there, but…"*. Answering a question
  is not correcting a mistake, and it costs a full round either way.
- `pages.correct_panel()` is dead code — `/correct/` renders `evaluate_panel(correcting=True)`.
- No `Content-Security-Policy` header. The sanitiser is the real defence and it held under everything
  thrown at it; a CSP would be cheap depth on a page that renders agent-authored HTML.
- Evaluating a **parked** idea is now refused (good), but the refusal arrives only at `/evaluate/`;
  the idea page for a parked idea with rounds still shows the full round, which is right.

---

## Result

**FAIL** — returned to Development. Defects 1, 2 and 3 each cost the Founder real money or silently
reverse a decision they made, and 4, 5, 6 and 7 lose work they typed. Everything in "What already
works" should survive the fix.
