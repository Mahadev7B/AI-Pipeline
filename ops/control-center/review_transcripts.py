"""ops/control-center/review_transcripts.py — TASK-017 (risks.id=3
reduction milestone).

Extracted from automation.py, unchanged internals (a pure move — see
ops/reviews/cto-risk3-milestone-architecture.md §5): the git-object-
database-backed transcript-assembly primitives Code Review's automated
invocation already used, and Security's Stage 2 §1.1 independently
verified line-by-line. Both automation.py's poller and the new
synchronous reviewer routes (reviewer_sync.py) import from here, so
"reuse" is a real shared import, not a second, drifting copy.

Also home to two things new in this milestone:
- `assemble_artifact_review_transcript()` — Red Team's artifact-scoped
  review (§1.3.3): retrieves one or more repo-relative files' *committed*
  content at a server-computed HEAD sha, never a working-tree read.
- `build_instructions_block()` — the parameterized instruction-block
  builder (§1.5): the SAME underlying content is assembled either way;
  only the trailing instructions text differs by trigger kind
  ("automated" — the poller's existing text, unchanged — or
  "synchronous" — new, factually accurate for a human-triggered
  invocation, not the poller's "AUTOMATED mode" wording).
"""
from __future__ import annotations

import re
import subprocess
import sys
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CODING_STANDARDS_PATH = REPO_ROOT / "ops" / "CODING_STANDARDS.md"

# §B.1/§B.13/Security's required fix C1 (Phase 3A): SHA format validation,
# before ANY git subprocess call ever touches a caller-supplied SHA.
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

_GIT_TIMEOUT_S = 30.0
_MAX_LOG_CHARS = 2_000  # matches agent_runtime.py's own stderr_text[:2000] truncation

MAX_REVIEW_TRANSCRIPT_CHARS = 60_000


def _truncate_for_log(text: str) -> str:
    return text[:_MAX_LOG_CHARS]


def _commit_exists(sha: str) -> bool:
    """Security's required fix C1 (Phase 3A): confirms a SHA resolves to a
    real commit object in THIS repository before it is trusted for a diff
    — `git cat-file -e <sha>^{commit}` is a read-only existence check, no
    output."""
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", "--", f"{sha}^{{commit}}"],
            cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[review_transcripts] git cat-file failed for {sha!r}: {type(exc).__name__}: {exc}\n")
        return False
    return result.returncode == 0


def _validate_repo_path(rel_path: str) -> bool:
    """§B.1.2's required path validation, exactly: reject absolute paths,
    reject anything where Path(repo_root, path).resolve() does not remain
    inside repo_root, reject a '..' component after normalization
    (redundant with resolve() but cheap, per the doc). Any exception while
    normalizing is treated as an invalid path, not allowed to propagate
    uncaught."""
    try:
        p = Path(rel_path)
        if p.is_absolute():
            return False
        if any(part == ".." for part in p.parts):
            return False
        resolved = (REPO_ROOT / rel_path).resolve()
        resolved.relative_to(REPO_ROOT.resolve())
    except (ValueError, OSError):
        return False
    return True


def _git_diff(base_sha: str, head_sha: str, paths: list[str]) -> str:
    """Fixed argv, never a shell string. `--` separates the two revision
    arguments from the pathspec arguments that follow (Security's
    required fix C1, Phase 3A)."""
    cmd = ["git", "--no-pager", "diff", "--no-color", base_sha, head_sha, "--", *paths]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[review_transcripts] git diff failed: {type(exc).__name__}: {exc}\n")
        return "(git diff could not be computed)"
    if result.returncode != 0:
        sys.stderr.write(f"[review_transcripts] git diff exited {result.returncode}: "
                          f"{_truncate_for_log(result.stderr.decode('utf-8', errors='replace'))}\n")
        return "(git diff could not be computed)"
    return result.stdout.decode("utf-8", errors="replace")


