#!/usr/bin/env python3
"""ops/control-center/egress_proxy.py — TASK-023 (risks.id=3 durable
closure): the model-API egress carve-out (addendum 1, finding B3) AND the
host-side credential gateway (addendum 2, finding C2).

The host-side, allowlisting daemon that owns the ONE permitted egress path
out of the Developer sandbox. Read, in full, before touching this file:
`ops/reviews/cto-task023-architecture.md` (the B3 Addendum and the Second
addendum), `ops/reviews/red-team-task023-addendum-review.md` (the CONNECT
contract), and `ops/reviews/red-team-task023-addendum2-review.md` (the
BINDING GATEWAY CONTRACT restated verbatim below). Every clause here is a
security boundary, not a convenience.

WHY THIS EXISTS
---------------
The sandbox keeps `--unshare-all` (including `--unshare-net`): it has no
network interface, no route, no DNS, no reachable TCP destination. The
sandboxed `claude` CLI must nonetheless reach the model API to do any work
at all. The single exception is a Unix-domain socket bind-mounted into the
sandbox (`/run/ai-pipeline/egress.sock` by default) — Unix sockets
traverse the *filesystem* namespace, not the *network* namespace, so this
grants one named, auditable channel without granting any interface.

This daemon owns that socket and serves TWO modes on it:

  * GATEWAY mode (addendum 2, the live model path). The sandbox holds only
    the non-secret sentinel `ANTHROPIC_API_KEY=SANDBOX-PLACEHOLDER-NOT-A-
    CREDENTIAL` and an `ANTHROPIC_BASE_URL` pointing at the in-sandbox
    relay. This daemon TERMINATES the plain-HTTP request, replaces the
    sentinel with the real credential read from a `0600` trusted-account
    file that is NEVER bind-mounted, and re-originates over TLS to the
    destination named in its own trusted config — never one named by the
    request.
  * CONNECT mode (addendum 1, retained as LIVE, ACTIVELY-DENIED RESERVE).
    Red Team confirmed the real CLI still issues `CONNECT
    api.anthropic.com:443` and `CONNECT http-intake.logs.us5.datadoghq.com
    :443` (Datadog telemetry) on this same socket even in gateway mode.
    With the recommended empty `allow` list all of them are 403'd and the
    CLI works normally. Do NOT delete this path and do NOT add
    `api.anthropic.com:443` back to `allow` "for the CLI's benefit": a
    credentialed CONNECT would hand it a content-opaque tunnel the gateway
    cannot see.

RUNS AS: the broker's own trusted account (or a dedicated
`ai-pipeline-egress` system account) — NEVER as `ai-developer`, NEVER as
root. The allowlist config AND the credential file it reads are owned by
that trusted account, are NOT bind-mounted into the sandbox, and are
therefore unreadable and unwidenable by the sandboxed Developer even as
root inside its own user namespace. See
`ops/reviews/task023-os-provisioning-runbook.md`.

THE CONNECT-PARSE ROBUSTNESS CONTRACT (Red Team's addendum-1 non-blocking
item, `ops/reviews/red-team-task023-addendum-review.md`, implemented here
exactly — do NOT relax any clause):

  1. The allow decision is made against the proxy-parsed CONNECT
     request-line target `host:port` ONLY — never a client-supplied
     `Host:` header, which is ignored entirely.
  2. The allowlist is by *hostname*:port. A CONNECT whose target is an IP
     literal (IPv4 or IPv6, in any encoding) is rejected outright — so a
     raw IP that happens to equal the API's own resolved address is ALSO
     denied (the allowlist has no IP entries, and an IP-literal target is
     refused before any allowlist check).
  3. The hostname is resolved host-side (by `socket.create_connection`,
     inside this trusted process's own network namespace) — the sandbox
     has no resolver of its own and can never supply or influence the
     resolved address.
  4. Fail CLOSED on ANY parse ambiguity: a non-CONNECT method, a malformed
     request line, a missing/zero/out-of-range/non-decimal port, an
     IPv6/bracketed target, whitespace or trailing junk in the target,
     non-ASCII bytes, or a connection that closes before a full header
     block arrives — every one of these is a rejection, never a
     best-effort guess.
  5. A non-443 port on an allowlisted host is denied (the allowlist entry
     is an exact `host:port`; `api.anthropic.com:443` allowed does not
     allow `api.anthropic.com:22`).

THE BINDING GATEWAY CONTRACT (`ops/reviews/red-team-task023-addendum2-
review.md` §4, clauses C1–C10 plus the two "also required" items — these
are REQUIREMENTS of that review, not suggestions; Code Review/QA/Security
hold this file to them):

  C1. DESTINATION IS TRUSTED-SIDE ONLY. The upstream host/port comes
      *exclusively* from `gateway.upstream` in the trusted config file.
      The request line's authority (absolute-form URI) and the `Host:`
      header are NEVER consulted for destination selection, for TLS
      SNI/verification, or for anything else. Red Team built the naive
      variant and demonstrated it ships the real credential to an
      attacker-chosen host in ONE request from inside a real sandbox, in
      both the absolute-form and the `Host:`-header shape. This clause is
      the single most important line in this file: see
      `_normalise_request_target()`, which returns ONLY a path, and
      `_gateway_dial()`, whose only source of host/port is `cfg`.
  C2. BOTH REQUEST FORMS ARE ACCEPTED AND NORMALISED. The shipped
      `egress_relay.py` sets HTTP(S)_PROXY, so the real CLI emits
      absolute-form (`POST http://127.0.0.1:8889/v1/messages?beta=true`,
      `Host: 127.0.0.1:8889`); origin-form must also work. Both are
      rewritten to origin-form with this gateway's OWN `Host:` for the
      configured upstream. Anything else — unknown method, malformed
      request line, obs-fold continuation, absolute-form with a non-http
      scheme — is a fail-closed `400` and the connection is closed.
  C3. PER-REQUEST INJECTION, AND NEVER A TUNNEL. Every request on every
      connection is parsed and rewritten; the gateway never degrades into
      byte-pumping after request 1 (that is exactly the keep-alive leak
      CTO found by running it). Any client-supplied `x-api-key` /
      `Authorization` / `Proxy-Authorization` is REMOVED and REPLACED,
      never appended to.
  C4. RESPONSE FRAMING IS PART OF THE SECURITY PROPERTY. Real model
      traffic is `"stream": true` — SSE, chunked, no `Content-Length`,
      long-lived. Responses are streamed incrementally and chunked/EOF
      framing is tracked exactly, because getting request N's response
      boundary wrong is what lets request N+1 through unrewritten.
  C5. FRAMING AMBIGUITY FAILS CLOSED. `Content-Length` + `Transfer-
      Encoding` together, duplicate/conflicting `Content-Length`,
      non-decimal length, or any `Transfer-Encoding` on a REQUEST (which
      this gateway deliberately does not implement) → `400` + close,
      never "best effort". Bodies are STREAMED with a ceiling, never
      buffered whole, so the untrusted side cannot declare a huge
      `Content-Length` and OOM this trusted daemon.
  C6. NO CREDENTIAL CAN COME BACK. Redirects are never followed — a 3xx
      is relayed to the client verbatim and no request is ever re-issued
      with the injected header. No error/diagnostic response, header or
      body, contains the injected value or any part of it. There is no
      debug/echo/control verb on this socket.
  C7. NO CONNECTION SHARING ACROSS CLIENTS. One client connection gets
      its own upstream connection, created lazily and closed with it.
      Upstream connections are never pooled or reused across client
      connections or sessions, so two concurrent sandboxes can never
      reach each other's prompts or responses.
  C8. LOGGING: METADATA ONLY, EXPLICITLY. This daemon now sees every
      prompt and every response of the Founder's own work in plaintext.
      It MUST NEVER log request or response BODIES, never log the
      credential or the value of any `x-api-key`/`Authorization` header
      (not even truncated or hashed), and never write bodies to disk,
      journal or stderr. Permitted: timestamps, method, path, status,
      byte counts, session/connection ids, and the
      `sentinel_seen`/`swapped` booleans. Everything this file emits goes
      through `_log()`, which takes only scalar metadata fields.
  C9. THE EMPTY-ALLOWLIST GUARD IS RECONCILED, NOT DELETED. The
      fail-closed "refuse to start if I can forward nothing" guard is
      retained in spirit: `allow: []` is permitted ONLY together with a
      valid gateway config. Empty allowlist AND no gateway config = still
      refuse to start. A missing/unreadable/wrong-mode credential file =
      refuse to start; never start and forward un-credentialed or with
      the sentinel.
  C10. TLS VERIFICATION IS MANDATORY AND IS NEVER DISABLED. Hostname and
      chain are verified against a CA store this account can actually
      read; `check_hostname`/`CERT_REQUIRED` are asserted at load time,
      and there is deliberately no config key that can turn them off. If
      a deployment's proxy re-terminates TLS with a private CA, provision
      a readable copy and set `gateway.ca_file` — do NOT run this daemon
      as root and do NOT disable verification.
  SPEND (Red Team moved this from "named, not built" to REQUIRED). The
      CLI's own `--max-budget-usd` is enforced by the untrusted side and
      is worth nothing against this threat model. A hard, gateway-side
      per-session ceiling on request COUNT and cumulative request BYTES
      is enforced here, fail-closed with a `429` and a log line. The
      session key is the client's `SO_PEERCRED` (pid, /proc starttime,
      uid) — the in-sandbox relay process, one per live sandbox — so two
      concurrent sandboxes get independent budgets without adding a
      session token to this socket (which would be an architecture
      change, not Development's to make).
  PATH ALLOWLIST (Red Team, "also required"). The credential is attached
      only to an explicitly allowlisted request PATH. Otherwise the
      sandbox could use the operator's credential for anything that
      credential can do on the API host — Red Team's `POST /steal` went
      upstream credentialed against a naive build. A path outside the
      list is a visible `403` from this gateway, never a silent widening.

NOT STARTED as a side effect of import (`if __name__ == "__main__"` guard,
same convention as opsdb_broker.py). This module is fully unit-testable
over a temp-path Unix socket against a throwaway localhost destination —
see ops/db/test_egress_proxy.py — which is a legitimate test fixture, not
the persistent, dedicated-account daemon this task's Development pass must
not stand up.
"""
from __future__ import annotations

