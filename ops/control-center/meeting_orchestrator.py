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
    """Step 2: Orchestrator (this function's own validation) + CEO Agent
    (the real judgment call) select participants. CEO is always
    included by the caller (run_meeting), never decided here. Returns
    validated, deterministically-truncated candidate names only — never
    unvalidated text. On any invocation failure, returns an empty list
    (a meeting with just CEO is still a valid, honest meeting — never
    fabricate a selection when the real call failed)."""
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
    selected = _parse_selection(result.response_text)
    # Deterministic truncation at the cap (Red Team condition 2) — CEO is
    # added separately by the caller, so the cap here is MAX-1 others.
    return selected[: agent_runtime.MAX_MEETING_PARTICIPANTS - 1]


def _gather_position(meeting_id: int, agent_name: str, topic: str) -> tuple[str, bool, str | None]:
    """Runs in its own worker thread — opens and closes its own
    connection, never shares one across threads. Returns
    (agent_name, ok, position_text_or_None). Never fabricates a position
    on failure — persists the real agent_runs outcome either way."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_run(conn, agent_name, "meeting", agent_runtime.MEETING_ACTIVITY_LABEL, scope_id=meeting_id)
        prompt = (
            f"Founder: An Executive Meeting has been raised on this topic: \"{topic}\" "
            f"State your position from your own role and responsibilities — your real "
            f"assessment, not a generic opinion. Be concise (2-4 sentences)."
        )
        result = agent_runtime.invoke_agent(agent_name, prompt, wait_for_slot=True)
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
    positions gathered concurrently, bounded → CEO synthesizes). Returns
    the new meeting's id. Raises ValueError for a bad topic. Never
    raises for a participant/synthesis failure — those are recorded
    honestly and the meeting still completes with whatever real work
    succeeded."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty")
    if len(topic) > MAX_TOPIC_CHARS:
        raise ValueError(f"topic exceeds the {MAX_TOPIC_CHARS:,}-character limit")

    others = _select_participants(topic)
    participants = ["ceo"] + others  # CEO is always a participant — never optional

    conn = opsdb.connect()
    try:
        meeting_id = opsdb.create_meeting(conn, topic, "founder", participants)
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