def _git_show_file(head_sha: str, path: str) -> str | None:
    """Retrieves the file's committed content from git's OWN OBJECT
    DATABASE (`git show <sha>:<path>`), never a live filesystem read of
    the working tree — closes a working-tree symlink/TOCTOU exposure more
    robustly than path validation alone: git never touches a filesystem
    symlink at this path when resolving a tree object.

    Deliberately NOT given a `--` separator before the combined
    `<sha>:<path>` object argument — `git show -- <sha>:<path>` silently
    treats the whole string as a PATHSPEC instead of an object reference.
    This form is safe without `--` regardless: the argument always begins
    with `head_sha`, which `_SHA_RE`/`_commit_exists()` have already
    confirmed is pure lowercase hex — it can never be misread as a
    `-`-prefixed option."""
    cmd = ["git", "--no-pager", "show", f"{head_sha}:{path}"]
    try:
        result = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[review_transcripts] git show failed for {path!r}: {type(exc).__name__}: {exc}\n")
        return None
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="replace")


def current_head_sha() -> str | None:
    """New in this milestone (§1.3.3): the server — never the client —
    computes `head_sha = git rev-parse HEAD` at request time, for Red
    Team's artifact-scoped synchronous review. Matches this codebase's own
    "server computes trusted values, never trusts client input for
    anything security-relevant" convention."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"[review_transcripts] git rev-parse HEAD failed: {type(exc).__name__}: {exc}\n")
        return None
    if result.returncode != 0:
        return None
    sha = result.stdout.decode("utf-8", errors="replace").strip()
    return sha if _SHA_RE.match(sha) else None


def _read_coding_standards() -> str:
    try:
        return CODING_STANDARDS_PATH.read_text()
    except OSError as exc:
        sys.stderr.write(f"[review_transcripts] could not read CODING_STANDARDS.md: {type(exc).__name__}: {exc}\n")
        return "(CODING_STANDARDS.md could not be read)"


def build_instructions_block(kind: str, truncated: bool) -> str:
    """§1.5: ONE implementation, two accurate instruction variants, not a
    copy-pasted-and-forgotten second version. `kind` is 'automated' (the
    poller's pre-existing text, unchanged) or 'synchronous' (new — a
    human clicked a button, this is not an unattended background
    process)."""
    truncation_note = (
        "\n\nNOTE: the content above was truncated to fit this review's size limit — you do not have "
        "the complete picture. Per your role doc's automated-invocation note, a truncated transcript "
        "must not receive VERDICT: PASS.\n"
        if truncated else ""
    )
    if kind == "automated":
        body = (
            "\n\nYou are reviewing this in AUTOMATED mode — a narrower context than a human-supervised "
            "session (see your role doc's automated-invocation note for exactly what this means and what "
            "it structurally cannot catch). Give your real findings, then end your entire reply with, as "
            "the STRICTLY LAST non-blank line, exactly one of:\nVERDICT: PASS\nVERDICT: REJECT"
        )
    elif kind == "synchronous":
        body = (
            "\n\nYou are reviewing this in SYNCHRONOUS mode — invoked directly, on demand, by a human "
            "clicking 'run this review now,' not by an unattended background process. Like the automated "
            "poller's invocation, you have **no** Bash/Read/Grep/Glob access in this mode — everything you "
            "need has been assembled below, deterministically, by this project's own Python code. If you "
            "find you need to explore beyond what's provided to render a real verdict, say so explicitly in "
            "your findings and end with the same REJECT/incomplete-context handling below — the human who "
            "triggered this can then run a separate, fully tool-bearing interactive session for that "
            "specific need, the same way they always could. Give your real findings, then end your entire "
            "reply with, as the STRICTLY LAST non-blank line, exactly one of:\nVERDICT: PASS\nVERDICT: REJECT"
        )
    else:
        raise ValueError(f"kind must be 'automated' or 'synchronous', got {kind!r}")
    return f"{body}{truncation_note}"


def assemble_diff_review_transcript(task_row: sqlite3.Row, handoff_row: sqlite3.Row, base_sha: str,
                                     head_sha: str, paths: list[str], kind: str) -> tuple[str, bool]:
    """§B.1's bullet list (Phase 3A), assembled by deterministic Python —
    never real tool grants for the invocation this feeds, automated or
    synchronous alike. Graceful, disclosed truncation at
    MAX_REVIEW_TRANSCRIPT_CHARS if exceeded — the instructions block
    (including the truncation notice, when present) is appended AFTER
    truncation, so the model always receives the real VERDICT: instruction
    regardless of how much content had to be cut. `kind` selects which
    instruction-block variant (§1.5) — everything else is identical for
    'automated' and 'synchronous'."""
    parts: list[str] = []
    parts.append(f"TASK-{task_row['id']:03d}: {task_row['title']}")
    if task_row["business_goal"]:
        parts.append(f"Business goal: {task_row['business_goal']}")
    if task_row["acceptance_criteria"]:
        parts.append(f"Acceptance criteria: {task_row['acceptance_criteria']}")
    if task_row["architecture_notes"]:
        parts.append(f"Architecture notes: {task_row['architecture_notes']}")
    if task_row["tests_required"]:
        parts.append(f"Tests required: {task_row['tests_required']}")

    parts.append("")
    parts.append("Developer's handoff record:")
    if handoff_row["work_completed"]:
        parts.append(f"Work completed: {handoff_row['work_completed']}")
    parts.append(f"Files changed: {handoff_row['files_changed']}")
    if handoff_row["tests_added"]:
        parts.append(f"Tests added: {handoff_row['tests_added']}")
    if handoff_row["expected_behavior"]:
        parts.append(f"Expected behavior: {handoff_row['expected_behavior']}")
    if handoff_row["known_limitations"]:
        parts.append(f"Known limitations: {handoff_row['known_limitations']}")

    parts.append("")
    parts.append(f"git diff {base_sha}..{head_sha} (scoped to files_changed):")
    parts.append(_git_diff(base_sha, head_sha, paths))

    parts.append("")
    parts.append("Full final content of every changed/added file "
                  "(retrieved via `git show <head_sha>:<path>` — the committed object, never a working-tree read):")
    for path in paths:
        content = _git_show_file(head_sha, path)
        parts.append(f"--- {path} ---")
        parts.append(content if content is not None else "(could not retrieve this file's content from the commit)")

    parts.append("")
    parts.append("CODING_STANDARDS.md (verbatim):")
    parts.append(_read_coding_standards())

    content = "\n".join(parts)
    truncated = len(content) > MAX_REVIEW_TRANSCRIPT_CHARS
    if truncated:
        content = content[:MAX_REVIEW_TRANSCRIPT_CHARS] + "\n\n[content truncated at 60,000 characters]"

    return content + build_instructions_block(kind, truncated), truncated


def assemble_artifact_review_transcript(task_row: sqlite3.Row, head_sha: str,
                                         paths_with_content: list[tuple[str, str | None]]) -> tuple[str, bool]:
    """§1.3.3: Red Team's artifact-scoped synchronous review — a plan/
    architecture document, not a code diff. `paths_with_content` is
    already-retrieved (path, committed_content) pairs (content is None
    only if a path passed eligibility validation but retrieval somehow
    still failed — not expected in practice, since callers only reach
    here after `current_head_sha()`/`_git_show_file()` succeeded, but
    handled the same graceful way as the diff-review path rather than
    assumed impossible). Always 'synchronous' — there is no automated/
    poller mode for Red Team in this milestone."""
    parts: list[str] = []
    parts.append(f"TASK-{task_row['id']:03d}: {task_row['title']}")
    if task_row["business_goal"]:
        parts.append(f"Business goal: {task_row['business_goal']}")
    if task_row["acceptance_criteria"]:
        parts.append(f"Acceptance criteria: {task_row['acceptance_criteria']}")

    parts.append("")
    parts.append(f"Artifact(s) under review, retrieved via `git show {head_sha[:12]}:<path>` "
                  "(the committed object at the server-computed current HEAD, never a working-tree read):")
    for path, content in paths_with_content:
        parts.append(f"--- {path} ---")
        parts.append(content if content is not None else "(could not retrieve this file's content from the commit)")

    content = "\n".join(parts)
    truncated = len(content) > MAX_REVIEW_TRANSCRIPT_CHARS
    if truncated:
        content = content[:MAX_REVIEW_TRANSCRIPT_CHARS] + "\n\n[content truncated at 60,000 characters]"

    return content + build_instructions_block("synchronous", truncated), truncated