import ipaddress
import json
import os
import select
import socket
import ssl
import struct
import sys
import threading
import time
from pathlib import Path

DEFAULT_SOCKET_PATH = "/run/ai-pipeline/egress.sock"
DEFAULT_CONFIG_PATH = "/etc/ai-pipeline/egress-allowlist.json"

# The non-secret placeholder `launch_developer_sandboxed.sh` puts inside the
# sandbox as ANTHROPIC_API_KEY. It is NOT a credential and is safe in git;
# it exists so the gateway can log `sentinel_seen` and so a value found in a
# commit or a handoff row is self-evidently worthless (architecture doc,
# second addendum, QA charter item (j)). The gateway does NOT require the
# client to send it — the credential header is replaced unconditionally
# (C3) whatever the client sent.
SENTINEL_API_KEY = "SANDBOX-PLACEHOLDER-NOT-A-CREDENTIAL"

_RECV = 65_536
_MAX_HEADER_BYTES = 16_384       # generous ceiling on a request/response header block
_MAX_HEADER_LINES = 200          # ceiling on header count (C5: oversized headers fail closed)
_IO_TIMEOUT_S = 30.0             # per-socket idle timeout; a stalled tunnel/client costs one connection
# The gateway's own idle ceiling. A streamed SSE response can legitimately
# be quiet for a long time between events, and the CLI itself advertises
# `x-stainless-timeout: 600`, so the CONNECT path's 30s would cut real work
# off mid-answer.
_GATEWAY_IO_TIMEOUT_S = 600.0

# C2: the only request methods this gateway will forward. Observed from a
# real CLI session: `HEAD /api/hello` and `POST /v1/messages?beta=true`.
# GET is included because it is safe and idempotent; anything else is a
# fail-closed 400 rather than a silent widening.
_GATEWAY_METHODS = frozenset({"GET", "HEAD", "POST"})

# C3: never forwarded from the client. Credential headers are replaced (not
# appended to); hop-by-hop headers are this gateway's own to decide.
_STRIPPED_REQUEST_HEADERS = frozenset({
    "host", "x-api-key", "authorization", "proxy-authorization",
    "proxy-connection", "connection", "keep-alive", "te", "trailer",
    "transfer-encoding", "upgrade", "content-length", "expect",
})

# Which header forms may carry the credential. A Console API key goes out
# as `x-api-key`; a claude.ai OAuth token as `Authorization: Bearer <tok>`.
# Deployment configuration, not a code constant (architecture doc, second
# addendum) — but constrained to these two, fail-closed.
_ALLOWED_CREDENTIAL_HEADERS = frozenset({"x-api-key", "authorization"})


# --------------------------------------------------------------- logging --

def _log(event: str, **fields: object) -> None:
    """C8: the ONLY output path in this module. Takes an event name plus
    scalar METADATA fields — timestamps, method, path, status, byte counts,
    session/connection ids, booleans. Never a body, never a header value,
    never the credential.

    Enforced structurally, not by convention: every value is coerced with
    `repr()` on a scalar and any non-scalar is replaced with its type name,
    so a future caller cannot accidentally hand this function a body buffer
    or a header dict and have it printed. Callers must not pre-format
    content into `event` either — that is the one thing review must check
    when a new call site is added."""
    parts = [f"egress_proxy: {event}"]
    for key, value in fields.items():
        if isinstance(value, bool) or value is None:
            rendered = str(value)
        elif isinstance(value, (int, float)):
            rendered = str(value)
        elif isinstance(value, str):
            # Path/method/status strings only. Bounded so an over-long
            # attacker-chosen path cannot flood the journal, and sanitised
            # so it cannot inject newlines into the log stream.
            rendered = value[:200].replace("\r", "\\r").replace("\n", "\\n")
        else:
            rendered = f"<{type(value).__name__}>"
        parts.append(f"{key}={rendered}")
    sys.stderr.write(" ".join(parts) + "\n")
    sys.stderr.flush()


# --------------------------------------------------------------- parsing --

_ASCII_DIGITS = frozenset("0123456789")


