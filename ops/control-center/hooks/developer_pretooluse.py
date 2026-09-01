#!/usr/bin/env python3
"""ops/control-center/hooks/developer_pretooluse.py — TASK-017 (risks.id=3
reduction milestone).

The self-immune Developer denylist's `PreToolUse` hook. Registered ONLY
in `.claude/agents/developer.md`'s own `hooks:` frontmatter (§2.1 of
ops/reviews/cto-risk3-milestone-architecture.md) — nowhere else. Denies
Write/Edit (typed `file_path`, the primary defense) and Bash (string
matching, an explicitly-disclosed coarser backstop) tool calls that touch
a small set of protected paths: the Founder credential file, the
operational database, `ptrace`/`sudo`/`gdb`/`strace`, and this hook's own
defining files (self-protection, closing Red Team's Stage 3 S8 finding).

FAIL-CLOSED CONTRACT (§2.2a — REQUIRED, not optional hardening; added and
twice corrected across three Red Team review rounds — see
ops/reviews/red-team-risk3-milestone-review.md §1, §6, §7 for the full
correction history. Do NOT "simplify" this structure without re-reading
that history first): Claude Code's own PreToolUse hook dispatch (`iI()`/
`rZ6()` in the installed CLI's cli.js) fails OPEN — i.e. silently ALLOWS
the tool call — on any hook exit code other than exactly 2, including
Python's own default behavior on an uncaught exception (traceback to
stderr, exit code 1). The structure below exists ONLY to make that
impossible for this hook:

  1. Every parsing/evaluation step that can raise on ordinary,
     non-adversarial input (`json.loads`, `Path.resolve()`,
     `shlex.split()`) runs inside ONE `try` block in main(), guarded by
     `except BaseException` — not `except Exception`, because a stray
     `sys.exit()` anywhere (present or future) raises `SystemExit`, a
     direct subclass of `BaseException`, not of `Exception`.
  2. The legitimate exit calls — BOTH the success path's own
     `sys.exit(...)` AND the exception handler's own `sys.exit(2)` — sit
     OUTSIDE any `try` block whose matching `except` could re-catch their
     own `SystemExit`. Nesting either inside the guarded region would
     force every invocation (allowed or denied alike) through the
     exception handler, denying 100% of tool calls unconditionally — the
     exact bug Red Team's second-pass review caught in an earlier draft
     of this structure (see that review's §6.3).
  3. The exception handler's own two calls (`_emit_decision`,
     `_best_effort_log_internal_error`) are themselves wrapped in a
     nested `try/except BaseException`, falling back to a hardcoded
     stdout write if even THEY raise — no further logic that could itself
     fail (Red Team's second-pass review, §6.4).
  4. For every deny decision — including the exception-handling fallback
     — BOTH signals are emitted: the JSON form
     (`hookSpecificOutput.permissionDecision: "deny"`) as the ONLY
     content on stdout (checked and honored by the harness before exit
     code is even examined), AND exit code 2 (the fallback carrier of
     intent, and what surfaces the human-visible "hook blocking error").

No subprocess calls of its own (stdlib only: sys/json/shlex/pathlib) —
Security's Stage 2 §2.3 "always use absolute paths for hook-internal
external-binary calls" is satisfied by construction: there is no external
binary to bare-name-resolve via $PATH in the first place.

Both check paths (Write/Edit's typed `file_path`, Bash's string matching)
are explicitly, honestly disclosed as bypassable by a deliberately
adversarial agent — base64/heredoc indirection, glob/string-concatenation
evasion of the substring list, a symlink plus an unrelated-looking Bash
command (§2.2/§2.3 of the architecture document). This hook raises the
bar for realistic, non-adversarial scope creep; it is not a sandbox, and
does not claim to be one.
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

# ops/control-center/hooks/developer_pretooluse.py -> repo root is four
# parents up (hooks -> control-center -> ops -> repo root).
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------
# §2.2: the denylist, concretely — every pattern named, nothing left as
# "a denylist" in the abstract.
# ---------------------------------------------------------------------

# Write/Edit (tool_input.file_path) — structured, .resolve()-based, the
# PRIMARY defense (Security's Stage 2 §2.2 finding: Bash-string matching
# is structurally weaker than typed-field matching).
_PROTECTED_FILES = (
    REPO_ROOT / "ops" / "control-center" / ".founder_credential.json",  # the credential file
    REPO_ROOT / "ops" / "db" / "operations.sqlite3",                    # Security's S2
    REPO_ROOT / ".claude" / "agents" / "developer.md",                  # this hook's own defining
                                                                          # file (Red Team's S8)
    REPO_ROOT / "ops" / "control-center" / "hooks" / "developer_pretooluse.py",  # this hook's own
                                                                          # script (Red Team's S8)
    REPO_ROOT / ".claude" / "settings.json",       # pre-emptive — doesn't exist today
    REPO_ROOT / ".claude" / "settings.local.json",  # pre-emptive — doesn't exist today
)
# Resolved once at import time — cheap, and every one of these paths is
# fixed/hardcoded (never derived from untrusted input), so there is no
# TOCTOU concern in resolving them once up front rather than per call.
_PROTECTED_FILES_RESOLVED = tuple(p.resolve() for p in _PROTECTED_FILES)
_REPO_ROOT_RESOLVED = REPO_ROOT.resolve()

# Bash (tool_input.command) — string/substring matching, explicitly
# disclosed as a coarser backstop, not the primary defense (§2.2).
# Correction (Security's TASK-017 milestone review §1.2, "one cheap
# denylist addition"): the four self-protection paths below are in THIS
# plain substring list, not only in the narrower, command-anchored check
# further down — closes the "route the edit through a command name
# outside the six-command anchor list" bypass (e.g. a plain `python3 -c
# "open(p).read()"` call), at the cost of four more string literals, no
# scope expansion. Still bypassable by base64/heredoc/glob/concatenation
# indirection — disclosed, not claimed closed (§2.3).
#
# TASK-023 (§5 point 3): "ptrace" alone stays a plain substring (it's a
# syscall/API name, not a standalone shell token an ordinary command line
# would ever contain as a whole word next to legitimate text — e.g.
# "ptrace(2)" in a comment string would still deny, which is fine/coarse
# by design). " gdb"/" strace" (WITH a leading space) were dropped from
# this list — see _BASH_DENYLISTED_TOKENS and _check_bash() below for why
# and what replaced them.
_BASH_SUBSTRINGS = (
    "founder_credential",
    "operations.sqlite3",
    "import sqlite3",
    "sqlite3.connect",
    "ptrace",
    "sudo ",
    ".claude/agents/developer.md",
    "developer_pretooluse.py",
    ".claude/settings.json",
    ".claude/settings.local.json",
)

# TASK-023 (§5 point 3, "the leading-space " gdb"/" strace" substring
# bug"): the ORIGINAL check above used " gdb" and " strace" (a literal
# leading space) as plain substrings. That has two real, live bugs, not
# hypothetical ones: (1) it misses gdb/strace as the very FIRST token on
# the command line ("gdb -p 1234" has no leading space before "gdb" — the
# substring never matches), and (2) it CAN false-positive on an unrelated
# word that merely contains " gdb"/" strace" as a substring inside a
# longer token (e.g. a path or flag containing "outgdbstuff"). Token-based
# matching — checking whole, shlex-split tokens for exact membership —
# fixes both: it catches "gdb ..." as the first token, and it does not
# fire on a longer token that merely contains the substring. Still the
# same disclosed, non-adversarial-only backstop as every other Bash check
# here (a quoted/escaped/glob-expanded "gdb" can still evade a token
# check, same as it could evade the old substring check) — this closes a
# concrete correctness bug in the existing mechanism, not a claim of new
# completeness.
_BASH_DENYLISTED_TOKENS = ("gdb", "strace")

# TASK-023 (§5 point 3, "the shlex.split() hang-to-fail-open bug"):
# shlex.split() has real, documented quadratic-time behavior on certain
# adversarial inputs (long runs of unbalanced quote/escape characters) —
# a large-enough crafted `command` string can make the call itself run
# long enough to look "hung," and this hook's own fail-closed contract
# (§2.2a) means an in-flight call that never returns is not "denied," it
# is a tool call the harness is left waiting on indefinitely. Enforced as
# a plain length check on `command` BEFORE shlex.split() is ever called —
# a real, non-adversarial Bash command from Developer's own legitimate
# workflow is never anywhere close to this size; a command this large is
# itself denial-worthy regardless of content.
_MAX_BASH_COMMAND_CHARS = 50_000

# The narrower, token-anchored check, retained ALONGSIDE the substring
# list above (§2.2) because it also catches variable/glob-expanded forms
# a plain substring match on the literal path would miss (e.g. `sed -i
# ".claude/agents/"*".md"`) — best-effort, not a claim of completeness.
_BASH_ANCHOR_TOKENS = ("cat", "sed", "cp", "mv", "rm", ">", ">>")
_BASH_ANCHORED_PATHS = (
    ".claude/agents/developer.md",
    "ops/control-center/hooks/developer_pretooluse.py",
    ".claude/settings.json",
    ".claude/settings.local.json",
)


class HookInputError(Exception):
    """Raised by _parse_payload() when stdin isn't a JSON object — caught
    by main()'s own outer `except BaseException`, same as every other
    decision-computation failure. Not a BaseException subclass itself: it
    only needs to propagate up to main()'s single guarded `try`, which
    already catches BaseException (a superset of Exception)."""


def _parse_payload(raw_stdin: str) -> dict:
    try:
        payload = json.loads(raw_stdin)
    except (ValueError, TypeError) as exc:
        raise HookInputError(f"payload JSON parse failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise HookInputError(f"payload was not a JSON object (got {type(payload).__name__})")
    return payload


def _check_write_edit(tool_input: dict) -> tuple[str, str] | None:
    """Returns (decision, matched_rule) if this is a Write/Edit-shaped
    payload this hook denies; None if `tool_input` has no `file_path` key
    at all (not a Write/Edit call — the caller falls through to the Bash
    check), or does but nothing matched (allow, though the caller may
    still deny for other reasons). Every ordinary malformed-input failure
    mode here (a non-string file_path, a path .resolve() can't handle) is
    itself a DENY, per §2.2a — never left to raise past this function."""
    if "file_path" not in tool_input:
        return None
    raw_path = tool_input["file_path"]
    if not isinstance(raw_path, str):
        return ("deny", f"file_path was not a string (got {type(raw_path).__name__})")
    try:
        path = Path(raw_path).resolve()
    except (TypeError, OSError, RuntimeError, ValueError) as exc:
        return ("deny", f"file_path resolve failed: {exc}")

    for protected in _PROTECTED_FILES_RESOLVED:
        if path == protected or protected in path.parents:
            return ("deny", f"protected path: {protected}")
    try:
        path.relative_to(_REPO_ROOT_RESOLVED)
    except ValueError:
        return ("deny", f"path outside repo root: {path}")
    return None


def _check_bash(tool_input: dict) -> tuple[str, str] | None:
    """Returns (decision, matched_rule) if this is a Bash-shaped payload
    this hook denies; None if `tool_input` has no `command` key at all, or
    does but nothing matched (allow, subject to the caller's own final
    fallback)."""
    if "command" not in tool_input:
        return None
    command = tool_input["command"]
    if not isinstance(command, str):
        return ("deny", f"command was not a string (got {type(command).__name__})")

    # TASK-023 (§5 point 3): the length ceiling MUST be checked before
    # ANY parsing of `command` — including the plain substring loop below,
    # which is linear and not itself the quadratic-blowup risk, but
    # ordering the ceiling first, unconditionally, means this stays true
    # even if a future edit adds a more expensive check above shlex.split().
    if len(command) > _MAX_BASH_COMMAND_CHARS:
        return ("deny", f"command exceeds the {_MAX_BASH_COMMAND_CHARS}-character ceiling "
                         f"({len(command)} chars) — denied before parsing, not evaluated further")

    for pattern in _BASH_SUBSTRINGS:
        if pattern in command:
            return ("deny", f"bash substring match: {pattern!r}")

    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        # §2.2a: an ordinary, non-adversarial quoting mistake
        # (shlex.split() raising ValueError on unbalanced quotes) MUST
        # deny, never silently "no pattern matched, allow" — this is the
        # exact fail-open trap Red Team's original finding named.
        return ("deny", f"shlex parse failed: {exc}")

    # TASK-023 (§5 point 3): token-based, not substring-based — see
    # _BASH_DENYLISTED_TOKENS' own comment above for why. Checked against
    # the WHOLE token (exact match) and, separately, against just the
    # token's final path component (os.path.basename-equivalent) so an
    # invocation via an absolute/relative path (e.g. "/usr/bin/gdb -p 1")
    # is still caught, not only a bare "gdb".
    for tok in tokens:
        base = tok.rsplit("/", 1)[-1]
        if tok in _BASH_DENYLISTED_TOKENS or base in _BASH_DENYLISTED_TOKENS:
            return ("deny", f"bash token match: {tok!r}")

    anchor_present = any(tok in _BASH_ANCHOR_TOKENS for tok in tokens)
    if anchor_present:
        for protected_path in _BASH_ANCHORED_PATHS:
            for tok in tokens:
                if protected_path in tok:
                    return ("deny", f"bash token-anchored match: {protected_path!r}")
    return None


def _evaluate(payload: dict) -> tuple[str, str]:
    """Returns (decision, matched_rule). Corrected per Red Team's
    TASK-017 milestone review §7.5, point 2: Write/Edit and Bash are
    checked independently, keyed on which field is actually PRESENT in
    tool_input — NOT sequentially-and-unconditionally on file_path first.
    An unconditional `tool_input["file_path"]` access would KeyError (and,
    per this hook's own fail-closed contract, DENY) every single Bash
    call before ever reaching the Bash-specific checks, for the wrong
    reason — the same defect CLASS (an unconditional check placed where a
    conditional one belongs) that produced this document's earlier
    REJECTs, in a new spot. An unrecognized tool_input shape (neither key
    present) also denies — fail-closed, never "no pattern matched,
    allow" for a shape this hook doesn't recognize."""
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return ("deny", f"tool_input was not an object (got {type(tool_input).__name__})")

    write_edit_result = _check_write_edit(tool_input)
    if write_edit_result is not None:
        return write_edit_result

    bash_result = _check_bash(tool_input)
    if bash_result is not None:
        return bash_result

    if "file_path" not in tool_input and "command" not in tool_input:
        return ("deny", "tool_input had neither file_path nor command — unrecognized shape")

    return ("allow", "no denylist rule matched")


def _emit_decision(decision: str, matched_rule: str | None) -> None:
    """stdout: ONLY this JSON object — the more robust primary signal
    (checked and honored before exit-code branches are even reached).
    Flushed explicitly so a SUBSEQUENT best-effort step (_log_denial, on
    the success path — see main()) failing does not risk the harness
    never having seen this decision at all; CPython's own interpreter
    shutdown also flushes stdout on an uncaught exception, but this
    flush makes it a structural guarantee here, not an unstated
    buffering/shutdown-order assumption (Red Team's TASK-017 milestone
    review §7.5, point 1)."""
    reason = matched_rule if matched_rule else "denied"
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }))
    sys.stdout.flush()


