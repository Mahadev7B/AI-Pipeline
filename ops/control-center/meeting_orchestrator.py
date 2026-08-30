"""ops/control-center/meeting_orchestrator.py — Phase 2, Milestone 2B3B.

Real Executive Meetings — the multi-agent orchestration layer built on
top of 2B3A's bounded concurrent Agent Runtime foundation, per
ops/EXECUTIVE_MEETINGS.md's five steps and
ops/reviews/cto-milestone2b3b-architecture.md's design. server.py's
POST /api/meetings route calls only run_meeting() — this module owns
every step (participant selection, concurrent position-gathering,
synthesis) so that logic doesn't leak into the HTTP layer, the same
separation agent_runtime.py already keeps from server.py.

This module does NOT talk to sqlite3 directly except through opsdb.py
functions (create_meeting, start_run, send_message, end_run,
finalize_meeting_synthesis) — opsdb.py remains the only writer. It does
NOT invoke the runtime except through agent_runtime.invoke_agent() —
that remains the only Agent Runtime boundary. This module is pure
orchestration glue between the two, plus the CEO-facing prompts that
drive selection and synthesis.

Concurrency: participant positions are gathered via a
concurrent.futures.ThreadPoolExecutor sized to
agent_runtime.MAX_CONCURRENT_INVOCATIONS (stdlib only, no new
dependency) — NOT a separate, larger pool. Meetings compete for the same
global 3-permit semaphore as any concurrent Ask-Agent traffic;
"concurrency is deliberately bounded" holds system-wide, not per-
feature. Every worker thread opens and closes its own opsdb.connect() —
a Python sqlite3.Connection is never shared across threads (2B3A's
established, verified rule).
"""
from __future__ import annotations

import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402
import agent_runtime  # noqa: E402

MAX_TOPIC_CHARS = 2_000  # generous for a real cross-cutting question; matches the
                          # discipline of MAX_ASK_MESSAGE_CHARS in server.py

_CANDIDATE_ROLES = tuple(r for r in agent_runtime.MEETING_PARTICIPANT_ALLOWLIST if r != "ceo")


def _parse_selection(response_text: str) -> list[str]:
    """Lenient parsing (Red Team's Milestone 2B3B condition 1): never
    require CEO's selection response to be in an exact format. Matches
    each candidate role name case-insensitively, tolerant of
    surrounding whitespace/punctuation, anywhere in the response — never
    trusts the response as literal instructions, only as a signal for
    which of the fixed, pre-approved candidate names were mentioned."""
    if not response_text:
        return []
    text = response_text.lower()
    selected = []
    for role in _CANDIDATE_ROLES:
        # word-boundary match so e.g. "ceo" doesn't accidentally match inside another word
        if re.search(rf"(?<![a-z0-9-]){re.escape(role)}(?![a-z0-9-])", text):
            selected.append(role)
    return selected


def _select_participants(topic: str) -> list[str]:
    """Step 2, CEO's half: CEO Agent's real judgment call about who has
    relevant expertise. Milestone 2B3B round 2 (TASK-011, item 1) split
    this function from Orchestrator's half — _validate_selection() below
    — per cto-milestone2b3b-round2-architecture.md: this now returns the
    RAW parsed candidate names (allowlist-filtered by _parse_selection()'s
    regex, so it can only ever match a real candidate role, but NOT
    truncated to the cap — that's Orchestrator's job, not CEO's). CEO is
    always included by the caller (run_meeting), never decided here. On
    any invocation failure, returns an empty list (a meeting with just
    CEO is still a valid, honest meeting — never fabricate a selection
    when the real call failed)."""
    prompt = (
        f"Founder: A cross-cutting question has been raised for an Executive Meeting: "
        f"\"{topic}\" From this list of candidate roles, which should participate because "
        f"they have real, relevant expertise for this specific question (do not include a "
        f"role just because it exists): {', '.join(_CANDIDATE_ROLES)}. Respond with ONLY a "
        f"comma-separated list of the role names you select from that exact list, nothing "
        f"else — no explanation, no punctuation besides commas."
    )
    result = agent_runtime.invoke_agent("ceo", prompt, wait_for_slot=True)
    if not result.ok:
        return []
    return _parse_selection(result.response_text)