def _split_host_port(target: str) -> tuple[str | None, int | None]:
    """Strict `host:port` split. Returns (host, port) only for an
    unambiguous single-colon `host:port` with a decimal in-range port and
    a non-empty host; returns (None, None) for ANYTHING else (fail closed):
    empty, whitespace-bearing, bracketed/IPv6, zero or more-than-one colon,
    non-decimal or out-of-range port. Deliberately conservative."""
    if not isinstance(target, str) or not target:
        return (None, None)
    if any(ch.isspace() for ch in target):
        return (None, None)
    if "[" in target or "]" in target:  # IPv6 bracket form — reject, fail closed
        return (None, None)
    if target.count(":") != 1:           # zero colons (no port) or IPv6/ambiguous
        return (None, None)
    host, _, port_str = target.partition(":")
    if not host:
        return (None, None)
    if not port_str or any(ch not in _ASCII_DIGITS for ch in port_str):
        return (None, None)
    port = int(port_str)
    if port < 1 or port > 65535:
        return (None, None)
    return (host, port)


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def parse_connect_target(raw: bytes) -> tuple[str, int] | None:
    """Parse the CONNECT request line out of the raw header bytes. Returns
    (host, port) for a well-formed CONNECT to a hostname:port target, or
    None on any ambiguity (clause 4 of the robustness contract). The
    decision is based ONLY on the request line — the header block that
    follows (including any `Host:` header) is never consulted."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if "\r\n" not in text:
        return None
    request_line = text.split("\r\n", 1)[0]
    parts = request_line.split(" ")
    if len(parts) != 3:
        return None
    method, target, version = parts
    if method != "CONNECT":
        return None
    if version not in ("HTTP/1.1", "HTTP/1.0"):
        return None
    host, port = _split_host_port(target)
    if host is None or port is None:
        return None
    return (host, port)


def peek_method(raw: bytes) -> str | None:
    """The request-line method of an already-read header block, or None if
    the request line is not even shaped like one. Used only to route a
    connection to the CONNECT path or the gateway path; both paths re-parse
    the block themselves and neither trusts this."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    if "\r\n" not in text:
        return None
    parts = text.split("\r\n", 1)[0].split(" ")
    if not parts or not parts[0]:
        return None
    return parts[0]


def _normalise_request_target(target: str) -> str | None:
    """**C1 — the single most important function in this file.**

    Takes the request-line target in EITHER form and returns ONLY an
    origin-form `path[?query]`. The authority of an absolute-form URI is
    parsed solely in order to be DISCARDED; it is never returned, and no
    caller can obtain it from here. That is the structural reason a
    `POST http://127.0.0.1:18912/steal` from inside the sandbox cannot
    steer the credential anywhere: the destination is not derivable from
    this function's return value at all.

    Returns None (fail closed, `400`) for: an empty target, a target with
    whitespace, a non-`http`/`https` scheme, an authority-only absolute URI
    with no path (normalised to `/`... see below), or anything that is not
    left starting with `/`.
    """
    if not target or any(ch.isspace() for ch in target):
        return None
    lowered = target.lower()
    for scheme in ("http://", "https://"):
        if lowered.startswith(scheme):
            rest = target[len(scheme):]
            slash = rest.find("/")
            if slash < 0:
                # `http://authority` with no path at all — the authority is
                # discarded exactly as in every other branch; the request
                # becomes a root request, which the path allowlist then
                # almost certainly denies.
                return "/"
            target = rest[slash:]
            break
    else:
        if "://" in target:
            return None  # some other scheme — fail closed, never guess
    if not target.startswith("/"):
        return None
    if "\x00" in target:
        return None
    return target


class RequestHead:
    """A parsed, validated client request head. `headers` preserves order
    and original casing for relaying; `path` is origin-form only (C1)."""

    __slots__ = ("method", "path", "version", "headers", "content_length", "sentinel_seen")

    def __init__(self, method: str, path: str, version: str,
                 headers: list[tuple[str, str]], content_length: int,
                 sentinel_seen: bool):
        self.method = method
        self.path = path
        self.version = version
        self.headers = headers
        self.content_length = content_length
        self.sentinel_seen = sentinel_seen


