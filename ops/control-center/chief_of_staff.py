"""ops/control-center/chief_of_staff.py — Phase 3A Part A (TASK-015).

The Chief of Staff Founder conversational interface. Mirrors
meeting_orchestrator.py's separation from server.py: pure orchestration
glue, imports opsdb/agent_runtime/meeting_orchestrator/derived_state,
never touches sqlite3 directly except through opsdb.py functions, never
invokes the runtime except through agent_runtime.invoke_agent(). server.py's
POST /api/chief-of-staff/ask route calls only ask_chief_of_staff() — this
module owns every step (state-digest assembly, transcript building,
CONSULT: parsing, consult-meeting triggering, the second narration
invocation, response persistence).

Full design: ops/reviews/cto-phase3a-architecture.md §A.1-A.5;
independently reviewed in ops/reviews/security-phase3a-threat-model.md
and ops/reviews/red-team-phase3a-architecture.md (both folded into the
shipped design — see that document's "Correction" sections).

This is the first-ever real `claude --agent orchestrator` invocation in
this system's history. `orchestrator` is intentionally NOT in
agent_runtime.ASK_AGENT_ALLOWLIST — this module, and the dedicated
POST /api/chief-of-staff/ask route that calls it, is the ONLY way to
reach it. Every invocation still goes through agent_runtime.invoke_agent(),
which still runs `_run_claude()` with unconditional `--tools ""` /
`--strict-mcp-config` — nothing in this module can, or tries to, change
that.

PART B NOTE (not built here — see the Phase 3A architecture doc's Part
A/Part B split, Red Team's NB3): this module deliberately does not read
or write automation_events/automation_state (those tables don't exist
yet) and does not touch derived_state.automation_status_digest() (not
implemented yet, same reason).
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402
import agent_runtime  # noqa: E402
import meeting_orchestrator  # noqa: E402
import derived_state  # noqa: E402

AGENT_NAME = "orchestrator"
THREAD_ID = f"agent-{AGENT_NAME}-company"

# The whole rendered digest — every section's rows combined — is capped
# here, in addition to each derived_state.*_digest() helper's own
# `limit=` row cap. "One disclosed number, not a vibe" — same convention
# as server.py's MAX_ASK_MESSAGE_CHARS / agent_runtime.MAX_RESPONSE_CHARS.
# See ops/reviews/cto-phase3a-architecture.md §A.2.
MAX_STATE_DIGEST_CHARS = 6_000

# CONSULT: parsing (§A.3). The fixed, pre-approved candidate tuple,
# stated exactly once (Security's Phase 3A threat-model review, required
# fix C3): agent_runtime.MEETING_PARTICIPANT_ALLOWLIST with "ceo"
# removed. Reused directly from meeting_orchestrator.py — that module
# already computes this exact tuple for CEO's own participant
# nomination; this is the SAME tuple, not a second hand-typed copy.
# "orchestrator" was never a member of MEETING_PARTICIPANT_ALLOWLIST in
# the first place, so there is nothing to separately exclude for it — the
# Chief of Staff cannot name itself as a consult target because it was
# never in the candidate set to begin with.
_CONSULT_CANDIDATES = meeting_orchestrator.CONSULT_CANDIDATE_ROLES

# Matches a line beginning with "CONSULT:" (case-insensitive), anywhere
# in the reply — the label itself is required (so ordinary prose
# mentioning a role name, e.g. "CTO would probably weigh in here," never
# accidentally triggers a real meeting); only the text captured AFTER the
# label is ever scanned for candidate names, never the surrounding prose.
_CONSULT_LINE_RE = re.compile(r"^\s*CONSULT:\s*(.*)$", re.IGNORECASE | re.MULTILINE)


def _parse_consult(reply_text: str | None) -> list[str]:
    """Deterministic Python parsing — the model's raw reply is NEVER
    trusted as an instruction to execute, only ever a signal Python alone
    decides whether to act on. Identical trust pattern to
    meeting_orchestrator._parse_selection()'s existing handling of CEO's
    own participant nomination: lenient, case-insensitive, matched only
    against a fixed candidate tuple. A `CONSULT: ceo` or
    `CONSULT: orchestrator` line — Founder-typed or adversarially
    prompt-injected — simply never matches _CONSULT_CANDIDATES and has no
    effect; the parser's only behavior for an unrecognized name is to
    drop it.

    If more than one CONSULT: line is present (a malformed reply — the
    persona is instructed to emit at most one), the FIRST is used; this
    mirrors _select_participants()'s own lenient, no-fabrication style
    rather than requiring a strict single-line format, and is safe here
    specifically because names are only ever extracted from the text
    captured after the label, never from the reply's surrounding prose.

    Capped/deduped via meeting_orchestrator.cap_participants() — the
    SAME shared helper _validate_selection() uses for CEO's own
    nomination cap, so there is exactly one implementation of "at most
    MAX_MEETING_PARTICIPANTS - 1 others, deduped" in this codebase."""
    if not reply_text:
        return []
    m = _CONSULT_LINE_RE.search(reply_text)
    if not m:
        return []
    mentioned = m.group(1).lower()
    matched = [
        role for role in _CONSULT_CANDIDATES
        if re.search(rf"(?<![a-z0-9-]){re.escape(role)}(?![a-z0-9-])", mentioned)
    ]
    cap = agent_runtime.MAX_MEETING_PARTICIPANTS - 1
    capped, _dropped = meeting_orchestrator.cap_participants(matched, cap)
    return capped