def _validate_selection(candidates: list[str]) -> tuple[list[str], str]:
    """Step 2, Orchestrator's half (Milestone 2B3B round 2, item 1). Pure
    Python — no invoke_agent() call, never touches ASK_AGENT_ALLOWLIST or
    MEETING_PARTICIPANT_ALLOWLIST, because it never becomes a `claude
    --agent` subprocess. Per cto-milestone2b3b-round2-architecture.md:
    Orchestrator's real, distinct contribution is enforcement — deduping
    CEO's raw nomination, dropping a redundant self-nomination of "ceo"
    (CEO is always added separately by the caller, never counted here),
    and deterministically truncating to the cap — not a second creative
    judgment about which roles are relevant, which stays CEO's call.
    Returns (validated_names, a short human-readable explanation of what
    was admitted/dropped and why) — the explanation is what a meeting's
    detail page actually shows (see run_meeting() below), the real,
    attributed record Design Conformance round 2 asked for."""
    deduped: list[str] = []
    seen: set[str] = set()
    for name in candidates:
        if name == "ceo" or name in seen:
            continue
        seen.add(name)
        deduped.append(name)

    cap = agent_runtime.MAX_MEETING_PARTICIPANTS - 1  # CEO takes the +1 slot, added by the caller
    validated = deduped[:cap]

    if not deduped:
        explanation = "Validated CEO's nomination: none. CEO is the meeting's only participant."
    elif len(validated) == len(deduped):
        explanation = (
            f"Validated CEO's nomination: {', '.join(deduped)}. "
            f"Admitted {len(validated)} of {len(deduped)} — within the {cap}-other cap."
        )
    else:
        dropped = deduped[cap:]
        explanation = (
            f"Validated CEO's nomination: {', '.join(deduped)}. "
            f"Admitted {len(validated)} of {len(deduped)} — capped at {cap} others; "
            f"dropped: {', '.join(dropped)}."
        )
    return validated, explanation


def _position_prompt(topic: str) -> str:
    """The one prompt template for "state your position on this meeting's
    topic" — shared by _gather_position() (the original gather) and
    retry_position() (item 5) below, since a retry is explicitly the same
    ask made again, not a different one. Milestone 2B3B round 2's own
    architecture document is explicit that retry reuses "_gather_position()'s
    existing prompt template unchanged" — factored out here so that's
    true by construction, not by two copies staying in sync by hand.
    gather_requested_position() (item 2) intentionally does NOT use this —
    its prompt is worded differently on purpose (the meeting is already
    under way and the Founder specifically asked for this participant)."""
    return (
        f"Founder: An Executive Meeting has been raised on this topic: \"{topic}\" "
        f"State your position from your own role and responsibilities — your real "
        f"assessment, not a generic opinion. Be concise (2-4 sentences)."
    )