class RequestParseError(Exception):
    """Fail-closed request rejection. `status` is the wire status to send
    before closing the connection; `detail` is METADATA ONLY (C8) — it is
    passed to `_log()` and must never contain body or header content."""

    def __init__(self, status: bytes, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def parse_request_head(raw: bytes) -> RequestHead:
    """Parse and validate a non-CONNECT request head. Raises
    RequestParseError (fail closed) on ANY ambiguity — C2 and C5.

    Nothing here consults the authority or the `Host:` header for anything
    (C1): `Host:` is parsed only so that it can be dropped from the
    forwarded header set."""
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise RequestParseError(b"400 Bad Request", "non-ASCII bytes in request head")
    if not text.endswith("\r\n\r\n"):
        raise RequestParseError(b"400 Bad Request", "request head not CRLFCRLF-terminated")
    lines = text[:-4].split("\r\n")
    request_line = lines[0]
    parts = request_line.split(" ")
    if len(parts) != 3:
        raise RequestParseError(b"400 Bad Request", "malformed request line")
    method, target, version = parts
    if version not in ("HTTP/1.1", "HTTP/1.0"):
        raise RequestParseError(b"400 Bad Request", "unsupported HTTP version")
    if method not in _GATEWAY_METHODS:
        raise RequestParseError(b"400 Bad Request", f"method not permitted: {method}")
    path = _normalise_request_target(target)
    if path is None:
        raise RequestParseError(b"400 Bad Request", "malformed or non-http request target")

    header_lines = lines[1:]
    if len(header_lines) > _MAX_HEADER_LINES:
        raise RequestParseError(b"400 Bad Request", "too many request headers")

    headers: list[tuple[str, str]] = []
    content_lengths: list[str] = []
    transfer_encodings = 0
    sentinel_seen = False
    for line in header_lines:
        if not line:
            raise RequestParseError(b"400 Bad Request", "empty header line")
        if line[0] in (" ", "\t"):
            # obs-fold continuation: a classic request-smuggling primitive.
            raise RequestParseError(b"400 Bad Request", "obs-fold header continuation")
        if ":" not in line:
            raise RequestParseError(b"400 Bad Request", "header line without a colon")
        name, _, value = line.partition(":")
        if not name or any(ch.isspace() for ch in name):
            # `Foo : bar` / `Foo\t: bar` — another smuggling primitive.
            raise RequestParseError(b"400 Bad Request", "malformed header name")
        value = value.strip()
        lowered = name.lower()
        if lowered == "content-length":
            content_lengths.append(value)
        elif lowered == "transfer-encoding":
            transfer_encodings += 1
        elif lowered in ("x-api-key", "authorization"):
            if value == SENTINEL_API_KEY or value == f"Bearer {SENTINEL_API_KEY}":
                sentinel_seen = True
        headers.append((name, value))

    # C5 — framing ambiguity fails closed, in every shape.
    if transfer_encodings and content_lengths:
        raise RequestParseError(b"400 Bad Request",
                                "Content-Length and Transfer-Encoding both present")
    if transfer_encodings:
        # Deliberately not implemented for requests: the real CLI always
        # sends Content-Length (verified against the binary). "A
        # Transfer-Encoding the gateway does not fully implement -> 400."
        raise RequestParseError(b"400 Bad Request", "Transfer-Encoding requests are not accepted")
    if len(content_lengths) > 1:
        raise RequestParseError(b"400 Bad Request", "duplicate Content-Length")
    content_length = 0
    if content_lengths:
        value = content_lengths[0]
        if not value or any(ch not in _ASCII_DIGITS for ch in value):
            raise RequestParseError(b"400 Bad Request", "non-decimal Content-Length")
        content_length = int(value)
    return RequestHead(method, path, version, headers, content_length, sentinel_seen)


# ------------------------------------------------------------ socket I/O --

class _SocketReader:
    """A minimal buffered reader over a socket. Exists so a keep-alive
    gateway connection can read request N+1's head out of bytes that
    arrived in the same TCP segment as request N's body, without ever
    losing or duplicating a byte (C3/C4 — a lost boundary is what lets an
    unrewritten request through)."""

    __slots__ = ("_sock", "_buf")

    def __init__(self, sock: socket.socket, initial: bytes = b""):
        self._sock = sock
        self._buf = bytearray(initial)

    def buffered(self) -> bytes:
        return bytes(self._buf)

    def _fill(self) -> bool:
        try:
            chunk = self._sock.recv(_RECV)
        except OSError:
            return False
        if not chunk:
            return False
        self._buf.extend(chunk)
        return True

    def read_header_block(self) -> bytes | None:
        """Bytes up to and INCLUDING the first CRLFCRLF, leaving anything
        after it buffered. None if the peer closed first (ambiguous — fail
        closed) or the block exceeds `_MAX_HEADER_BYTES`."""
        while b"\r\n\r\n" not in self._buf:
            if len(self._buf) > _MAX_HEADER_BYTES:
                return None
            if not self._fill():
                return None
        if self._buf.index(b"\r\n\r\n") + 4 > _MAX_HEADER_BYTES:
            return None
        head, _, rest = bytes(self._buf).partition(b"\r\n\r\n")
        self._buf = bytearray(rest)
        return head + b"\r\n\r\n"

    def read_line(self, limit: int = _MAX_HEADER_BYTES) -> bytes | None:
        """One CRLF-terminated line, terminator included. Used for chunked
        framing. None on EOF or if the line exceeds `limit`."""
        while b"\r\n" not in self._buf:
            if len(self._buf) > limit:
                return None
            if not self._fill():
                return None
        idx = self._buf.index(b"\r\n") + 2
        line = bytes(self._buf[:idx])
        del self._buf[:idx]
        return line

    def read_some(self, want: int) -> bytes:
        """Up to `want` bytes, at least 1 unless the peer closed (b"").
        Never buffers a whole body (C5)."""
        if not self._buf and not self._fill():
            return b""
        take = min(want, len(self._buf))
        data = bytes(self._buf[:take])
        del self._buf[:take]
        return data


# ---------------------------------------------------------------- config --

class GatewayConfig:
    """The trusted-side model-API gateway configuration (addendum 2 / the
    binding gateway contract). EVERYTHING that decides where the credential
    goes lives here and ONLY here — C1.

    Constructed only via `load()` in production; the constructor is public
    so tests can inject a throwaway upstream without a config file."""

    __slots__ = ("upstream_host", "upstream_port", "credential", "credential_header",
                 "credential_prefix", "allowed_paths", "ca_file", "upstream_proxy",
                 "max_requests_per_session", "max_request_bytes_per_session",
                 "max_request_body_bytes", "_ctx")

    def __init__(self, upstream_host: str, upstream_port: int, credential: str,
                 credential_header: str = "x-api-key", credential_prefix: str = "",
                 allowed_paths: frozenset[str] = frozenset({"/v1/messages", "/api/hello"}),
                 ca_file: str | None = None,
                 upstream_proxy: tuple[str, int] | None = None,
                 max_requests_per_session: int = 500,
                 max_request_bytes_per_session: int = 256 * 1024 * 1024,
                 max_request_body_bytes: int = 32 * 1024 * 1024):
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.credential = credential            # NEVER logged, NEVER echoed (C6/C8)
        self.credential_header = credential_header
        self.credential_prefix = credential_prefix
        self.allowed_paths = allowed_paths
        self.ca_file = ca_file
        self.upstream_proxy = upstream_proxy
        self.max_requests_per_session = max_requests_per_session
        self.max_request_bytes_per_session = max_request_bytes_per_session
        self.max_request_body_bytes = max_request_body_bytes
        self._ctx: ssl.SSLContext | None = None

    # C10: built once, asserted verified. There is deliberately no config
    # key anywhere in this file that can set check_hostname=False or
    # verify_mode=CERT_NONE.
    def ssl_context(self) -> ssl.SSLContext:
        if self._ctx is None:
            ctx = ssl.create_default_context(cafile=self.ca_file)
            if not ctx.check_hostname or ctx.verify_mode != ssl.CERT_REQUIRED:
                raise ValueError("refusing to run with TLS verification disabled (contract C10)")
            self._ctx = ctx
        return self._ctx

    @classmethod
    def load(cls, raw: object, default_upstream_proxy: tuple[str, int] | None) -> "GatewayConfig":
        """Fail-closed parse of the config file's `gateway` object. Any
        problem — including a credential file that is missing, empty, or
        readable by anyone but this account — raises, and `serve_forever()`
        then refuses to start (C9). Starting un-credentialed, or forwarding
        the sentinel upstream, is never an option."""
        if not isinstance(raw, dict):
            raise ValueError("'gateway' must be a JSON object")

        upstream = raw.get("upstream")
        host, port = _split_host_port(upstream) if isinstance(upstream, str) else (None, None)
        if host is None or port is None:
            raise ValueError(f"invalid gateway.upstream (must be 'hostname:port'): {upstream!r}")
        if _is_ip_literal(host):
            # Same reasoning as the CONNECT allowlist (clause 2), plus: TLS
            # hostname verification against an IP literal needs an IP SAN and
            # is not a shape this deployment should acquire by accident.
            raise ValueError("gateway.upstream must be a hostname, not an IP literal")

        cred_path = raw.get("credential_file")
        if not isinstance(cred_path, str) or not cred_path:
            raise ValueError("gateway.credential_file is required")
        credential = _read_credential_file(cred_path)

        header = raw.get("credential_header", "x-api-key")
        if not isinstance(header, str) or header.lower() not in _ALLOWED_CREDENTIAL_HEADERS:
            raise ValueError("gateway.credential_header must be 'x-api-key' or 'authorization'")
        header = header.lower()
        prefix = raw.get("credential_prefix", "Bearer " if header == "authorization" else "")
        if not isinstance(prefix, str) or "\r" in prefix or "\n" in prefix:
            raise ValueError("gateway.credential_prefix must be a header-safe string")

        raw_paths = raw.get("allowed_paths", ["/v1/messages", "/api/hello"])
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError("gateway.allowed_paths must be a non-empty list")
        paths: set[str] = set()
        for entry in raw_paths:
            if (not isinstance(entry, str) or not entry.startswith("/")
                    or "?" in entry or any(ch.isspace() for ch in entry)):
                raise ValueError(f"invalid gateway.allowed_paths entry: {entry!r}")
            paths.add(entry)

        ca_file = raw.get("ca_file")
        if ca_file is not None and (not isinstance(ca_file, str) or not Path(ca_file).is_file()):
            raise ValueError(f"gateway.ca_file is set but not a readable file: {ca_file!r}")

        proxy = default_upstream_proxy
        raw_proxy = raw.get("upstream_proxy", "__inherit__")
        if raw_proxy != "__inherit__":
            if raw_proxy in (None, ""):
                proxy = None
            else:
                ph, pp = _split_host_port(raw_proxy) if isinstance(raw_proxy, str) else (None, None)
                if ph is None or pp is None:
                    raise ValueError(f"invalid gateway.upstream_proxy: {raw_proxy!r}")
                proxy = (ph, pp)

        def _positive_int(key: str, default: int) -> int:
            value = raw.get(key, default)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"gateway.{key} must be a positive integer")
            return value

        cfg = cls(
            upstream_host=host.lower(), upstream_port=port, credential=credential,
            credential_header=header, credential_prefix=prefix,
            allowed_paths=frozenset(paths), ca_file=ca_file, upstream_proxy=proxy,
            max_requests_per_session=_positive_int("max_requests_per_session", 500),
            max_request_bytes_per_session=_positive_int(
                "max_request_bytes_per_session", 256 * 1024 * 1024),
            max_request_body_bytes=_positive_int("max_request_body_bytes", 32 * 1024 * 1024),
        )
        cfg.ssl_context()  # C10: fail at startup, not on the first real request
        return cfg


