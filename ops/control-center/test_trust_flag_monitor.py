#!/usr/bin/env python3
"""ops/control-center/test_trust_flag_monitor.py — TASK-023 regression
check for trust_flag_monitor.py.

No OS dependency — writes a throwaway JSON file to a temp path and points
check_trust_flag() at it directly; never touches the real
$CLAUDE_CONFIG_DIR/.claude.json.

Usage: python3 ops/control-center/test_trust_flag_monitor.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_flag_monitor as tfm  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


def _write_config(tmpdir: Path, projects: dict) -> Path:
    path = tmpdir / ".claude.json"
    path.write_text(json.dumps({"projects": projects}))
    return path


def main() -> int:
    tmpdir = Path(tempfile.mkdtemp(prefix="trust-flag-monitor-test-"))
    repo_root = tmpdir / "repo"
    repo_root.mkdir()
    repo_key = str(repo_root.resolve())

    # ---- trusted=True case ----
    cfg = _write_config(tmpdir, {repo_key: {"hasTrustDialogAccepted": True}})
    result = tfm.check_trust_flag(cfg, repo_root)
    check("hasTrustDialogAccepted=true -> trusted=True", result["trusted"] is True, str(result))

    # ---- trusted=False case (explicit false) ----
    cfg = _write_config(tmpdir, {repo_key: {"hasTrustDialogAccepted": False}})
    result = tfm.check_trust_flag(cfg, repo_root)
    check("hasTrustDialogAccepted=false -> trusted=False", result["trusted"] is False, str(result))

    # ---- missing project entry entirely ----
    cfg = _write_config(tmpdir, {"/some/other/repo": {"hasTrustDialogAccepted": True}})
    result = tfm.check_trust_flag(cfg, repo_root)
    check("no projects[repo_key] entry at all -> trusted=False (safe default)",
          result["trusted"] is False, str(result))

    # ---- missing config file entirely ----
    missing_cfg = tmpdir / "does-not-exist.json"
    result = tfm.check_trust_flag(missing_cfg, repo_root)
    check("config file does not exist -> trusted=False, no exception", result["trusted"] is False, str(result))

    # ---- malformed JSON ----
    malformed = tmpdir / "malformed.json"
    malformed.write_text("{not valid json")
    result = tfm.check_trust_flag(malformed, repo_root)
    check("malformed JSON -> trusted=False, no exception", result["trusted"] is False, str(result))

    # ---- hasTrustDialogAccepted key entirely absent from the project entry ----
    cfg = _write_config(tmpdir, {repo_key: {}})
    result = tfm.check_trust_flag(cfg, repo_root)
    check("project entry present but key absent -> trusted=False", result["trusted"] is False, str(result))

    # ---- main()'s exit code mirrors trusted/not-trusted, --no-log avoids any DB dependency ----
    import argparse
    import io
    import contextlib

    cfg = _write_config(tmpdir, {repo_key: {"hasTrustDialogAccepted": True}})
    sys.argv = ["trust_flag_monitor.py", "--repo-root", str(repo_root), "--quiet"]
    # main() reads CLAUDE_CONFIG_DIR-derived path internally; patch via
    # monkeypatch of _config_path for this in-process check.
    original_config_path = tfm._config_path
    tfm._config_path = lambda: cfg
    try:
        exit_code = tfm.main()
        check("main() exit code is 0 when trusted", exit_code == 0, str(exit_code))

        cfg2 = _write_config(tmpdir, {repo_key: {"hasTrustDialogAccepted": False}})
        tfm._config_path = lambda: cfg2
        sys.argv = ["trust_flag_monitor.py", "--repo-root", str(repo_root), "--quiet", "--no-log"]
        exit_code = tfm.main()
        check("main() exit code is 1 when not trusted", exit_code == 1, str(exit_code))
    finally:
        tfm._config_path = original_config_path

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
