#!/usr/bin/env python3
"""ops/control-center/egress_proxy.py — TASK-023 (risks.id=3 durable
closure), finding B3: the model-API egress carve-out.

The host-side, allowlisting HTTP-CONNECT proxy that owns the ONE permitted
egress path out of the Developer sandbox. Read the Addendum ("B3 ... the
model-API network carve-out") of `ops/reviews/cto-task023-architecture.md`
and the Red Team PASS (`ops/reviews/red-team-task023-addendum-review.md`)
in full before touching this file — the allow/deny contract below is a
security boundary, not a convenience.

WHY THIS EXISTS
---------------
The sandbox keeps `--unshare-all` (including `--unshare-net`): it has no
network interface, no route, no DNS, no reachable TCP destination. The
sandboxed `claude` CLI must nonetheless reach the model API to do any work
at all. The single exception is a Unix-domain socket bind-mounted into the
sandbox (`/run/ai-pipeline/egress.sock` by default) — Unix sockets
traverse the *filesystem* namespace, not the *network* namespace, so this
grants one named, auditable channel without granting any interface. This
daemon owns that socket, speaks HTTP CONNECT over it, and forwards ONLY to
an allowlist of `hostname:port`, denying everything else.

RUNS AS: the broker's own trusted account (or a dedicated
`ai-pipeline-egress` system account) — NEVER as `ai-developer`. The
allowlist config file it reads is owned by that trusted account, is NOT
bind-mounted into the sandbox, and is therefore unreadable and unwidenable
by the sandboxed Developer even as root inside its own user namespace. See
`ops/reviews/task023-os-provisioning-runbook.md`.

THE CONNECT-PARSE ROBUSTNESS CONTRACT (Red Team's non-blocking item,
`ops/reviews/red-team-task023-addendum-review.md`, implemented here
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
import sys
import threading
from pathlib import Path

DEFAULT_SOCKET_PATH = "/run/ai-pipeline/egress.sock"
DEFAULT_CONFIG_PATH = "/etc/ai-pipeline/egress-allowlist.json"

_RECV = 65_536
_MAX_HEADER_BYTES = 16_384       # generous ceiling on the CONNECT request header block
_IO_TIMEOUT_S = 30.0             # per-socket idle timeout; a stalled tunnel/client costs one connection


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


# ---------------------------------------------------------------- config --

class AllowlistConfig:
    """The host-owned allowlist. `allow` is a set of (hostname_lower, port)
    tuples; `upstream_proxy` is an optional (host, port) that, when set,
    this proxy chains its own CONNECT through (this environment routes all
    outbound HTTPS via an agent egress proxy — see /root/.ccr/README.md and
    HTTPS_PROXY). When unset, allowed destinations are dialed directly."""

    def __init__(self, allow: set[tuple[str, int]], upstream_proxy: tuple[str, int] | None):
        self.allow = allow
        self.upstream_proxy = upstream_proxy

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
        if not allow:
            raise ValueError("egress allowlist config permits nothing ('allow' is empty) — "
                             "refusing to start a proxy that can never forward anything")
        upstream_proxy = None
        raw_upstream = data.get("upstream_proxy")
        if raw_upstream:
            uh, up = _split_host_port(raw_upstream) if isinstance(raw_upstream, str) else (None, None)
            if uh is None or up is None:
                raise ValueError(f"invalid upstream_proxy (must be 'host:port'): {raw_upstream!r}")
            upstream_proxy = (uh, up)
        return cls(allow, upstream_proxy)


# --------------------------------------------------------------- the proxy --

class EgressProxy:
    def __init__(self, socket_path: str = DEFAULT_SOCKET_PATH,
                 config_path: str = DEFAULT_CONFIG_PATH,
                 config: AllowlistConfig | None = None):
        self.socket_path = socket_path
        self.config_path = config_path
        self._config = config  # injectable for tests; else loaded at serve_forever()

    def _dial(self, config: AllowlistConfig, host: str, port: int) -> socket.socket:
        """Open a socket to the (already-allowlisted) destination. Chains
        through the configured upstream proxy if set, else connects
        directly — resolving `host` host-side in this trusted process
        either way (clause 3)."""
        if config.upstream_proxy is not None:
            up_host, up_port = config.upstream_proxy
            sock = socket.create_connection((up_host, up_port), timeout=_IO_TIMEOUT_S)
            try:
                sock.sendall(
                    f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode("ascii")
                )
                resp = _read_header_block(sock)
                status_line = resp.split(b"\r\n", 1)[0] if resp else b""
                if b" 200 " not in status_line and not status_line.endswith(b" 200"):
                    raise OSError(f"upstream proxy refused CONNECT: {status_line!r}")
                return sock
            except OSError:
                sock.close()
                raise
        # Direct: create_connection resolves the hostname host-side.
        return socket.create_connection((host, port), timeout=_IO_TIMEOUT_S)

    def handle_connection(self, conn: socket.socket, config: AllowlistConfig) -> None:
        """The full per-connection logic, factored out of the accept loop
        so it is unit-testable directly. Never propagates — the accept loop
        also guards it, but a single bad connection must cost exactly one
        connection, never the daemon."""
        conn.settimeout(_IO_TIMEOUT_S)
        header = _read_header_block(conn)
        if header is None:
            _reject(conn, b"400 Bad Request", "no complete request header received")
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
            upstream = self._dial(config, host, port)
        except OSError as exc:
            _reject(conn, b"502 Bad Gateway", f"could not reach allowlisted destination: {exc}")
            return
        try:
            conn.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            _tunnel(conn, upstream)
        finally:
            upstream.close()

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

def _read_header_block(sock: socket.socket) -> bytes | None:
    """Read until the CRLFCRLF end-of-headers terminator. Returns the bytes
    up to and including the first terminator, or None if the peer closed
    first (ambiguous — fail closed) or the header block exceeds the ceiling.
    Any bytes after the terminator are TLS/tunnel payload and are handled by
    the tunnel pump; a well-behaved CONNECT client waits for the 200 before
    sending them, so there are normally none."""
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
    return bytes(buf)


def _reject(conn: socket.socket, status: bytes, detail: str) -> None:
    try:
        conn.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Length: 0\r\n"
                     b"Connection: close\r\n\r\n")
    except OSError:
        pass
    sys.stderr.write(f"egress_proxy: rejected connection ({status.decode('ascii')}): {detail}\n")


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
    proxy = EgressProxy(socket_path=socket_path, config_path=config_path)
    print(f"egress_proxy: listening on {socket_path} (allowlist: {config_path})", file=sys.stderr)
    proxy.serve_forever()


if __name__ == "__main__":
    main()