def _read_credential_file(path: str) -> str:
    """Read the real model-API credential from its trusted-side file.
    Fail-closed on every problem (C9), and refuse a file any other account
    can read: the whole point of addendum 2 is that this value exists in
    exactly one place the sandbox cannot reach."""
    p = Path(path)
    try:
        st = p.stat()
    except OSError as exc:
        raise ValueError(f"gateway.credential_file is not readable: {exc}") from exc
    if not p.is_file():
        raise ValueError("gateway.credential_file must be a regular file")
    if st.st_mode & 0o077:
        raise ValueError("gateway.credential_file must be 0600 (no group/other access) — "
                         f"found mode {st.st_mode & 0o777:04o}")
    if st.st_uid != os.geteuid():
        raise ValueError("gateway.credential_file must be owned by the account this daemon "
                         f"runs as (file uid {st.st_uid}, daemon euid {os.geteuid()})")
    credential = p.read_text().strip()
    if not credential:
        raise ValueError("gateway.credential_file is empty")
    if credential == SENTINEL_API_KEY:
        raise ValueError("gateway.credential_file contains the sandbox sentinel, not a credential")
    if "\r" in credential or "\n" in credential:
        raise ValueError("gateway.credential_file must contain a single header-safe value")
    return credential


def _env_upstream_proxy() -> tuple[str, int] | None:
    """This daemon's OWN ambient `HTTPS_PROXY`, if set — trusted-side, read
    from this trusted process's environment, never from anything the
    sandbox can influence (the sandbox is `--clearenv`'d and its relay's
    proxy vars only point at the relay itself)."""
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not raw:
        return None
    value = raw.split("://", 1)[1] if "://" in raw else raw
    value = value.rstrip("/")
    host, port = _split_host_port(value)
    if host is None or port is None:
        return None
    return (host, port)


class AllowlistConfig:
    """The host-owned egress configuration. `allow` is a set of
    (hostname_lower, port) tuples for the CONNECT reserve path;
    `upstream_proxy` is an optional (host, port) that, when set, this proxy
    chains its own CONNECT through (this environment routes all outbound
    HTTPS via an agent egress proxy — see /root/.ccr/README.md and
    HTTPS_PROXY). When unset, allowed destinations are dialed directly.
    `gateway`, when present, enables the model-API credential gateway."""

    def __init__(self, allow: set[tuple[str, int]], upstream_proxy: tuple[str, int] | None,
                 gateway: GatewayConfig | None = None):
        self.allow = allow
        self.upstream_proxy = upstream_proxy
        self.gateway = gateway

    @classmethod
    def load(cls, config_path: str) -> "AllowlistConfig":
        data = json.loads(Path(config_path).read_text())
        if not isinstance(data, dict):
            raise ValueError("egress allowlist config must be a JSON object")
        allow: set[tuple[str, int]] = set()
        for entry in data.get("allow", []):
            host, port = _split_host_port(entry) if isinstance(entry, str) else (None, None)
            if host is None or port is None:
                raise ValueError(f"invalid allowlist entry (must be 'hostname:port'): {entry!r}")
            if _is_ip_literal(host):
                raise ValueError(f"allowlist entries must be hostnames, not IP literals: {entry!r}")
            allow.add((host.lower(), port))
        upstream_proxy = None
        raw_upstream = data.get("upstream_proxy")
        if raw_upstream:
            uh, up = _split_host_port(raw_upstream) if isinstance(raw_upstream, str) else (None, None)
            if uh is None or up is None:
                raise ValueError(f"invalid upstream_proxy (must be 'host:port'): {raw_upstream!r}")
            upstream_proxy = (uh, up)
        gateway = None
        if data.get("gateway") is not None:
            gateway = GatewayConfig.load(data["gateway"],
                                         upstream_proxy or _env_upstream_proxy())
        # C9 — the fail-closed guard is RECONCILED, not deleted. Red Team's
        # recommended posture is `allow: []` (the CONNECT path stays as live,
        # actively-denied reserve) PLUS a valid gateway config. What must
        # still be refused is a daemon that can serve NOTHING at all: an
        # empty allowlist with no gateway forwards nothing, ever, and
        # starting it would only make an unusable egress path look healthy.
        if not allow and gateway is None:
            raise ValueError("egress config permits nothing: 'allow' is empty AND no 'gateway' "
                             "is configured — refusing to start a proxy that can never forward "
                             "anything. (An empty 'allow' is correct and expected, but only "
                             "alongside a valid 'gateway' — see contract clause C9.)")
        return cls(allow, upstream_proxy, gateway)


# -------------------------------------------------------- session budgets --

class _SessionBudget:
    """The gateway-side spend ceiling Red Team moved from 'named, not built'
    to REQUIRED. Counts REQUESTS and cumulative REQUEST BYTES for one
    sandbox session and refuses (429) once either ceiling is passed.

    Why this is the only place a limit can exist: `--max-budget-usd` is
    enforced by the sandboxed CLI — the untrusted side — so a compromised
    session simply does not enforce it. This is a crude request/byte cap,
    not token-accurate cost accounting; its job is to convert 'unbounded'
    into 'bounded and alarming'."""

    __slots__ = ("requests", "request_bytes", "exhausted", "first_seen")

    def __init__(self) -> None:
        self.requests = 0
        self.request_bytes = 0
        self.exhausted = False
        self.first_seen = time.time()


_MAX_TRACKED_SESSIONS = 256


def _peer_session_key(conn: socket.socket) -> tuple:
    """Identify the sandbox session behind a client connection, WITHOUT
    trusting anything the client sends: SO_PEERCRED is filled in by the
    kernel. The peer is the in-sandbox `egress_relay.py` process — one per
    live sandbox — so its (pid, start-time, uid) is a stable per-session
    identity for as long as that sandbox runs.

    The /proc start-time is included specifically so that a recycled PID
    cannot inherit (or reset) another session's budget. If /proc is
    unreadable the key degrades to (pid, uid) with an empty start-time,
    which is still per-connection-peer and never shared with a different
    uid; it never degrades to a single global bucket that one session could
    exhaust for another."""
    try:
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
        pid, uid, _gid = struct.unpack("3i", raw)
    except OSError:
        return ("nopeer",)
    starttime = ""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        starttime = stat.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        pass
    return (pid, starttime, uid)


# --------------------------------------------------------------- the proxy --

