#!/usr/bin/env python3
"""ops/control-center/founder_auth.py — Phase 2, Milestone 2B4 (TASK-013).

Credential storage and verification for Founder identity checks used by
`server.py`'s `/login` / `/api/login` routes, plus the two CLI subcommands
a Founder runs directly from their own terminal to create or rotate their
passphrase. Full design: `ops/reviews/cto-milestone2b4-architecture.md`
(sections 2, 3, 13), independently reviewed in
`ops/reviews/security-milestone2b4-threat-model.md` and
`ops/reviews/red-team-milestone2b4-architecture.md`.

No HTTP/session logic lives here — that's `server.py`, next to
`SESSION_TOKEN` (same separation as `agent_runtime.py` vs. `server.py`
for model-invocation mechanics vs. HTTP dispatch). This module owns only:
  - the credential file's JSON format and where it lives
  - deriving/verifying a passphrase against it (hashlib.scrypt, stdlib
    only — no third-party KDF library)
  - the `setup`/`change` CLI subcommands a Founder runs by hand

WHAT THIS PROVES AND DOES NOT PROVE — same disclosure discipline as every
other milestone in this codebase (see `server.py`'s module docstring and
`ops/SECURITY.md`): a correct passphrase proves the caller knows a secret
only the Founder was ever told. It does NOT create an OS-level privilege
boundary. Any process running as the same OS user as the Founder (e.g. an
agent invoked with Bash tool access, per the still-open `risks.id=3`) can
already read this credential file directly, or run `change`/`setup`
itself, or (per Security's independent finding) `PTRACE_ATTACH` to the
running `server.py` process and read session state out of memory without
ever touching this file. `setup`'s "refuse if a credential already
exists" check and `change`'s "must know the current passphrase" check are
both safety rails for the Founder's own workflow (catching an accidental
overwrite, or documenting an intentional rotation) — neither is a
security boundary against that same-OS-user attacker class. See §11 of
the architecture doc for the full trace.

Usage:
    python3 ops/control-center/founder_auth.py setup
    python3 ops/control-center/founder_auth.py change
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import secrets
import sys
import time
from pathlib import Path

CREDENTIAL_PATH = Path(__file__).resolve().parent / ".founder_credential.json"

# scrypt parameters — OWASP's current general-purpose recommendation, not
# the memory-constrained fallback (N=2**14). Measured ~0.98s/hash on a
# real machine; login happens rarely (once per session, not once per
# request), so the extra cost is a non-issue for UX and meaningfully
# raises the cost of offline brute force. See architecture doc §2.
SCRYPT_N = 2**17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
# hashlib.scrypt's default maxmem ceiling is 32 MiB; N=2**17, r=8 needs
# ~128 MiB (128 * N * r bytes) and raises ValueError without an explicit,
# larger maxmem. Verified directly (Red Team's Milestone 2B4 review).
SCRYPT_MAXMEM = 132 * 1024 * 1024

SALT_BYTES = 16
MIN_PASSPHRASE_LENGTH = 16  # bumped from 12 -> 16 per architecture doc §13 (cheap defense-in-depth)

CREDENTIAL_VERSION = 1


class CredentialError(Exception):
    """Raised for any problem loading/parsing the credential file —
    caught by server.py and treated identically to 'no credential file
    exists yet' (503, setup required). Deliberately not raised for 'file
    doesn't exist' itself — callers check that with Path.exists() first,
    per the architecture doc's fail-closed design (§3)."""


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def derive_hash(passphrase: str, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P,
                 dklen: int = SCRYPT_DKLEN) -> bytes:
    """hashlib.scrypt over the passphrase's UTF-8 bytes. Never raises on
    an empty passphrase (scrypt accepts a zero-length password) — verified
    directly, see the test suite; an empty passphrase simply derives *a*
    hash that (almost certainly) won't match the stored one, failing
    verification cleanly rather than crashing. maxmem must be passed
    explicitly at these parameters or hashlib.scrypt raises ValueError."""
    return hashlib_scrypt(passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=SCRYPT_MAXMEM)


def hashlib_scrypt(password: bytes, *, salt: bytes, n: int, r: int, p: int, dklen: int, maxmem: int) -> bytes:
    """Thin wrapper so the rest of this module (and tests) can patch/mock
    a single call site if ever needed; also keeps the maxmem requirement
    (architecture doc §2) in exactly one place."""
    return hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, dklen=dklen, maxmem=maxmem)


def credential_exists(path: Path = CREDENTIAL_PATH) -> bool:
    return path.exists()


