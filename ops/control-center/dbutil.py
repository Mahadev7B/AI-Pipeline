"""ops/control-center/dbutil.py — shared read-only DB access for every
Control Center generator script. One copy of the OPSDB_PATH resolution,
the URI percent-encoding fix, and the mode=ro connection — not six.

See ops/db/README.md for the OPSDB_PATH testing convention this all
respects, and ops/reviews/cto-phase2-architecture.md for why every
Control Center connection is opened read-only.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

_DB_DIR = Path(__file__).resolve().parent.parent / "db"
_CC_DIR = Path(__file__).resolve().parent

_using_scratch_db = bool(os.environ.get("OPSDB_PATH"))
DB_PATH = Path(os.environ["OPSDB_PATH"]) if _using_scratch_db else _DB_DIR / "operations.sqlite3"


def out_path(default_name: str, env_var: str) -> Path:
    """Resolve where a generator should write its output — real path in
    ops/control-center/ by default, or a scratch-DB sibling when testing
    (see ops/db/README.md — never overwrite the real Control Center pages
    while testing against a scratch database)."""
    if os.environ.get(env_var):
        return Path(os.environ[env_var])
    if _using_scratch_db:
        return DB_PATH.with_name(DB_PATH.stem + "." + default_name)
    return _CC_DIR / default_name


def connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise SystemExit(f"error: {DB_PATH} does not exist — run `opsdb.py init` first")
    # mode=ro: every Control Center generator is read-only, verified in
    # Milestone 1 by an actual write-refusal test, not just asserted.
    # The path MUST be percent-encoded — an unescaped '#' or '?' is a URI
    # fragment/query separator, not a literal character (Milestone 1 Code
    # Review finding, confirmed with a real reproduction).
    conn = sqlite3.connect(f"file:{quote(str(DB_PATH))}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def write_output(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    path.chmod(0o600)  # same reasoning as operations.sqlite3 — this is the same class of internal data