class EgressProxy:
    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH,
                 config_path: str = DEFAULT_CONFIG_PATH,
                 config: AllowlistConfig | None = None):
        self.socket_path = socket_path
        self.config_path = config_path
        self._config = config  # injectable for tests; else loaded at serve_forever()
        self._sessions: dict[tuple, _SessionBudget] = {}
        self._sessions_lock = threading.Lock()
        self._conn_seq = 0

    def _next_conn_id(self) -> int:
        with self._sessions_lock:
            self._conn_seq += 1
            return self._conn_seq

    def _session(self, key: tuple) -> _SessionBudget:
        with self._sessions_lock:
            budget = self._sessions.get(key)
            if budget is None:
                if len(self._sessions) >= _MAX_TRACKED_SESSIONS:
                    # Bounded memory: drop the oldest entry. A dropped entry
                    # is a budget RESET, so the ceiling is only as strong as
                    # this table is large — 256 concurrent sandbox sessions
                    # on one host is far outside this design's shape, and
                    # the eviction is logged so it can never be silent.
                    oldest = min(self._sessions, key=lambda k: self._sessions[k].first_seen)
                    del self._sessions[oldest]
                    _log("session_table_evicted", tracked=len(self._sessions))
                budget = _SessionBudget()
                self._sessions[key] = budget
            return budget

    def _dial(self, config: AllowlistConfig, host: str, port: int) -> tuple[socket.socket, bytes]:
        """Open a socket to the (already-allowlisted) destination. Chains
        through the configured upstream proxy if set, else connects
        directly — resolving `host` host-side in this trusted process
        either way (clause 3).

        Returns `(sock, early_bytes)`, where `early_bytes` is any payload the
        upstream proxy coalesced after its own `200` response header block
        and which therefore still owes delivery to the client."""
        if config.upstream_proxy is not None:
            up_host, up_port = config.upstream_proxy
            sock = socket.create_connection((up_host, up_port), timeout=_IO_TIMEOUT_S)
            try:
                sock.sendall(
                    f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode("ascii")
                )
                read = _read_header_block(sock)
                if read is None:
                    raise OSError("upstream proxy closed before a complete CONNECT response")
                resp, early = read
                status_line = resp.split(b"\r\n", 1)[0]
                if b" 200 " not in status_line and not status_line.endswith(b" 200"):
                    raise OSError(f"upstream proxy refused CONNECT: {status_line!r}")
                return (sock, early)
            except OSError:
                sock.close()
                raise
        # Direct: create_connection resolves the hostname host-side.
        return (socket.create_connection((host, port), timeout=_IO_TIMEOUT_S), b"")

    def handle_connection(self, conn: socket.socket, config: AllowlistConfig) -> None:
        """The full per-connection logic, factored out of the accept loop
        so it is unit-testable directly. Never propagates — the accept loop
        also guards it, but a single bad connection must cost exactly one
        connection, never the daemon.

        Dispatch: a CONNECT goes to the addendum-1 reserve path (allowlist,
        opaque tunnel); anything else goes to the addendum-2 credential
        gateway. Both fail closed."""
        conn.settimeout(_IO_TIMEOUT_S)
        # The first head is read with the buffered reader, which bounds the
        # HEAD BLOCK rather than the read buffer. That distinction is
        # load-bearing and was found by reproducing it: the real CLI's very
        # first `POST /v1/messages` carries a body measured at 4 KB and, on
        # the same connection, 23,654 bytes — and the relay pumps in 64 KB
        # chunks, so head and body routinely arrive in ONE read. Bounding
        # the buffer (as `_read_header_block` does) rejected such a request
        # `400` before it ever reached the gateway. Verified against a
        # 25 KB first-request body: 400 before this change, forwarded and
        # credentialed after.
        reader = _SocketReader(conn)
        header = reader.read_header_block()
        if header is None:
            _reject(conn, b"400 Bad Request", "no complete request header received")
            return
        client_early = reader.buffered()
        if peek_method(header) != "CONNECT":
            if config.gateway is None:
                _reject(conn, b"403 Forbidden",
                        "non-CONNECT request but no model-API gateway is configured")
                return
            self.handle_gateway_connection(conn, config.gateway, reader, header)
            return
        # CONNECT keeps its previously-reviewed, stricter rule, now stated
        # explicitly instead of emerging as a side effect of the read loop:
        # bytes pipelined ahead of the `200` are about to be tunnelled
        # OPAQUELY, so an over-large pipelined burst is refused rather than
        # forwarded. (Code Review verified this behaviour directly: 4 KB
        # pipelined is forwarded in full, 50 KB is rejected `400` with a log
        # line. That is unchanged.)
        if len(client_early) > _MAX_HEADER_BYTES:
            _reject(conn, b"400 Bad Request",
                    "too many bytes pipelined ahead of the CONNECT response")
            return
        target = parse_connect_target(header)
        if target is None:
            _reject(conn, b"400 Bad Request", "malformed or non-CONNECT request")
            return
        host, port = target
        if _is_ip_literal(host):
            # Clause 2: an IP-literal target is refused before any allowlist
            # check, so a raw IP equal to the API's resolved address is denied.
            _reject(conn, b"403 Forbidden", f"IP-literal CONNECT target denied: {host}")
            return
        if (host.lower(), port) not in config.allow:
            _reject(conn, b"403 Forbidden", f"{host}:{port} is not in the egress allowlist")
            return
        try:
            upstream, upstream_early = self._dial(config, host, port)
        except OSError as exc:
            _reject(conn, b"502 Bad Gateway", f"could not reach allowlisted destination: {exc}")
            return
        try:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            # Hand over anything that arrived early on either side BEFORE the
            # pump starts, in the right direction, so no byte is ever lost:
            # a pipelined client request body goes upstream, and payload the
            # upstream proxy coalesced with its 200 goes to the client.
            if client_early:
                upstream.sendall(client_early)
            if upstream_early:
                conn.sendall(upstream_early)
            _tunnel(conn, upstream)
        finally:
            upstream.close()

    # ------------------------------------------------ the credential gateway --

    def _gateway_dial(self, cfg: GatewayConfig) -> ssl.SSLSocket:
        """**C1/C7/C10.** Open a fresh TLS connection to the ONE destination
        named in the trusted config. `cfg` is the only input; nothing from
        the client request reaches this function, by construction — there is
        no parameter through which it could. Never pooled or cached, so no
        two client connections ever share an upstream (C7)."""
        host, port = cfg.upstream_host, cfg.upstream_port
        if cfg.upstream_proxy is not None:
            proxy_host, proxy_port = cfg.upstream_proxy
            raw = socket.create_connection((proxy_host, proxy_port), timeout=_IO_TIMEOUT_S)
            try:
                raw.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\n"
                            f"Host: {host}:{port}\r\n\r\n".encode("ascii"))
                read = _read_header_block(raw)
                if read is None:
                    raise OSError("upstream proxy closed before a complete CONNECT response")
                resp, early = read
                status_line = resp.split(b"\r\n", 1)[0]
                if b" 200 " not in status_line and not status_line.endswith(b" 200"):
                    raise OSError("upstream proxy refused CONNECT for the configured model API")
                if early:
                    # Bytes before our ClientHello would mean the proxy is not
                    # behaving as a tunnel. Fail closed rather than feed
                    # unexplained bytes into the TLS layer.
                    raise OSError("upstream proxy sent data before the TLS handshake")
            except OSError:
                raw.close()
                raise
        else:
            raw = socket.create_connection((host, port), timeout=_IO_TIMEOUT_S)
        try:
            # C10: verified TLS, hostname = the CONFIGURED host (never the
            # request's authority or Host: header).
            tls = cfg.ssl_context().wrap_socket(raw, server_hostname=host)
        except (OSError, ssl.SSLError):
            raw.close()
            raise
        tls.settimeout(_GATEWAY_IO_TIMEOUT_S)
        return tls

    def _charge(self, budget: _SessionBudget, cfg: GatewayConfig, request_bytes: int) -> str | None:
        """Gateway-side spend ceiling. Returns None if the request may
        proceed, or a short METADATA-ONLY reason string if it must be
        refused (429). Once a session trips a ceiling it stays exhausted —
        fail closed, not a per-request retry window."""
        with self._sessions_lock:
            if budget.exhausted:
                return "session budget already exhausted"
            if budget.requests + 1 > cfg.max_requests_per_session:
                budget.exhausted = True
                return "per-session request ceiling reached"
            if budget.request_bytes + request_bytes > cfg.max_request_bytes_per_session:
                budget.exhausted = True
                return "per-session request-byte ceiling reached"
            budget.requests += 1
            budget.request_bytes += request_bytes
            return None

    def _build_upstream_head(self, cfg: GatewayConfig, head: RequestHead) -> bytes:
        """**C1/C2/C3.** Emit an origin-form request for the CONFIGURED
        upstream, with this gateway's own `Host:` and the real credential
        substituted in. Any client-supplied credential/hop-by-hop header
        was already dropped by `_STRIPPED_REQUEST_HEADERS`, so the injected
        header REPLACES rather than joins whatever the client sent."""
        authority = (cfg.upstream_host if cfg.upstream_port == 443
                     else f"{cfg.upstream_host}:{cfg.upstream_port}")
        lines = [f"{head.method} {head.path} HTTP/1.1", f"Host: {authority}"]
        for name, value in head.headers:
            if name.lower() in _STRIPPED_REQUEST_HEADERS:
                continue
            lines.append(f"{name}: {value}")
        lines.append(f"{cfg.credential_header}: {cfg.credential_prefix}{cfg.credential}")
        if head.content_length or head.method == "POST":
            lines.append(f"Content-Length: {head.content_length}")
        lines.append("Connection: keep-alive")
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

    def _relay_response(self, conn: socket.socket, up_reader: _SocketReader,
                        request_method: str) -> tuple[int, bool, int] | None:
        """**C4/C6.** Stream one upstream response back to the client
        incrementally, tracking chunked/length/EOF framing exactly so the
        next request on this connection is still parsed and rewritten
        rather than pumped through. Relays verbatim — a 3xx `Location:` is
        passed to the client and NEVER followed here (C6).

        Returns (status, keep_alive, body_bytes) or None if the upstream
        framing was unusable (fail closed: the connection is torn down)."""
        while True:
            head_bytes = up_reader.read_header_block()
            if head_bytes is None:
                return None
            text = head_bytes.decode("latin-1")
            lines = text[:-4].split("\r\n")
            status_parts = lines[0].split(" ")
            if len(status_parts) < 2 or not status_parts[1].isdigit():
                return None
            status = int(status_parts[1])
            version = status_parts[0]
            content_lengths: list[str] = []
            chunked = False
            close_requested = version == "HTTP/1.0"
            for line in lines[1:]:
                name, _, value = line.partition(":")
                lowered = name.strip().lower()
                value = value.strip()
                if lowered == "content-length":
                    content_lengths.append(value)
                elif lowered == "transfer-encoding":
                    chunked = "chunked" in value.lower()
                elif lowered == "connection" and "close" in value.lower():
                    close_requested = True
            if content_lengths and chunked:
                return None  # C5: framing ambiguity fails closed, both directions
            if len(set(content_lengths)) > 1:
                return None
            conn.sendall(head_bytes)
            if 100 <= status < 200:
                # Interim response: relayed, then the real one follows on the
                # same connection. Keep reading.
                continue
            break

        body_bytes = 0
        if request_method == "HEAD" or status in (204, 304):
            return (status, not close_requested, 0)
        if chunked:
            while True:
                line = up_reader.read_line()
                if line is None:
                    return None
                conn.sendall(line)
                size_text = line.decode("latin-1").split(";", 1)[0].strip()
                try:
                    size = int(size_text, 16)
                except ValueError:
                    return None
                if size < 0:
                    return None
                if size == 0:
                    while True:  # trailers, then the terminating CRLF
                        trailer = up_reader.read_line()
                        if trailer is None:
                            return None
                        conn.sendall(trailer)
                        if trailer == b"\r\n":
                            break
                    break
                remaining = size + 2  # chunk data plus its own CRLF
                while remaining:
                    piece = up_reader.read_some(min(_RECV, remaining))
                    if not piece:
                        return None
                    conn.sendall(piece)
                    remaining -= len(piece)
                body_bytes += size
            return (status, not close_requested, body_bytes)
        if content_lengths:
            remaining = content_lengths[0]
            if not remaining or any(ch not in _ASCII_DIGITS for ch in remaining):
                return None
            remaining = int(remaining)
            while remaining:
                piece = up_reader.read_some(min(_RECV, remaining))
                if not piece:
                    return None
                conn.sendall(piece)
                remaining -= len(piece)
                body_bytes += len(piece)
            return (status, not close_requested, body_bytes)
        # No framing headers at all: the body runs to EOF, so this
        # connection cannot carry another request (C4 — never guess a
        # boundary; end the connection instead).
        while True:
            piece = up_reader.read_some(_RECV)
            if not piece:
                break
            conn.sendall(piece)
            body_bytes += len(piece)
        return (status, False, body_bytes)

    def handle_gateway_connection(self, conn: socket.socket, cfg: GatewayConfig,
                                  reader: "_SocketReader", first_head: bytes) -> None:
        """The model-API credential gateway (addendum 2). Terminates every
        request on this client connection, validates it fail-closed,
        substitutes the sentinel credential for the real one on EVERY
        request (C3 — never once per connection), and streams the response
        back with exact framing (C4).

        `reader` is the connection's buffered reader, already holding
        whatever arrived after the head in the same read (typically the
        request body); `first_head` is the head block `handle_connection`
        already took out of it."""
        conn.settimeout(_GATEWAY_IO_TIMEOUT_S)
        conn_id = self._next_conn_id()
        budget = self._session(_peer_session_key(conn))
        head_bytes = first_head
        upstream: ssl.SSLSocket | None = None
        up_reader: _SocketReader | None = None
        try:
            while True:
                started = time.monotonic()
                try:
                    head = parse_request_head(head_bytes)
                except RequestParseError as exc:
                    _reject(conn, exc.status, exc.detail)
                    return

                path_only = head.path.split("?", 1)[0]
                if path_only not in cfg.allowed_paths:
                    # Red Team's `POST /steal` — a visible 403 from this
                    # gateway, never a silent widening of what the operator's
                    # credential is used for.
                    _log("gateway_denied_path", conn=conn_id, method=head.method, path=path_only)
                    _reject(conn, b"403 Forbidden", "request path is not in the gateway allowlist")
                    return
                if head.content_length > cfg.max_request_body_bytes:
                    _log("gateway_denied_body_size", conn=conn_id, path=path_only,
                         content_length=head.content_length)
                    _reject(conn, b"413 Payload Too Large",
                            "request body exceeds the gateway's per-request ceiling")
                    return

                request_bytes = len(head_bytes) + head.content_length
                denial = self._charge(budget, cfg, request_bytes)
                if denial is not None:
                    _log("gateway_budget_exceeded", conn=conn_id, path=path_only,
                         reason=denial, requests=budget.requests,
                         request_bytes=budget.request_bytes)
                    _reject(conn, b"429 Too Many Requests", denial)
                    return

                if upstream is None:
                    try:
                        upstream = self._gateway_dial(cfg)
                    except (OSError, ssl.SSLError, ValueError) as exc:
                        _log("gateway_upstream_error", conn=conn_id,
                             error=type(exc).__name__)
                        _reject(conn, b"502 Bad Gateway",
                                "could not reach the configured model-API upstream")
                        return
                    up_reader = _SocketReader(upstream)

                try:
                    upstream.sendall(self._build_upstream_head(cfg, head))
                    remaining = head.content_length
                    while remaining:
                        piece = reader.read_some(min(_RECV, remaining))
                        if not piece:
                            _log("gateway_client_body_truncated", conn=conn_id, path=path_only)
                            return  # fail closed: never send a half body upstream
                        upstream.sendall(piece)
                        remaining -= len(piece)
                except OSError:
                    _log("gateway_upstream_write_failed", conn=conn_id, path=path_only)
                    _reject(conn, b"502 Bad Gateway", "upstream connection failed mid-request")
                    return

                relayed = self._relay_response(conn, up_reader, head.method)
                if relayed is None:
                    _log("gateway_upstream_framing_error", conn=conn_id, path=path_only)
                    return
                status, keep_alive, body_bytes = relayed
                # C8: metadata only. No body, no header value, no credential.
                _log("gateway_request", conn=conn_id, method=head.method, path=path_only,
                     status=status, request_bytes=request_bytes, response_bytes=body_bytes,
                     sentinel_seen=head.sentinel_seen, swapped=True,
                     duration_ms=int((time.monotonic() - started) * 1000),
                     session_requests=budget.requests)
                if not keep_alive:
                    return
                nxt = reader.read_header_block()
                if nxt is None:
                    return  # client finished (or over-long head) — normal end
                head_bytes = nxt
        finally:
            if upstream is not None:
                try:
                    upstream.close()  # C7: never pooled, never reused
                except OSError:
                    pass

    def _safe_handle(self, conn: socket.socket, config: AllowlistConfig) -> None:
        try:
            self.handle_connection(conn, config)
        except OSError:
            pass  # BrokenPipe/ConnectionReset on either side — one connection, never the daemon
        except Exception:
            pass  # a hostile/misbehaving client must never take down this always-running proxy
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        config = self._config if self._config is not None else AllowlistConfig.load(self.config_path)
        # C8: metadata only — the destination and the mode set, never the
        # credential (nor its length, nor a hash of it).
        _log("config_loaded",
             connect_allow_entries=len(config.allow),
             gateway_enabled=config.gateway is not None,
             gateway_upstream=(f"{config.gateway.upstream_host}:{config.gateway.upstream_port}"
                               if config.gateway else None),
             gateway_paths=(len(config.gateway.allowed_paths) if config.gateway else 0))
        sock_path = Path(self.socket_path)
        if sock_path.exists():
            sock_path.unlink()
        sock_path.parent.mkdir(parents=True, exist_ok=True)
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(sock_path))
            os.chmod(sock_path, 0o660)  # group ai-pipeline-db (or a dedicated group) — see runbook
            server.listen(64)
            while True:
                conn, _ = server.accept()
                # Thread-per-connection: a CONNECT tunnel is long-lived, so a
                # single-threaded loop (as the opsdb broker uses) would wedge
                # every other caller. Enforcement is stateless and per-request,
                # so concurrency adds no shared-state risk.
                threading.Thread(target=self._safe_handle, args=(conn, config), daemon=True).start()
        finally:
            server.close()


