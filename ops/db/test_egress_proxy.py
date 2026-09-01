#!/usr/bin/env python3
"""ops/db/test_egress_proxy.py — TASK-023 (risks.id=3 durable closure)
finding B3: regression + robustness check for
ops/control-center/egress_proxy.py.

Proves the CONNECT-parse robustness contract Red Team requires
(ops/reviews/red-team-task023-addendum-review.md, "Non-blocking"), all
against a real EgressProxy served over a TEMP-PATH Unix socket in-process,
with a throwaway localhost destination standing in for the model API — a
legitimate test fixture, not OS provisioning (no accounts, no persistent
daemon, no real external network):

  1. An allowlisted hostname:port CONNECTs (200) and the tunnel round-trips.
  2. A non-allowlisted host is denied (403).
  3. An allowlisted host on the WRONG port is denied (403).
  4. A raw-IP CONNECT target equal to the allowlisted host's own resolved
     address is ALSO denied (allowlist is by hostname; IP literals rejected).
  5. A client-supplied `Host:` header is ignored — the decision is on the
     request-line target only (a Host-spoof to an allowlisted name does not
     smuggle a denied request-line host through).
  6. Parse ambiguity fails CLOSED: non-CONNECT method, no port, multiple
     colons, IPv6 bracket form, non-decimal port, trailing junk — none get
     a 200 (6 cases).
  7. Bytes PIPELINED after the CRLFCRLF terminator are forwarded to the
     destination rather than silently dropped (Code Review non-blocking
     item — a dropped TLS ClientHello would stall the handshake for 30s
     with no diagnostic).

Emits 13 checks in total (2+1+1+1+1+6+1) — the count is stated here, and
in the handoff, as an exact number rather than an estimate.

Usage: python3 ops/db/test_egress_proxy.py
"""
from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "control-center"))
import egress_proxy  # noqa: E402

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# --------------------------------------------------- throwaway destination --