def _log(role: str, tool_name: str, matched_rule: str, tool_input_summary: str,
          session_id: str | None, transcript_path: str | None) -> None:
    """Best-effort only — must never raise past this function. Every
    caller relies on that: the success path's own deny-logging (§7.5,
    point 1 — safe because _emit_decision() above already flushed, and
    this function's own internal guard means a write-lock/IO failure
    here can't crash the process after that point) and the exception
    handler's fallback (already inside its own nested best-effort guard,
    §2.2a point 4). A LAZY import of opsdb (not a module-level one) so a
    broken/missing ops/db/opsdb.py cannot itself crash this hook before
    decision emission even has a chance to run."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "ops" / "db"))
        import opsdb  # noqa: E402 — deliberately lazy, see docstring above
        conn = opsdb.connect()
        try:
            opsdb.record_hook_denial(conn, role, tool_name, matched_rule, tool_input_summary,
                                      session_id=session_id, transcript_path=transcript_path)
        finally:
            conn.close()
    except BaseException:
        pass


def _log_denial(payload: dict, matched_rule: str) -> None:
    tool_name = payload.get("tool_name") if isinstance(payload, dict) else None
    tool_input = payload.get("tool_input") if isinstance(payload, dict) else None
    summary = ""
    if isinstance(tool_input, dict):
        summary = str(tool_input.get("file_path") or tool_input.get("command") or tool_input)
    session_id = payload.get("session_id") if isinstance(payload, dict) else None
    transcript_path = payload.get("transcript_path") if isinstance(payload, dict) else None
    _log("developer", str(tool_name) if tool_name else "unknown", matched_rule, summary,
         session_id, transcript_path)


def _best_effort_log_internal_error(raw_stdin: str | None, exc: BaseException) -> None:
    _log("developer", "unknown", f"hook_internal_error: {type(exc).__name__}: {exc}",
         (raw_stdin or "")[:2000], None, None)


def main() -> None:
    raw_stdin = None
    try:
        raw_stdin = sys.stdin.read()                # inside the try — nothing
                                                      # executes before this line
        payload = _parse_payload(raw_stdin)          # guarded individually, above
        decision, matched_rule = _evaluate(payload)  # runs all of §2.2's checks
        # The guarded region ends HERE. Do NOT put the success-path
        # sys.exit()/_emit_decision/_log_denial inside this try — see the
        # module docstring and the comment below the `except`.
    except BaseException as exc:
        # BaseException, not Exception: a stray sys.exit() anywhere in
        # _evaluate() (present or future) raises SystemExit, which a
        # narrower `except Exception:` would NOT catch — silently
        # reproducing the exact fail-open bug this structure exists to
        # close.
        try:
            _emit_decision("deny", "hook_internal_error")   # stdout: ONLY this JSON
            _best_effort_log_internal_error(raw_stdin, exc)  # must not itself raise
        except BaseException:
            # The except handler's own calls aren't guaranteed not to
            # raise either. If emitting the JSON or logging itself fails,
            # fall back to the simplest possible hardcoded deny — no
            # further logic that could fail.
            sys.stdout.write(
                '{"hookSpecificOutput": {"hookEventName": "PreToolUse", '
                '"permissionDecision": "deny", '
                '"permissionDecisionReason": "hook_internal_error"}}'
            )
        sys.exit(2)
        return  # unreachable — sys.exit() above already raised SystemExit

    # Success path — reached only once decision computation above
    # returned normally, i.e. nothing raised. Deliberately OUTSIDE the
    # try/except: this sys.exit() also raises SystemExit and must never
    # be caught by our own handler.
    _emit_decision(decision, matched_rule)
    if decision == "deny":
        _log_denial(payload, matched_rule)            # best-effort; must not raise past _log()
    sys.exit(0 if decision == "allow" else 2)          # exit code as a redundant
                                                        # second signal, never the
                                                        # only one


if __name__ == "__main__":
    main()