# ------------------------------------------------------------------- I/O --

def _read_header_block(sock: socket.socket) -> tuple[bytes, bytes] | None:
    """Read until the CRLFCRLF end-of-headers terminator. Returns
    `(header, leftover)` — the bytes up to and including the first
    terminator, plus anything that arrived AFTER it in the same read — or
    None if the peer closed first (ambiguous — fail closed) or the header
    block exceeds the ceiling.

    The leftover is real tunnel payload and the caller MUST forward it after
    dialling (Code Review non-blocking item): a well-behaved CONNECT client
    waits for the `200` before sending anything, so there is normally none,
    but a client that pipelines (or a TLS ClientHello coalesced into the same
    TCP segment) previously had those bytes silently DROPPED here — which
    would surface as a TLS handshake that stalls until the 30s idle timeout
    with no diagnostic. Never discard them *up to the header ceiling*.

    That last qualification is exact, and is the round-3 Code Review
    non-blocking item: the `_MAX_HEADER_BYTES` check below runs after each
    extend regardless of whether the terminator has already arrived, so a
    peer that pipelines MORE than 16 KB in the same burst has the whole
    connection rejected `400` (verified: 4 KB pipelined is forwarded in
    full, 50 KB is rejected with a log line). That is fail-closed and
    audible, and it is the right posture for the two places this function
    is still used — reading an upstream proxy's own CONNECT response, and
    (via an explicit `len(client_early)` check in `handle_connection`) the
    client CONNECT path, where the pipelined bytes are about to be
    tunnelled OPAQUELY.

    The gateway path deliberately uses a different rule:
    `_SocketReader.read_header_block()` bounds the HEAD BLOCK, not the read
    buffer, because a legitimate `POST /v1/messages` body (4 KB and 23,654
    bytes, both measured against the real CLI in one session) routinely
    arrives in the same read as its head, and there it is re-parsed rather
    than tunnelled. Bounding the buffer there rejected real production
    traffic `400`; that was found by reproducing it, not by reading it."""
    buf = bytearray()
    while b"\r\n\r\n" not in buf:
        try:
            chunk = sock.recv(_RECV)
        except OSError:
            return None
        if not chunk:
            return None
        buf.extend(chunk)
        if len(buf) > _MAX_HEADER_BYTES:
            return None
    header, _, leftover = bytes(buf).partition(b"\r\n\r\n")
    return (header + b"\r\n\r\n", leftover)