def _gather_position(meeting_id: int, agent_name: str, topic: str) -> tuple[str, bool, str | None]:
    """Runs in its own worker thread — opens and closes its own
    connection, never shares one across threads. Returns
    (agent_name, ok, position_text_or_None). Never fabricates a position
    on failure — persists the real agent_runs outcome either way."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_run(conn, agent_name, "meeting", agent_runtime.MEETING_ACTIVITY_LABEL, scope_id=meeting_id)
        result = agent_runtime.invoke_agent(agent_name, _position_prompt(topic), wait_for_slot=True)
        if result.ok:
            opsdb.send_message(conn, f"meeting-{meeting_id}", "meeting", agent_name, result.response_text,
                                to_agent=None, meeting_id=meeting_id)
            opsdb.end_run(conn, run_id, "ended")
            return (agent_name, True, result.response_text)
        else:
            sys.stderr.write(f"[control-center] meeting {meeting_id}: {agent_name} failed to provide a position "
                              f"({result.error_kind}): {result.error}\n")
            opsdb.end_run(conn, run_id, "failed")
            return (agent_name, False, None)
    except Exception as exc:  # noqa: BLE001 — one participant's bug must not abort the whole meeting
        sys.stderr.write(f"[control-center] meeting {meeting_id}: unhandled error gathering {agent_name}'s position: "
                          f"{type(exc).__name__}: {exc}\n")
        try:
            opsdb.end_run(conn, run_id, "failed")
        except (LookupError, ValueError, NameError):
            pass  # run_id may not exist yet if start_run itself raised
        return (agent_name, False, None)
    finally:
        conn.close()


def _synthesize(topic: str, positions: dict[str, str]) -> tuple[str | None, str | None, str | None, str | None]:
    """Step 4: a real, separate CEO call — cannot happen concurrently
    with step 3, since it needs every position that succeeded. Returns
    (agreements, disagreements, unresolved_questions, recommendation),
    each None if the call fails or a field wasn't present in the
    response — never fabricated."""
    if not positions:
        return (None, None, None, None)
    positions_text = "\n".join(f"{name}: {text}" for name, text in positions.items())
    prompt = (
        f"Founder: Here are the real positions gathered for an Executive Meeting on: "
        f"\"{topic}\"\n\n{positions_text}\n\n"
        f"Synthesize this into exactly four labeled sections, in this order, each on its own "
        f"line starting with the exact label shown:\n"
        f"AGREEMENTS: <where the real positions above agree>\n"
        f"DISAGREEMENTS: <where they genuinely disagree>\n"
        f"UNRESOLVED: <real open questions this discussion didn't settle>\n"
        f"RECOMMENDATION: <your own synthesized recommendation as CEO — not an average of "
        f"votes, your actual judgment>\n"
        f"If a section has nothing real to report, write 'None.' for that section rather than "
        f"inventing content."
    )
    result = agent_runtime.invoke_agent("ceo", prompt, wait_for_slot=True)
    if not result.ok:
        return (None, None, None, None)
    return _parse_synthesis(result.response_text)


def _parse_synthesis(text: str) -> tuple[str | None, str | None, str | None, str | None]:
    fields = {"AGREEMENTS": None, "DISAGREEMENTS": None, "UNRESOLVED": None, "RECOMMENDATION": None}
    pattern = re.compile(r"^(AGREEMENTS|DISAGREEMENTS|UNRESOLVED|RECOMMENDATION):\s*(.*)$", re.IGNORECASE)
    current = None
    for line in (text or "").splitlines():
        m = pattern.match(line.strip())
        if m:
            current = m.group(1).upper()
            fields[current] = m.group(2).strip()
        elif current and line.strip():
            fields[current] = (fields[current] + " " + line.strip()).strip()
    # "None."-style non-answers are a real, honest response, not missing data — keep them as-is
    # rather than converting to None, so the Founder sees CEO explicitly said there was nothing.
    return (fields["AGREEMENTS"], fields["DISAGREEMENTS"], fields["UNRESOLVED"], fields["RECOMMENDATION"])


def run_meeting(topic: str) -> int:
    """The whole synchronous flow (Founder raises → CEO selects →
    Orchestrator validates → positions gathered concurrently, bounded →
    CEO synthesizes). Returns the new meeting's id. Raises ValueError for
    a bad topic. Never raises for a participant/synthesis failure — those
    are recorded honestly and the meeting still completes with whatever
    real work succeeded.

    Milestone 2B3B round 2 (item 1): Orchestrator's validation step now
    runs between CEO's raw nomination and meeting creation. Its
    `agent_runs` row is honestly `scope_type="company"` — the meeting
    doesn't exist yet at that point, so there is no `scope_id` to give a
    meeting-scoped run (opsdb.start_run() would reject one) — per
    cto-milestone2b3b-round2-architecture.md and Red Team's Milestone
    2B3B round 2 review (affirmed without reservation, open question 4).
    The actual visible content — what a meeting's detail page shows —
    lands in a real meeting-scoped message the moment `meeting_id`
    exists, on its own thread (`meeting-{id}-orchestrator`), never mixed
    into the shared positions thread every participant's own position
    uses."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ValueError(f"topic exceeds the {MAX_TOPIC_CHARS:,}-character limit")

    raw = _select_participants(topic)  # CEO's call, unchanged

    conn = opsdb.connect()
    try:
        run_id = opsdb.start_run(conn, "orchestrator", "company", agent_runtime.ORCHESTRATOR_VALIDATION_ACTIVITY_LABEL)
        # TASK-011 QA round 2, defect 1: unlike every other run-creating
        # call site this round added (gather_requested_position(),
        # retry_position()), this one had no try/except — a mid-step
        # exception (e.g. _validate_selection() raising, however
        # unlikely, or an sqlite3.OperationalError from end_run() itself)
        # left this row open (ended_at IS NULL) forever, with no
        # reconciliation pass covering it either (see agent_runtime.py's
        # ORCHESTRATOR_VALIDATION_ACTIVITY_LIKE / server.py's
        # _reconcile_orphaned_runs(), fixed alongside this). Same
        # end-as-failed-then-reraise discipline as _gather_position(),
        # gather_requested_position(), and retry_position() already use.
        try:
            validated, explanation = _validate_selection(raw)  # deterministic, no invocation
            opsdb.end_run(conn, run_id, "ended")
        except Exception:
            try:
                opsdb.end_run(conn, run_id, "failed")
            except (LookupError, ValueError):
                pass  # already ended somehow — nothing more to reconcile
            raise

        participants = ["ceo"] + validated  # CEO is always a participant — never optional
        meeting_id = opsdb.create_meeting(conn, topic, "founder", participants)
        opsdb.send_message(conn, f"meeting-{meeting_id}-orchestrator", "meeting", "orchestrator", explanation,
                            to_agent=None, meeting_id=meeting_id)
    finally:
        conn.close()

    positions: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=agent_runtime.MAX_CONCURRENT_INVOCATIONS) as pool:
        futures = [pool.submit(_gather_position, meeting_id, name, topic) for name in participants]
        for future in as_completed(futures):
            name, ok, text = future.result()
            if ok:
                positions[name] = text

    agreements, disagreements, unresolved, recommendation = _synthesize(topic, positions)
    conn = opsdb.connect()
    try:
        opsdb.finalize_meeting_synthesis(conn, meeting_id, agreements, disagreements, unresolved, recommendation)
    finally:
        conn.close()

    return meeting_id