def load_credential(path: Path = CREDENTIAL_PATH) -> dict:
    """Read and parse the credential file. Raises CredentialError on ANY
    problem — missing file, unreadable, malformed/partial JSON (e.g. a
    concurrent read landing mid-write during 'setup' or 'change'),
    missing/wrong-typed fields. Callers (server.py) must treat
    CredentialError exactly like 'setup required' (503) — Red Team's
    Milestone 2B4 review, non-blocking note: a malformed/partial file
    must never surface as an unhandled 500."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise CredentialError(f"could not read/parse credential file: {type(exc).__name__}: {exc}") from exc

    try:
        if not isinstance(data, dict):
            raise CredentialError("credential file does not contain a JSON object")
        if data.get("kdf") != "scrypt":
            raise CredentialError("credential file has an unrecognized kdf")
        for key in ("n", "r", "p", "dklen"):
            if not isinstance(data.get(key), int):
                raise CredentialError(f"credential file missing/invalid integer field '{key}'")
        salt = _unb64(data["salt"])
        stored_hash = _unb64(data["hash"])
    except CredentialError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise CredentialError(f"credential file is malformed: {type(exc).__name__}: {exc}") from exc

    return {
        "version": data.get("version"),
        "n": data["n"], "r": data["r"], "p": data["p"], "dklen": data["dklen"],
        "salt": salt, "hash": stored_hash,
        "created_at": data.get("created_at"),
    }


def verify_passphrase(passphrase: str, path: Path = CREDENTIAL_PATH) -> bool:
    """True iff `passphrase` matches the stored credential. Raises
    CredentialError if the credential file is missing/malformed — callers
    that already confirmed credential_exists() should still be prepared
    to catch this (a narrow TOCTOU window between the exists() check and
    this read is possible — Red Team's Milestone 2B4 review). Constant-
    time comparison of the DERIVED hash bytes, never the raw passphrase
    (architecture doc §2)."""
    cred = load_credential(path)
    candidate = derive_hash(passphrase, cred["salt"], n=cred["n"], r=cred["r"], p=cred["p"], dklen=cred["dklen"])
    return secrets.compare_digest(candidate, cred["hash"])


def _write_credential_atomic_new(passphrase: str, path: Path = CREDENTIAL_PATH) -> None:
    """`setup`: create the file fresh. os.open with O_EXCL|O_CREAT means
    the file is created AT mode 0600, atomically — no TOCTOU window where
    it briefly exists at a wider mode (architecture doc §3), and O_EXCL
    makes the open itself fail if the file already exists (a second guard
    beneath the caller's own already-exists check)."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = derive_hash(passphrase, salt)
    payload = _credential_json(salt, digest)

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
    except BaseException:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _write_credential_atomic_replace(passphrase: str, path: Path = CREDENTIAL_PATH) -> None:
    """`change`: write to a sibling temp file (same restrictive
    O_EXCL|0600 creation, same dot-prefixed `.founder_credential` stem so
    it falls under the .gitignore glob — architecture doc §13, not
    previously specified), then os.replace() — a single atomic POSIX
    rename, so there is no observable intermediate state (never a moment
    the file is deleted-but-not-replaced, never a moment it's readable at
    a wider mode)."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = derive_hash(passphrase, salt)
    payload = _credential_json(salt, digest)

    tmp_path = path.with_name(path.name + f".tmp-{os.getpid()}-{secrets.token_hex(4)}")
    fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _credential_json(salt: bytes, digest: bytes) -> str:
    payload = {
        "version": CREDENTIAL_VERSION,
        "kdf": "scrypt",
        "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P, "dklen": SCRYPT_DKLEN,
        "salt": _b64(salt),
        "hash": _b64(digest),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    return json.dumps(payload, indent=2) + "\n"


def _prompt_new_passphrase() -> str:
    while True:
        p1 = getpass.getpass("New Founder passphrase (min "
                              f"{MIN_PASSPHRASE_LENGTH} characters): ")
        if len(p1) < MIN_PASSPHRASE_LENGTH:
            print(f"Too short — must be at least {MIN_PASSPHRASE_LENGTH} characters. Try again.", file=sys.stderr)
            continue
        p2 = getpass.getpass("Confirm passphrase: ")
        if p1 != p2:
            print("Passphrases did not match. Try again.", file=sys.stderr)
            continue
        return p1


def cmd_setup(args: argparse.Namespace) -> int:
    path = CREDENTIAL_PATH
    if path.exists():
        print(f"A credential file already exists at {path}.", file=sys.stderr)
        print("Use `python3 ops/control-center/founder_auth.py change` to rotate it instead.", file=sys.stderr)
        return 1

    print("Setting up the Founder passphrase for the first time.")
    passphrase = _prompt_new_passphrase()
    try:
        _write_credential_atomic_new(passphrase, path)
    except FileExistsError:
        # O_EXCL lost a narrow race against something else creating the
        # file between our own exists() check above and the open() call —
        # a second, smaller-window guard against the same race (architecture
        # doc §3). Treat identically to the check above.
        print(f"A credential file already exists at {path} (created concurrently).", file=sys.stderr)
        print("Use `change` instead.", file=sys.stderr)
        return 1
    print(f"Founder credential created at {path}.")
    return 0


def cmd_change(args: argparse.Namespace) -> int:
    path = CREDENTIAL_PATH
    if not path.exists():
        print(f"No credential file exists at {path} yet.", file=sys.stderr)
        print("Use `python3 ops/control-center/founder_auth.py setup` instead.", file=sys.stderr)
        return 1

    current = getpass.getpass("Current Founder passphrase: ")
    try:
        ok = verify_passphrase(current, path)
    except CredentialError as exc:
        print(f"Could not read the existing credential file: {exc}", file=sys.stderr)
        return 1
    if not ok:
        print("Incorrect current passphrase. Nothing was changed.", file=sys.stderr)
        return 1

    print("Current passphrase verified.")
    new_passphrase = _prompt_new_passphrase()
    _write_credential_atomic_replace(new_passphrase, path)
    print(f"Founder credential updated at {path}.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    setup_p = sub.add_parser("setup", help="create the Founder credential file for the first time (refuses if one already exists)")
    setup_p.set_defaults(func=cmd_setup)

    change_p = sub.add_parser("change", help="rotate the Founder passphrase (requires knowing the current one)")
    change_p.set_defaults(func=cmd_change)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