def _reject(conn: socket.socket, status: bytes, detail: str) -> None:
    """Fail-closed rejection: a bare status, zero-length body, connection
    closed. C6 — the response carries NO diagnostic body, so nothing this
    daemon knows (least of all the injected credential) can be reflected
    back to the untrusted side; `detail` goes to the local log only, and is
    always a fixed metadata string chosen by this module, never client
    content."""
    try:
        conn.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Length: 0\r\n"
                     b"Connection: close\r\n\r\n")
    except OSError:
        pass
    _log("rejected", status=status.decode("ascii"), detail=detail)


def _tunnel(a: socket.socket, b: socket.socket) -> None:
    """Pump bytes both ways until either side closes or idles out."""
    a.settimeout(None)
    b.settimeout(None)
    socks = [a, b]
    while True:
        try:
            readable, _, _ = select.select(socks, [], [], _IO_TIMEOUT_S)
        except (OSError, ValueError):
            return
        if not readable:
            return  # idle timeout
        for src in readable:
            try:
                data = src.recv(_RECV)
            except OSError:
                return
            if not data:
                return
            dst = b if src is a else a
            try:
                dst.sendall(data)
            except OSError:
                return


def main() -> None:
    socket_path = os.environ.get("EGRESS_PROXY_SOCKET_PATH", DEFAULT_SOCKET_PATH)
    config_path = os.environ.get("EGRESS_PROXY_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    if os.geteuid() == 0:
        # C10's "do NOT solve a CA-readability problem by running as root",
        # made structural. The runbook provisions a trusted non-root account
        # for exactly this daemon; running as root would also mean the
        # credential file's 0600 ownership check passes for a file owned by
        # anyone this daemon should not be reading.
        _log("refusing_to_start", reason="egress_proxy must not run as root")
        raise SystemExit(1)
    proxy = EgressProxy(socket_path=socket_path, config_path=config_path)
    _log("listening", socket_path=socket_path, config_path=config_path)
    proxy.serve_forever()


if __name__ == "__main__":
    main()
