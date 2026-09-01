#!/usr/bin/env python3
"""ops/control-center/trust_flag_monitor.py — TASK-023, folded in per §5
point 4 of ops/reviews/cto-task023-architecture.md.

TASK-017's original self-checking trust-flag monitor was scoped to detect
silent reversion of Claude Code's own workspace-trust flag
(`projects["<repo-path>"].hasTrustDialogAccepted` in
`$CLAUDE_CONFIG_DIR/.claude.json`, or `~/.claude.json` if that env var is
unset — see `ops/reviews/cto-risk3-hook-invocation-investigation.md` §1)
for Developer specifically. This architecture's own §5 point 4 found that
purpose substantially moot for Developer once the sandbox structurally
prevents Developer's process from ever reaching that file (§4.4: it is
not bind-mounted into the sandbox at all) — but explicitly NOT moot for
`qa`/`cto`/`devops`, which remain on native, in-process, trust-flag-
dependent invocation and, in principle, still share the one global
`~/.claude.json` the Founder's own interactive session uses. This module
is that generalized, smaller-scoped monitor.

WHAT THIS DOES NOT DO: it does not fix a reverted trust flag, does not
write to `.claude.json` at all, and takes no corrective action. Per the
hook-invocation investigation's own finding (§2), setting
`hasTrustDialogAccepted: true` non-interactively is itself a real,
disclosed, security-relevant action (it is literally accepting a trust
prompt on the Founder's behalf) — this module's whole job is honest
detection and a visible alert, nothing more, so that decision stays a
deliberate one made elsewhere (deployment step / a human), not a silent
side effect of a monitor.

Usage:
    python3 ops/control-center/trust_flag_monitor.py [--repo-root PATH] [--quiet]

Exit code 0 if trust is confirmed accepted for the given repo path; exit
code 1 if it is not (missing config file, missing project entry, or the
flag is present but false) — so a scheduler (cron, a SessionStart hook,
CI) can treat non-zero as "needs a human's attention" without parsing
output. Always prints a one-line status to stdout; on a non-trusted
result, ALSO best-effort logs an activity-log entry via opsdb.py
(attributed to "devops", the role that owns this project's own deployment/
config-drift monitoring — see ops/control-center/README conventions) so
the alert has a durable, queryable trail, not only a terminal line a human
might not be watching. Logging failure (opsdb unavailable, no live task
to attach to, etc.) never changes this script's own exit code — the
trust-state finding itself is what matters, not whether the log write
succeeded.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# The three roles this monitor's scope was narrowed to, per §5 point 4 —
# named here for documentation/log-message purposes only; the underlying
# trust flag is keyed by absolute repo PATH, not by role, so there is only
# ever one check to make per repo, regardless of how many of these three
# roles are in play.
DEPENDENT_ROLES = ("qa", "cto", "devops")


def _config_path() -> Path:
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir) / ".claude.json"
    return Path.home() / ".claude.json"


def check_trust_flag(config_path: Path, repo_root: Path) -> dict:
    """Returns a dict describing the current trust state for repo_root,
    read from config_path. Never raises — a missing/malformed config file
    or a missing project entry is reported as trusted=False (the safe,
    "needs attention" default), not as an exception a caller has to
    separately guard against."""
    repo_key = str(repo_root.resolve())
    result = {
        "config_path": str(config_path),
        "repo_root": repo_key,
        "trusted": False,
        "detail": None,
    }
    if not config_path.exists():
        result["detail"] = f"config file does not exist: {config_path}"
        return result
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        result["detail"] = f"config file could not be read/parsed: {exc}"
        return result
    projects = data.get("projects")
    if not isinstance(projects, dict) or repo_key not in projects:
        result["detail"] = f"no projects[{repo_key!r}] entry in {config_path}"
        return result
    entry = projects[repo_key]
    trusted = bool(isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True)
    result["trusted"] = trusted
    result["detail"] = "hasTrustDialogAccepted is true" if trusted else "hasTrustDialogAccepted is false or absent"
    return result


def _best_effort_log_alert(result: dict) -> None:
    """Logs a non-trusted finding via opsdb.py's activity-log — best
    effort only, must never raise past this function or change the
    caller's exit code (same defensive discipline
    developer_pretooluse.py's own _log() already establishes for hook
    denials — this monitor is not itself security-enforcing, so a logging
    failure here is even less consequential, but the same "never let
    logging break the primary signal" rule still applies)."""
    try:
        sys.path.insert(0, str(REPO_ROOT / "ops" / "db"))
        import opsdb  # noqa: E402 — deliberately lazy, see docstring
        conn = opsdb.connect()
        try:
            opsdb.record_activity(
                conn, "devops", None,
                summary="trust_flag_monitor: shared workspace-trust flag is NOT accepted",
                detail=(f"{result['detail']} (config_path={result['config_path']}, "
                        f"repo_root={result['repo_root']}) — affects native, in-process "
                        f"invocation for: {', '.join(DEPENDENT_ROLES)}. PreToolUse hooks "
                        "silently do not fire for these roles until this is corrected — see "
                        "ops/reviews/cto-risk3-hook-invocation-investigation.md."),
            )
        finally:
            conn.close()
    except Exception:
        # Best-effort logging only — narrowed from BaseException (Code
        # Review non-blocking item): swallowing KeyboardInterrupt/SystemExit
        # here would mask a deliberate interrupt/exit; Exception is the right
        # breadth for "an opsdb/IO failure must never change our exit code".
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT,
                         help="repo path to check trust for (default: this repo)")
    parser.add_argument("--quiet", action="store_true", help="suppress the stdout status line")
    parser.add_argument("--no-log", action="store_true",
                         help="skip the best-effort activity-log write on a non-trusted finding "
                              "(useful for ad hoc/manual runs against a scratch OPSDB_PATH)")
    args = parser.parse_args()

    result = check_trust_flag(_config_path(), args.repo_root)

    if not args.quiet:
        status = "TRUSTED" if result["trusted"] else "NOT TRUSTED"
        print(f"trust_flag_monitor: {status} — {result['detail']} "
              f"(dependent roles: {', '.join(DEPENDENT_ROLES)})")

    if not result["trusted"]:
        if not args.no_log:
            _best_effort_log_alert(result)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
