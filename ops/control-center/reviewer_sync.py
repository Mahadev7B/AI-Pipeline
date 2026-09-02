"""ops/control-center/reviewer_sync.py — TASK-017 (risks.id=3 reduction
milestone).

Orchestration glue for the three new synchronous, zero-tool reviewer
routes server.py exposes: POST /api/tasks/<id>/review/{code,security,
red-team}. Mirrors automation.py's/meeting_orchestrator.py's own
separation from server.py: pure orchestration glue, imports opsdb/
agent_runtime/review_transcripts, never touches sqlite3 directly except
through opsdb.py functions, never invokes the runtime except through
agent_runtime.invoke_agent(). Full design:
ops/reviews/cto-risk3-milestone-architecture.md §1.

WHAT'S DIFFERENT FROM automation.py's POLLER, DELIBERATELY: there is no
claim-first ordering here and no automation_events-style caps. Both are
specific to the poller's own idempotency problem (a background process
must never silently re-process the same trigger forever) and its own
cost-control problem (an unattended loop needs a hard ceiling on how much
it can spend without a human in the loop). Neither applies to a route a
human just clicked "run this review now" on — a human re-running the same
review after a small fix is a legitimate, repeatable action, not a bug to
guard against (§1.4). `agent_runtime.invoke_agent()`'s own
MAX_CONCURRENT_INVOCATIONS semaphore and MAX_BUDGET_USD-per-call cap
still bound every individual invocation exactly as they do for every
other caller — nothing here bypasses those.

Same route/agent-name/gate-status mapping used throughout: 'code' ->
code-review agent, CODE_REVIEW gate; 'security' -> security agent,
SECURITY_REVIEW gate; 'red-team' -> red-team agent, RED_TEAM_REVIEW gate.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "db"))
import opsdb  # noqa: E402
import agent_runtime  # noqa: E402
import automation  # noqa: E402 — reuses automation._parse_verdict() directly, unchanged
                    # (§1.5: "the strictly-last-non-blank-line VERDICT: parsing... carr[ies]
                    # over unchanged to all three synchronous routes — same hardened,
                    # already-reviewed logic, reused, not reimplemented per kind").
import review_transcripts  # noqa: E402

MAX_ARTIFACT_PATHS = 5  # §1.3.3

_REVIEW_KIND_TO_AGENT = {"code": "code-review", "security": "security", "red-team": "red-team"}
_REVIEW_KIND_TO_GATE_STATUS = {"code": "CODE_REVIEW", "security": "SECURITY_REVIEW", "red-team": "RED_TEAM_REVIEW"}
# review_results.review_type's schema CHECK only allows 'code'/'security'
# (ops/db/schema.sql) — there is no 'red-team' review_type, and this
# milestone does not add one (out of scope: it would be a schema change
# to an already-reviewed table, not something §1 asks for). Red Team's
# own established convention throughout this project's review history
# (e.g. every "Recorded via `python3 ops/db/opsdb.py review-result
# --type code --by red-team ...`" citation in
# ops/reviews/red-team-risk3-milestone-review.md itself) already records
# a Red Team verdict under review_type='code' with
# reviewed_by_agent='red-team' — reused here, not a new convention
# invented for this route.
_REVIEW_KIND_TO_REVIEW_TYPE = {"code": "code", "security": "security", "red-team": "code"}
# §1.5's mechanical-rollback rule ("REJECT is a mechanical status rollback
# only, never a new Developer invocation") generalized to all three gates
# by the same logic each gate already uses elsewhere in this codebase:
# code/security review failures return to Developer (matches
# automation.py's own code-review-reject handling, and
# .claude/agents/security.md's own "--returned-to developer" instruction)
# for a fix at IN_DEVELOPMENT; a Red Team reject on an architecture
# artifact returns to CTO (matches this very milestone's own review
# history — every red-team-risk3 review recorded
# "--returned-to cto") for revision at ARCHITECTURE. CTO's architecture
# document does not spell out this per-kind destination explicitly; this
# mapping is the direct, non-improvised consequence of gate semantics
# already established elsewhere in this codebase, not new architecture —
# see the completion note for this task for the explicit call-out.
_REJECT_ROUTING = {
    "code": ("developer", "IN_DEVELOPMENT"),
    "security": ("developer", "IN_DEVELOPMENT"),
    "red-team": ("cto", "ARCHITECTURE"),
}


class ReviewNotEligible(Exception):
    """A 400-class condition: the task/handoff/artifact doesn't currently
    qualify for this review (wrong gate status, no completed handoff,
    invalid recorded SHA/file path, missing/invalid/uncommitted artifact
    path). Deliberately NOT a ValueError — this codebase's own convention
    (start_ask_agent_run(), decide_approval()) already uses ValueError for
    a 409-class "already in progress/already decided" condition; keeping
    this a distinct type lets server.py's handler map the two to the
    right HTTP status without guessing from a message string."""


def _run_diff_review_sync(task_id: int, kind: str) -> str | None:
    """Shared implementation for 'code' and 'security' — Both reuse the
    SAME transcript-assembly primitives (§1.3.1). Returns the verdict
    ('pass'/'reject') on a review that genuinely completed, or None if the
    invocation failed or produced no parseable VERDICT: line (still ends
    the reviewer_invocations/agent_runs rows as 'failed' — an honest,
    non-exceptional outcome, matching automation.py's own §B.8 handling —
    never raises for that case). Raises LookupError (no such task),
    ReviewNotEligible (400-class), or ValueError/sqlite3.OperationalError
    propagated unchanged from opsdb.start_ask_agent_run() (409-class
    "already in progress" / lock contention)."""
    agent_name = _REVIEW_KIND_TO_AGENT[kind]
    gate_status = _REVIEW_KIND_TO_GATE_STATUS[kind]

    conn = opsdb.connect()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task_row is None:
            raise LookupError(f"no such task TASK-{task_id:03d}")
        # Red Team's TASK-017 milestone review §3, non-blocking note:
        # the handoffs-lookup query doesn't check current task stage
        # before running — a stale re-trigger after the task already
        # progressed past this gate would otherwise attempt a real
        # review/status write against content that's no longer current.
        # Closed here with an explicit, friendly check rather than relying
        # on record_task_status()'s own transition logic, which (verified
        # directly against ops/db/opsdb.py for this task) enforces no
        # from-status/to-status legality at all — see this task's
        # completion note for why this is called out explicitly.
        if task_row["status"] != gate_status:
            raise ReviewNotEligible(
                f"TASK-{task_id:03d} is not currently at the {gate_status} gate "
                f"(current status: {task_row['status']}) — a {kind} review cannot be run against it right now.")
        handoff_row = conn.execute(
            "SELECT * FROM handoffs WHERE task_id = ? AND from_agent = 'developer' "
            "AND to_agent = 'code-review' ORDER BY id DESC LIMIT 1",
            (task_id,),
        ).fetchone()
    finally:
        conn.close()

    if handoff_row is None:
        raise ReviewNotEligible("no completed Developer handoff found for this task — nothing to review yet.")

    base_sha = handoff_row["base_commit_sha"]
    head_sha = handoff_row["head_commit_sha"]
    if not base_sha or not head_sha:
        raise ReviewNotEligible("handoff is missing recorded base/head commit SHAs — cannot assemble a diff.")
    if not (review_transcripts._SHA_RE.match(base_sha) and review_transcripts._SHA_RE.match(head_sha)):
        raise ReviewNotEligible("recorded base/head SHA does not resolve to a real commit in this repository.")
    if not (review_transcripts._commit_exists(base_sha) and review_transcripts._commit_exists(head_sha)):
        raise ReviewNotEligible("recorded base/head SHA does not resolve to a real commit in this repository.")

    try:
        files_changed = json.loads(handoff_row["files_changed"] or "[]")
    except (json.JSONDecodeError, TypeError):
        files_changed = None
    if not isinstance(files_changed, list) or not files_changed:
        raise ReviewNotEligible("handoff has no usable files_changed list.")
    validated_paths: list[str] = []
    for entry in files_changed:
        if not isinstance(entry, str) or not review_transcripts._validate_repo_path(entry):
            raise ReviewNotEligible(f"invalid file path in handoff: {entry!r}")
        validated_paths.append(entry)

    transcript, truncated = review_transcripts.assemble_diff_review_transcript(
        task_row, handoff_row, base_sha, head_sha, validated_paths, kind="synchronous")

    return _invoke_and_record(task_id, kind, agent_name, transcript, truncated,
                               base_commit_sha=base_sha, head_commit_sha=head_sha, artifact_paths=None)


def run_code_review_sync(task_id: int) -> str | None:
    return _run_diff_review_sync(task_id, "code")


def run_security_review_sync(task_id: int) -> str | None:
    return _run_diff_review_sync(task_id, "security")


def run_red_team_review_sync(task_id: int, artifact_paths: list[str]) -> str | None:
    """§1.3.3: artifact-scoped, not diff-scoped. `artifact_paths` is
    already form-split/stripped by server.py; validated here. The server
    — never the client — computes head_sha at request time."""
    if not artifact_paths:
        raise ReviewNotEligible("at least one artifact_paths entry is required.")
    if len(artifact_paths) > MAX_ARTIFACT_PATHS:
        raise ReviewNotEligible(f"at most {MAX_ARTIFACT_PATHS} artifact_paths entries are allowed.")

    conn = opsdb.connect()
    try:
        task_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    finally:
        conn.close()
    if task_row is None:
        raise LookupError(f"no such task TASK-{task_id:03d}")
    if task_row["status"] != "RED_TEAM_REVIEW":
        raise ReviewNotEligible(
            f"TASK-{task_id:03d} is not currently at the RED_TEAM_REVIEW gate "
            f"(current status: {task_row['status']}) — a red-team review cannot be run against it right now.")

    for p in artifact_paths:
        if not review_transcripts._validate_repo_path(p):
            raise ReviewNotEligible(f"invalid or unsafe artifact path: {p!r}")

    head_sha = review_transcripts.current_head_sha()
    if head_sha is None:
        raise ReviewNotEligible("could not determine the current commit (git rev-parse HEAD failed).")

    paths_with_content: list[tuple[str, str | None]] = []
    for p in artifact_paths:
        content = review_transcripts._git_show_file(head_sha, p)
        if content is None:
            # §1.3.3: "If the named path doesn't exist at HEAD (not yet
            # committed, or a typo), the route fails closed with a 400
            # before any model invocation — no silent partial review."
            raise ReviewNotEligible(
                f"{p!r} does not exist at HEAD ({head_sha[:12]}) — not yet committed, or a typo.")
        paths_with_content.append((p, content))

    transcript, truncated = review_transcripts.assemble_artifact_review_transcript(
        task_row, head_sha, paths_with_content)

    return _invoke_and_record(task_id, "red-team", "red-team", transcript, truncated,
                               base_commit_sha=None, head_commit_sha=head_sha, artifact_paths=artifact_paths)


def _invoke_and_record(task_id: int, kind: str, agent_name: str, transcript: str, truncated: bool,
                        base_commit_sha: str | None, head_commit_sha: str | None,
                        artifact_paths: list[str] | None) -> str | None:
    """The real, zero-tool invocation, and every one of §B.8's four
    outcomes (pass / reject / invocation failure / parse-failure),
    generalized across all three reviewer kinds — same hardened logic
    automation.py's own _invoke_and_record() already established,
    reused, not reimplemented per kind (§1.5). agent_runs is started via
    opsdb.start_ask_agent_run() — the same generic, already-hardened
    function Ask-Agent uses (§1.4) — BEFORE the reviewer_invocations row,
    so a failure creating the latter still leaves a clean, ended
    agent_runs row rather than one stuck open."""
    conn = opsdb.connect()
    try:
        run_id = opsdb.start_ask_agent_run(
            conn, agent_name, agent_runtime.REVIEWER_SYNC_ACTIVITY_LABEL, agent_runtime.REVIEWER_SYNC_ACTIVITY_LIKE)
    finally:
        conn.close()
    # ValueError ("already in progress") / sqlite3.OperationalError (lock
    # contention) propagate to the caller unchanged — same convention
    # _handle_ask() already relies on for Ask-Agent.

    invocation_id = None
    try:
        conn = opsdb.connect()
        try:
            invocation_id = opsdb.start_reviewer_invocation(
                conn, task_id, kind, agent_name, triggered_by="founder",
                base_commit_sha=base_commit_sha, head_commit_sha=head_commit_sha,
                artifact_paths=artifact_paths)
        finally:
            conn.close()

        result = agent_runtime.invoke_agent(agent_name, transcript, timeout_s=agent_runtime.REVIEW_TIMEOUT_S)

        if not result.ok:
            sys.stderr.write(
                f"[reviewer_sync] task={task_id}: synchronous {kind} review invocation failed "
                f"({result.error_kind}): {review_transcripts._truncate_for_log(result.error or '')}\n"
            )
            _end_run_and_invocation(run_id, invocation_id, "failed", outcome="error",
                                     cost_usd=result.cost_usd, truncated=truncated,
                                     skip_reason=f"invocation failed ({result.error_kind})")
            return None

        verdict = automation._parse_verdict(result.response_text)
        if verdict is None:
            sys.stderr.write(
                f"[reviewer_sync] task={task_id}: synchronous {kind} review reply had no VERDICT: line as "
                f"the strictly-last non-blank line — parse failure, not a guess\n"
            )
            _end_run_and_invocation(run_id, invocation_id, "failed", outcome="error",
                                     cost_usd=result.cost_usd, truncated=truncated,
                                     skip_reason="review reply had no parseable VERDICT: line")
            return None

        findings = [agent_runtime.clip_for_storage(result.response_text)]
        review_type = _REVIEW_KIND_TO_REVIEW_TYPE[kind]
        conn = opsdb.connect()
        try:
            # TASK-020 (Milestone B), Red Team's review (required fix #2):
            # this end_run() call deliberately does NOT pass
            # cost_usd=result.cost_usd, even though that real,
            # already-computed value sits right here (and IS passed to
            # opsdb.end_reviewer_invocation() a few lines below). DEC-009's
            # Milestone B boundary explicitly excludes TASK-017/risks.id=3/
            # reviewer_sync.py — this file is not touched functionally by
            # that milestone. The disclosed consequence: as long as
            # TASK-017 stays paused (DEC-008), every "Synchronous review"
            # agent_runs row will have cost_usd = NULL by construction, not
            # just historically — not a Milestone B bug, and not something
            # end_run()'s now-existing cost_usd column fixes on its own.
            # See generate_costs.py's "Synchronous review" by-path row for
            # the Founder-facing side of this same disclosure.
            opsdb.end_run(conn, run_id, "ended")
            if verdict == "pass":
                # §1.5: PASS never auto-advances the task — a human still
                # does that. reviewed_by_agent/agent_run_id/review_result_id
                # are what distinguish a synchronous session from a
                # human-supervised interactive one, not a change to the
                # shared review_results table's shape.
                review_id = opsdb.record_review_result(conn, task_id, review_type, agent_name, "pass",
                                                         findings=findings)
                opsdb.end_reviewer_invocation(conn, invocation_id, "completed", outcome="pass",
                                               review_result_id=review_id, agent_run_id=run_id,
                                               cost_usd=result.cost_usd, truncated=truncated)
            else:
                returned_to, rollback_status = _REJECT_ROUTING[kind]
                review_id = opsdb.record_review_result(conn, task_id, review_type, agent_name, "reject",
                                                         findings=findings, returned_to=returned_to)
                # §1.5: a single, mechanical tasks.status transition — pure
                # bookkeeping, NEVER a new agent model invocation.
                opsdb.record_task_status(
                    conn, task_id, rollback_status, changed_by_agent="orchestrator",
                    note=f"[Synchronous review, TASK-017] {agent_name} rejected — routed back to "
                         f"{returned_to} (reviewer_invocations id={invocation_id}).",
                )
                opsdb.end_reviewer_invocation(conn, invocation_id, "completed", outcome="reject",
                                               review_result_id=review_id, agent_run_id=run_id,
                                               cost_usd=result.cost_usd, truncated=truncated)
        finally:
            conn.close()
        return verdict
    except Exception:
        # Code Review, TASK-009's own precedent (server.py's _handle_ask):
        # an unhandled exception anywhere in this block must still end the
        # already-created agent_runs row (and, if it exists yet, the
        # reviewer_invocations row) as 'failed', or either stays open
        # until the next server restart's reconciliation pass — and, for
        # reviewer_invocations, there IS no startup reconciliation pass
        # (§1.4: no claim to reconcile against), so leaving one open here
        # would be permanent, not just until next restart.
        conn = opsdb.connect()
        try:
            try:
                opsdb.end_run(conn, run_id, "failed")
            except (LookupError, ValueError):
                pass  # already ended somehow — nothing more to reconcile
            if invocation_id is not None:
                try:
                    opsdb.end_reviewer_invocation(conn, invocation_id, "failed", outcome="error",
                                                   agent_run_id=run_id,
                                                   skip_reason="unhandled error during synchronous review")
                except (LookupError, ValueError):
                    pass  # already ended somehow — nothing more to reconcile
        finally:
            conn.close()
        raise


def _end_run_and_invocation(run_id: int, invocation_id: int, status: str, outcome: str | None,
                             cost_usd: float | None, truncated: bool, skip_reason: str) -> None:
    conn = opsdb.connect()
    try:
        opsdb.end_run(conn, run_id, "failed")
        opsdb.end_reviewer_invocation(conn, invocation_id, status, outcome=outcome, agent_run_id=run_id,
                                       cost_usd=cost_usd, truncated=truncated, skip_reason=skip_reason)
    finally:
        conn.close()