# ------------------------------------------- items 2, 3, 5 (Milestone 2B3B round 2) --

def gather_requested_position(meeting_id: int, agent_name: str, topic: str,
                               requested_by: str = "founder") -> tuple[bool, str | None]:
    """Item 2 (POST /api/meetings/<id>/request-perspective): a manually-
    requested participant's position, gathered synchronously against an
    already-created meeting. Mirrors _gather_position()'s discipline
    (never fabricate a position on failure, always persist the real
    agent_runs outcome).

    TASK-011 QA round 2, defect 2 (fixed here): opsdb.add_meeting_participant()
    now runs BEFORE the real invocation, not after — the same "claim
    exclusivity first" discipline retry_position() below already uses via
    opsdb.start_meeting_retry_run(). Previously this atomic append
    happened only on a successful invocation, at the very end; that meant
    N truly concurrent requests for the same not-yet-participant agent
    could all pass the caller's (server.py) read-only pre-check and all
    make a REAL, costed invocation before only one of them won the
    append — QA reproduced exactly this (3 concurrent calls, 3 real
    invocations, 3 messages persisted in the shared thread, only 1
    credited). Reserving the slot first means a second concurrent caller
    now fails opsdb.add_meeting_participant()'s own atomic dup check
    immediately (ValueError, "already a participant") and never reaches
    invoke_agent() at all — no wasted invocation, not just tidier
    bookkeeping after the fact.

    A reservation that isn't backed by a real, successful position must
    not linger as a fabricated participant (opsdb.add_meeting_participant()'s
    own contract, unchanged) — so on invocation failure, or any unhandled
    exception after reserving, opsdb.remove_meeting_participant() rolls
    the reservation back before returning/re-raising. Writes into the
    SAME shared `meeting-{id}` thread every other participant's position
    uses (this is a real position on the topic, just gathered later — not
    a new kind of record, and not item 1's Orchestrator note or item 3's
    follow-up thread).

    Returns (ok, error_message_or_None). Callers must not treat a
    returned `ok=False` as an HTTP error on its own — see server.py: the
    caller has already separately validated eligibility (allowlist,
    not-already-a-participant, cap) before calling this; this function's
    own opsdb.add_meeting_participant() call is the atomic, authoritative
    re-check of exactly that same eligibility, and can still raise
    LookupError/ValueError/sqlite3.OperationalError if the state changed
    between the caller's check and now (a real, if rare, race) —
    propagated uncaught, same as retry_position() below."""
    conn = opsdb.connect()
    try:
        # Reserve the slot BEFORE any real invocation — see docstring
        # above. Raises LookupError (meeting missing) / ValueError
        # (already a participant, or cap reached) / sqlite3.OperationalError
        # (lock contention) — propagated uncaught to server.py, same
        # convention every other write route in this codebase uses.
        opsdb.add_meeting_participant(conn, meeting_id, agent_name, agent_runtime.MAX_MEETING_PARTICIPANTS,
                                       requested_by=requested_by)

        run_id = opsdb.start_run(conn, agent_name, "meeting", agent_runtime.MEETING_ACTIVITY_LABEL, scope_id=meeting_id)
        prompt = (
            f"Founder: An Executive Meeting is already under way on this topic: \"{topic}\" "
            f"The Founder has specifically asked for your perspective. State your position from "
            f"your own role and responsibilities — your real assessment, not a generic opinion. "
            f"Be concise (2-4 sentences)."
        )
        # Everything from here on operates on an ALREADY-CREATED run row
        # (run_id) AND an already-reserved participant slot — same
        # discipline as _handle_ask() in server.py (Code Review,
        # TASK-009) and _gather_position() above: an unhandled exception
        # anywhere in this block (a send_message() failure, lock
        # contention, anything unexpected) must still end the run as
        # 'failed' AND release the reservation before propagating, or the
        # run stays open (ended_at IS NULL) until the next server
        # restart's reconciliation pass, and/or the reservation lingers
        # as a fabricated participant with no real position.
        try:
            result = agent_runtime.invoke_agent(agent_name, prompt, wait_for_slot=True)
            if not result.ok:
                sys.stderr.write(f"[control-center] meeting {meeting_id}: requested participant {agent_name} failed to "
                                  f"provide a position ({result.error_kind}): {result.error}\n")
                opsdb.end_run(conn, run_id, "failed")
                _release_reservation(conn, meeting_id, agent_name)
                return (False, result.error)

            opsdb.send_message(conn, f"meeting-{meeting_id}", "meeting", agent_name, result.response_text,
                                to_agent=None, meeting_id=meeting_id)
            opsdb.end_run(conn, run_id, "ended")
            return (True, None)
        except Exception:
            try:
                opsdb.end_run(conn, run_id, "failed")
            except (LookupError, ValueError):
                pass  # already ended somehow (e.g. by the branch that raised) — nothing more to reconcile
            _release_reservation(conn, meeting_id, agent_name)
            raise
    finally:
        conn.close()