def _start_dest_server() -> tuple[socket.socket, int]:
    """A localhost TCP server that greets with DEST-HELLO and echoes — the
    stand-in for the allowlisted model-API endpoint."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(8)
    port = srv.getsockname()[1]

    def _accept_loop() -> None:
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=_echo, args=(conn,), daemon=True).start()

    threading.Thread(target=_accept_loop, daemon=True).start()
    return srv, port


def _echo(conn: socket.socket) -> None:
    try:
        conn.sendall(b"DEST-HELLO\n")
        while True:
            data = conn.recv(4096)
            if not data:
                return
            conn.sendall(b"ECHO:" + data)
    except OSError:
        pass
    finally:
        conn.close()


# ------------------------------------------------------------ proxy client --

def _open(sock_path: str) -> socket.socket:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(5.0)
    s.connect(sock_path)
    return s


def _status_line(sock: socket.socket) -> bytes:
    buf = b""
    while b"\r\n" not in buf:
        try:
            chunk = sock.recv(4096)
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
    return buf.split(b"\r\n", 1)[0]


def _request_status(sock_path: str, raw: bytes) -> bytes:
    sock = _open(sock_path)
    try:
        sock.sendall(raw)
        return _status_line(sock)
    finally:
        sock.close()


def main() -> int:
    dest_srv, dest_port = _start_dest_server()
    resolved_ip = socket.gethostbyname("localhost")  # host-side resolution, mirrors the proxy's own

    config = egress_proxy.AllowlistConfig(
        allow={("localhost", dest_port)},
        upstream_proxy=None,  # direct dial — exercises the real getaddrinfo/connect path
    )
    sock_dir = tempfile.mkdtemp(prefix="egress-proxy-test-")
    sock_path = str(Path(sock_dir) / "egress.sock")
    proxy = egress_proxy.EgressProxy(socket_path=sock_path, config=config)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()

    deadline = time.time() + 5.0
    while not Path(sock_path).exists() and time.time() < deadline:
        time.sleep(0.02)
    if not Path(sock_path).exists():
        print("[FAIL] proxy never created its socket file")
        return 1

    # (1) allowlisted host:port -> 200, and the tunnel round-trips.
    sock = _open(sock_path)
    try:
        sock.sendall(f"CONNECT localhost:{dest_port} HTTP/1.1\r\nHost: localhost:{dest_port}\r\n\r\n"
                     .encode("ascii"))
        # consume the proxy's 200 header block, then exercise the tunnel
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        status = buf.split(b"\r\n", 1)[0]
        check("allowlisted localhost:port -> 200 Connection Established", b"200" in status, str(status))
        sock.sendall(b"ping")
        got = buf.split(b"\r\n\r\n", 1)[1] if b"\r\n\r\n" in buf else b""
        deadline = time.time() + 5.0
        while b"ECHO:ping" not in got and time.time() < deadline:
            try:
                chunk = sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            got += chunk
        check("tunnel round-trips through to the allowlisted destination",
              b"DEST-HELLO" in got and b"ECHO:ping" in got, str(got))
    finally:
        sock.close()

    # (2) non-allowlisted host -> 403.
    status = _request_status(sock_path, b"CONNECT evil.example.com:443 HTTP/1.1\r\n\r\n")
    check("non-allowlisted host -> 403", b"403" in status, str(status))

    # (3) allowlisted host, WRONG port -> 403.
    status = _request_status(sock_path, f"CONNECT localhost:9 HTTP/1.1\r\n\r\n".encode("ascii"))
    check("allowlisted host on a non-allowlisted port -> 403", b"403" in status, str(status))

    # (4) raw IP equal to the allowlisted host's resolved address -> 403.
    status = _request_status(sock_path,
                             f"CONNECT {resolved_ip}:{dest_port} HTTP/1.1\r\n\r\n".encode("ascii"))
    check("raw IP (= allowlisted host's resolved address) -> 403 (allowlist is by hostname)",
          b"403" in status, f"resolved_ip={resolved_ip} status={status!r}")

    # (5) client Host: header spoof is ignored — decision is on the request line.
    status = _request_status(sock_path,
                             f"CONNECT evil.example.com:{dest_port} HTTP/1.1\r\nHost: localhost\r\n\r\n"
                             .encode("ascii"))
    check("Host:-header spoof to an allowlisted name is ignored (request-line host denied)",
          b"403" in status, str(status))

    # (6) parse ambiguity fails closed — none of these get a 200.
    ambiguous = {
        "non-CONNECT method (GET)": b"GET / HTTP/1.1\r\n\r\n",
        "missing port": b"CONNECT localhost HTTP/1.1\r\n\r\n",
        "multiple colons in target": b"CONNECT localhost:80:90 HTTP/1.1\r\n\r\n",
        "IPv6 bracket form": b"CONNECT [::1]:443 HTTP/1.1\r\n\r\n",
        "non-decimal port": b"CONNECT localhost:https HTTP/1.1\r\n\r\n",
        "trailing junk in request line": b"CONNECT localhost:443 HTTP/1.1 extra\r\n\r\n",
    }
    for label, raw in ambiguous.items():
        status = _request_status(sock_path, raw)
        check(f"parse ambiguity fails closed: {label} (no 200)", b"200" not in status, str(status))

    # (7) bytes pipelined after the CRLFCRLF terminator must reach the
    # destination, not be discarded with the header block.
    sock = _open(sock_path)
    try:
        sock.sendall(f"CONNECT localhost:{dest_port} HTTP/1.1\r\n\r\nPIPELINED"
                     .encode("ascii"))
        got = b""
        deadline = time.time() + 5.0
        while b"ECHO:PIPELINED" not in got and time.time() < deadline:
            try:
                chunk = sock.recv(4096)
            except OSError:
                break
            if not chunk:
                break
            got += chunk
        check("bytes pipelined after CRLFCRLF are forwarded, not dropped",
              b"200" in got and b"ECHO:PIPELINED" in got, str(got))
    finally:
        sock.close()

    dest_srv.close()

    print()
    if FAILURES:
        print(f"{len(FAILURES)} check(s) FAILED: {FAILURES}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