def _build_state_digest(conn) -> str:
    """Assembles the bounded state digest (§A.2) — built fresh on every
    call, never cached across turns, so staleness within one conversation
    is structurally impossible: whatever this says is true as of the
    millisecond this specific call was made. Composes derived_state.py's
    read-only helpers — the single, shared implementation of every
    deterministic-state formula, not a second hand-typed copy living
    here."""
    lines: list[str] = []

    label, detail = derived_state.company_health(conn)
    lines.append(f"Company health: {label} ({detail})")

    lines.append("")
    lines.append("Agent status:")
    agent_rows = derived_state.agent_status_rows(conn)
    if agent_rows:
        for row in agent_rows:
            name = derived_state.display_name(row["name"])
            status = row["status"] or "available"
            activity = f" — {row['current_activity']}" if row["current_activity"] else ""
            lines.append(f"- {name}: {status}{activity}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Open / recently-changed risks:")
    risks = derived_state.open_risks_digest(conn)
    if risks:
        for r in risks:
            mitigation = f" — mitigation: {r['mitigation']}" if r["mitigation"] else ""
            lines.append(f"- risks.id={r['id']} [{r['severity']}/{r['status']}] {r['title']}{mitigation}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Active tasks (not DONE), most recently updated first:")
    tasks = derived_state.active_tasks_digest(conn)
    if tasks:
        for t in tasks:
            owner = f" — owner: {t['current_owner']}" if t["current_owner"] else ""
            blockers = f" — blockers: {t['blockers']}" if t["blockers"] else ""
            lines.append(f"- TASK-{t['id']:03d} [{t['status']}] {t['title']}{owner}{blockers}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Pending Founder approvals:")
    approvals = derived_state.pending_approvals_digest(conn)
    if approvals:
        for a in approvals:
            lines.append(
                f"- approvals.id={a['id']} [{a['decision']}] {a['request']} "
                f"(requested by {a['requested_by_agent']})"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Recent decisions:")
    decisions = derived_state.recent_decisions_digest(conn)
    if decisions:
        for d in decisions:
            lines.append(
                f"- decisions.id={d['id']} {d['title']}: {d['decision']} "
                f"(by {d['recommending_agent']}, {d['created_at']})"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Recent task status transitions:")
    transitions = derived_state.recent_status_transitions_digest(conn)
    if transitions:
        for tr in transitions:
            lines.append(
                f"- TASK-{tr['task_id']:03d}: {tr['from_status'] or '(new)'} -> {tr['to_status']} "
                f"(by {tr['changed_by_agent']}, {tr['changed_at']})"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Recent review/QA results:")
    review_qa = derived_state.recent_review_qa_digest(conn)
    if review_qa:
        for rq in review_qa:
            subtype = f" {rq['subtype']}" if rq["subtype"] else ""
            lines.append(
                f"- TASK-{rq['task_id']:03d} {rq['kind']}{subtype} by {rq['by_agent']}: "
                f"{rq['result']} ({rq['created_at']})"
            )
    else:
        lines.append("- none")

    lines.append("")
    lines.append("Recent deployments:")
    deployments = derived_state.recent_deployments_digest(conn)
    if deployments:
        for dep in deployments:
            lines.append(
                f"- TASK-{dep['task_id']:03d} v{dep['version']} to {dep['environment']} "
                f"by {dep['deployed_by_agent']} ({dep['deployed_at']})"
            )
    else:
        lines.append("- none")

    digest = "\n".join(lines)
    if len(digest) > MAX_STATE_DIGEST_CHARS:
        digest = digest[:MAX_STATE_DIGEST_CHARS] + "\n[state digest truncated at 6,000 characters]"
    return digest


def _now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _build_transcript(conn, digest: str) -> str:
    """Digest, prepended as a clearly labeled block, followed by the
    persisted agent-orchestrator-company thread's prior turns — reads
    `messages WHERE thread_id = ?` the same way server.py's own
    _build_transcript() already reads Ask-Agent's thread (reused as a
    read PATTERN, not a shared import — chief_of_staff.py must not import
    server.py, which imports this module). The Founder's newest message
    is already persisted by the caller before this is built, so it
    naturally appears as the transcript's last line."""
    header = f"CURRENT COMPANY STATE (as of {_now_iso()}):\n{digest}"

    rows = conn.execute(
        "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
        (THREAD_ID,),
    ).fetchall()
    lines = [header, ""]
    for r in rows:
        speaker = "Founder" if r["from_agent"] == "founder" else derived_state.display_name(AGENT_NAME)
        lines.append(f"{speaker}: {r['body']}")
    return "\n".join(lines)


def _build_narration_transcript(conn, digest: str, meeting_id: int, topic: str) -> str:
    """§A.3/§A.4 — the SECOND Chief of Staff invocation's transcript,
    once a consult meeting has completed. Includes everything
    _build_transcript() already includes (fresh digest + the full
    persisted conversation, ending with the Founder's original message)
    PLUS the real, persisted per-agent positions and CEO's real synthesis
    from the meeting that just ran — read from the actual
    meetings/messages(scope='meeting') rows, the same data anyone
    browsing /meetings/<id>.html sees, never a second, parallel
    representation of it. Asks the model to narrate a final,
    Founder-addressed answer in its own voice (§A.4's WHAT HAPPENED / WHY
    IT MATTERS / MY RECOMMENDATION / WHAT I NEED FROM YOU structure) —
    this reply, not the first turn's raw CONSULT: line, is what gets
    persisted and shown to the Founder."""
    base = _build_transcript(conn, digest)

    meeting_row = conn.execute(
        "SELECT agreements, disagreements, unresolved_questions, recommendation FROM meetings WHERE id = ?",
        (meeting_id,),
    ).fetchone()
    positions = conn.execute(
        "SELECT from_agent, body FROM messages WHERE thread_id = ? ORDER BY id",
        (f"meeting-{meeting_id}",),
    ).fetchall()

    lines = [
        base,
        "",
        f'Founder: I asked you to consult on this: "{topic}" An Executive Meeting (#{meeting_id}) was just '
        f"held for real. Here are the real, gathered positions from that meeting:",
        "",
    ]
    for p in positions:
        lines.append(f"{p['from_agent']}: {p['body']}")
    lines.append("")
    lines.append("CEO's real synthesis of that meeting:")
    lines.append(f"Agreements: {meeting_row['agreements'] if meeting_row and meeting_row['agreements'] else 'None.'}")
    lines.append(
        f"Disagreements: {meeting_row['disagreements'] if meeting_row and meeting_row['disagreements'] else 'None.'}"
    )
    lines.append(
        f"Unresolved: "
        f"{meeting_row['unresolved_questions'] if meeting_row and meeting_row['unresolved_questions'] else 'None.'}"
    )
    lines.append(
        f"CEO's recommendation: "
        f"{meeting_row['recommendation'] if meeting_row and meeting_row['recommendation'] else 'None.'}"
    )
    lines.append("")
    lines.append(
        f"Founder: Based on the real positions and CEO's synthesis above, give me your final answer now, in "
        f"your own voice, addressed to me directly. Reference Meeting #{meeting_id} so I can look at the full "
        f"detail if I want to. Do not include a CONSULT: line this time — the consultation already happened."
    )
    return "\n".join(lines)


def ask_chief_of_staff(message: str) -> None:
    """The whole flow for one Founder <-> Chief of Staff exchange
    (§A.1-A.5): claim the "one open exchange at a time" run guard ->
    persist the Founder's message -> assemble a fresh state digest + this
    thread's prior turns -> invoke orchestrator (the first real
    `claude --agent orchestrator` invocation in this system's history) ->
    parse CONSULT: out of the reply, never persisted or shown raw -> if
    present, run a real consult meeting and make a SECOND Chief of Staff
    invocation to narrate the final, Founder-addressed answer -> persist
    whichever reply is the real final answer -> end the run.

    Raises LookupError / ValueError / sqlite3.OperationalError from
    opsdb.start_ask_agent_run() — propagated uncaught; server.py maps
    those to 404/409/503, the same convention every other write route in
    this codebase uses (identical to _handle_ask()'s own contract).
    Never raises for an invocation failure — that is recorded honestly
    (agent_runs 'failed', no fabricated reply) and this function returns
    normally, same discipline _handle_ask()/meeting_orchestrator.py
    already use for a real, non-contract-violation failure."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_ask_agent_run(
            conn, AGENT_NAME, agent_runtime.CHIEF_OF_STAFF_ACTIVITY_LABEL, agent_runtime.CHIEF_OF_STAFF_ACTIVITY_LIKE
        )
    finally:
        conn.close()

    conn = opsdb.connect()
    try:
        try:
            opsdb.send_message(conn, THREAD_ID, "agent", "founder", message, to_agent=AGENT_NAME)

            digest = _build_state_digest(conn)
            transcript = _build_transcript(conn, digest)
            result = agent_runtime.invoke_agent(AGENT_NAME, transcript)

            if not result.ok:
                # No response message on failure — never fabricate an
                # answer. The failed run itself is the honest record.
                sys.stderr.write(
                    f"[control-center] Chief of Staff invocation failed ({result.error_kind}): {result.error}\n"
                )
                opsdb.end_run(conn, run_id, "failed")
                return

            consult_targets = _parse_consult(result.response_text)
            if consult_targets:
                # The first reply's raw text (including its CONSULT: line)
                # is discarded here — the Founder never sees it. Only the
                # second, narrated reply below is persisted/shown.
                meeting_id = meeting_orchestrator.run_consult_meeting(
                    message, consult_targets, initiated_by="founder"
                )
                # Fresh digest again — this really is a distinct model
                # turn/invocation, and the consult meeting itself can take
                # real time (§A.3's disclosed UX consequence), so "fresh,
                # every turn" is honored at the invocation level, not just
                # the message level.
                narration_digest = _build_state_digest(conn)
                narration_transcript = _build_narration_transcript(conn, narration_digest, meeting_id, message)
                narration_result = agent_runtime.invoke_agent(AGENT_NAME, narration_transcript)
                if narration_result.ok:
                    final_text = narration_result.response_text
                else:
                    sys.stderr.write(
                        f"[control-center] Chief of Staff narration invocation failed "
                        f"({narration_result.error_kind}): {narration_result.error}\n"
                    )
                    # A real, evidence-based fallback, not a fabrication —
                    # the meeting genuinely happened and is genuinely
                    # persisted; only the narration step itself failed.
                    final_text = (
                        f"I consulted the team on this — see Meeting #{meeting_id} for the full, real "
                        f"discussion — but I ran into a problem summarizing it for you just now. Please "
                        f"check the meeting directly, or ask me again."
                    )
            else:
                final_text = result.response_text

            opsdb.send_message(conn, THREAD_ID, "agent", AGENT_NAME, final_text, to_agent="founder")
            opsdb.end_run(conn, run_id, "ended")
        except Exception:
            try:
                opsdb.end_run(conn, run_id, "failed")
            except (LookupError, ValueError):
                pass  # already ended somehow — nothing more to reconcile
            raise
    finally:
        conn.close()