def _release_reservation(conn, meeting_id: int, agent_name: str) -> None:
    """Best-effort rollback of the reservation gather_requested_position()
    made via opsdb.add_meeting_participant() before invoking, for the
    case where the invocation did not, in fact, succeed. Never lets a
    cleanup-time error mask the real one already being handled/returned —
    same pragmatic "swallow cleanup failures" discipline the surrounding
    except blocks already use for opsdb.end_run()."""
    try:
        opsdb.remove_meeting_participant(conn, meeting_id, agent_name)
    except Exception as exc:  # noqa: BLE001 — cleanup-only, must never mask the real error
        sys.stderr.write(f"[control-center] meeting {meeting_id}: could not release reservation for "
                          f"{agent_name} after a failed request-perspective invocation: "
                          f"{type(exc).__name__}: {exc}\n")


def _build_followup_transcript(conn, meeting_id: int, agent_name: str, topic: str, thread_id: str) -> str:
    """Item 3's full-context reconstruction, built fresh from `messages`
    on every call — the same rebuild-from-scratch discipline server.py's
    own _build_transcript() already uses for Ask-Agent, not a new caching
    mechanism. Per cto-milestone2b3b-round2-architecture.md and Red
    Team's independent verification (Milestone 2B3B round 2 review,
    finding 6): a follow-up reply can honestly need to reference another
    participant's original position, not just the addressee's own — so
    this includes every `from_agent` row from the shared `meeting-{id}`
    positions thread (all participants, not filtered to just
    `agent_name`), plus this specific follow-up thread's own prior
    turns."""
    positions = conn.execute(
        "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
        (f"meeting-{meeting_id}",),
    ).fetchall()
    followup_rows = conn.execute(
        "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
        (thread_id,),
    ).fetchall()

    lines = [f'Founder: An Executive Meeting was held on this topic: "{topic}"', "", "Original positions from that meeting:"]
    for r in positions:
        lines.append(f"{r['from_agent']}: {r['body']}")
    lines.append("")
    lines.append(f"The Founder now has a follow-up question for you ({agent_name}) specifically. "
                  f"Answer as yourself, drawing on the full discussion above where relevant.")
    for r in followup_rows:
        speaker = "Founder" if r["from_agent"] == "founder" else agent_name
        lines.append(f"{speaker}: {r['body']}")
    return "\n".join(lines)


def gather_followup_reply(meeting_id: int, agent_name: str, topic: str, founder_message: str) -> tuple[bool, str | None]:
    """Item 3 (POST /api/meetings/<id>/followup). One Founder-initiated
    exchange in a thread separate from the shared positions thread — see
    _build_followup_transcript() above. Eligibility (agent_name is a
    current participant AND has a real recorded position — Red Team's
    Milestone 2B3B round 2 review, finding 7 / condition 6) is checked by
    the caller (server.py) before this is invoked, not here — this
    function's own job is only the write + the invocation.

    Returns (ok, error_message_or_None). No agent_runs row is created for
    this call — matching _select_participants()'s and _synthesize()'s own
    existing precedent (neither of those creates one either); CTO's
    Milestone 2B3B round 2 architecture document does not call for one
    here, unlike items 2 and 5 which explicitly do."""
    conn = opsdb.connect()
    try:
        thread_id = f"meeting-{meeting_id}-{agent_name}"
        opsdb.send_message(conn, thread_id, "meeting", "founder", founder_message,
                            to_agent=agent_name, meeting_id=meeting_id)
        transcript = _build_followup_transcript(conn, meeting_id, agent_name, topic, thread_id)
        result = agent_runtime.invoke_agent(agent_name, transcript, wait_for_slot=True)
        if not result.ok:
            sys.stderr.write(f"[control-center] meeting {meeting_id}: follow-up with {agent_name} failed "
                              f"({result.error_kind}): {result.error}\n")
            return (False, result.error)
        opsdb.send_message(conn, thread_id, "meeting", agent_name, result.response_text,
                            to_agent="founder", meeting_id=meeting_id)
        return (True, None)
    finally:
        conn.close()


def retry_position(meeting_id: int, agent_name: str, topic: str) -> tuple[bool, str | None]:
    """Item 5 (POST /api/meetings/<id>/retry). Uses
    opsdb.start_meeting_retry_run() for the atomic eligibility +
    exclusivity check — see that function's docstring for exactly what it
    guards against (a double-clicked Retry button racing itself, or
    racing the original still-in-flight _gather_position() call). Unlike
    gather_requested_position() above, the run is started FIRST and the
    invocation happens only after that succeeds — retry's whole purpose
    is closing a race that starting the run first is what closes it.

    Raises whatever start_meeting_retry_run() raises
    (LookupError/ValueError/sqlite3.OperationalError) — propagated
    uncaught; server.py maps those to 404/409/503, the same convention
    every other write route in this codebase uses. Returns
    (ok, error_message_or_None) only for the invocation's own
    success/failure, once the run has already started."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_meeting_retry_run(conn, meeting_id, agent_name,
                                                agent_runtime.MEETING_ACTIVITY_LABEL,
                                                agent_runtime.MAX_RETRIES_PER_PARTICIPANT)
        # Everything from here on operates on an ALREADY-CREATED run row
        # (run_id) — same discipline as _handle_ask() in server.py
        # (Code Review, TASK-009) and _gather_position() above: an
        # unhandled exception anywhere in this block (e.g. send_message()
        # raising sqlite3.OperationalError from lock contention — a real
        # possibility now that server.py is multi-threaded) must still
        # end the run as 'failed' before propagating, or it stays open
        # (ended_at IS NULL) and start_meeting_retry_run()'s own open-run
        # exclusivity check then falsely, permanently rejects every
        # future retry for this exact agent+meeting with a 409 (Code
        # Review, Milestone 2B3B round 2 finding).
        try:
            result = agent_runtime.invoke_agent(agent_name, _position_prompt(topic), wait_for_slot=True)
            if result.ok:
                opsdb.send_message(conn, f"meeting-{meeting_id}", "meeting", agent_name, result.response_text,
                                    to_agent=None, meeting_id=meeting_id)
                opsdb.end_run(conn, run_id, "ended")
                return (True, None)
            else:
                sys.stderr.write(f"[control-center] meeting {meeting_id}: retry for {agent_name} failed "
                                  f"({result.error_kind}): {result.error}\n")
                opsdb.end_run(conn, run_id, "failed")
                return (False, result.error)
        except Exception:
            try:
                opsdb.end_run(conn, run_id, "failed")
            except (LookupError, ValueError):
                pass  # already ended somehow (e.g. by the branch that raised) — nothing more to reconcile
            raise
    finally:
        conn.close()
