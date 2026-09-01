#!/usr/bin/env python3
"""ops/db/test_egress_gateway.py — TASK-023 addendum 2 (finding C2): the
host-side model-API credential gateway in ops/control-center/egress_proxy.py.

Proves, with real sockets and REAL TLS, every clause of the BINDING GATEWAY
CONTRACT in `ops/reviews/red-team-task023-addendum2-review.md` §4. Red Team
built the catastrophic mis-implementation and drove it from inside a real
sandbox; these are the regression tests that stop it being rebuilt.

Everything here uses throwaway processes/sockets under a temp dir, a
self-signed CA minted at test time, and a FAKE credential literal. No real
credential material is read, copied or sent anywhere, and nothing leaves
this host: the "upstream model API" is a local TLS server, and the
"attacker host" is a local TCP listener that must never be connected to.

  C1  (destination is trusted-side only)  checks 1-5, 49-51
  C2  (both request forms; else 400)      checks 1-4, 22-23
  C3  (per-request injection, no tunnel)  checks 8-10, 14-16
  C4  (real streamed SSE framing)         checks 11-13, 42-43
  C5  (framing ambiguity fails closed)    checks 17-21, 24-25, 44-46
  C6  (no redirect follow, no echo)       checks 47-48
  C7  (no cross-client upstream reuse)    check 52
  C8  (metadata-only logging)             checks 53-54
  C9  (empty-allowlist guard reconciled)  checks 55-60
  C10 (TLS verification mandatory)        checks 64-66
  spend ceiling (required, not optional)  checks 67-68
  spend ceiling vs a FORKING client (D2)  checks 69-74
  header-injection safety (D1)            checks 26-40
  path allowlist (required)               checks 6-7
  CONNECT reserve stays live + denied     checks 75-78
  round-4 non-blocking items              checks 41, 61-63

Emits 78 checks — an exact number, verified by running it, not an estimate.

The D1 and D2 batteries exist because a status-only assertion cannot see
either defect: both smuggling attacks returned `200` to the sandbox, and the
forking budget reset returned `200` twelve times. They assert on the bytes
`_build_upstream_head()` emits, on the request list a bare-LF-tolerant
upstream actually PARSED, and on statuses observed from twelve genuinely
forked processes.

Usage: python3 ops/db/test_egress_gateway.py
"""
from __future__ import annotations

import atexit
import io
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "control-center"))
import egress_proxy  # noqa: E402

FAILURES: list[str] = []
_N = 0

# A fake literal invented for this test file. It is not a credential and
# never was one; the gateway's only job here is to prove it goes to exactly
# one place.
FAKE_CREDENTIAL = "FAKE-GATEWAY-CREDENTIAL-NOT-REAL-0000"
PROMPT_MARKER = "SECRET-PROMPT-TEXT-THAT-MUST-NEVER-BE-LOGGED"


def check(label: str, condition: bool, detail: str = "") -> None:
    global _N
    _N += 1
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {_N:2d}. {label}{(' — ' + detail) if detail and not condition else ''}")
    if not condition:
        FAILURES.append(label)


# ---------------------------------------------------------------- fixtures --

def _mint_tls_cert(dirpath: Path) -> tuple[str, str]:
    """A throwaway self-signed cert for `localhost`, minted at test time so
    no private key is ever committed to this repository. It doubles as its
    own CA, which is what lets these tests exercise REAL TLS verification
    (C10) rather than disabling it — the thing the contract forbids."""
    cert = dirpath / "upstream.crt"
    key = dirpath / "upstream.key"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
        check=True, capture_output=True,
    )
    return (str(cert), str(key))


class UpstreamStub:
    """A local TLS server standing in for the model API. Records the
    METADATA of every request it receives (for this test's own assertions
    only) and answers with a real chunked SSE stream — the production
    response shape Red Team specifically noted had never been exercised."""

    def __init__(self, certfile: str, keyfile: str):
        self.requests: list[dict] = []
        self.connections = 0
        self.mode = "sse"          # "sse" | "length" | "redirect"
        self.redirect_to = ""
        self._lock = threading.Lock()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        raw = socket.socket()
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw.bind(("127.0.0.1", 0))
        raw.listen(16)
        self.port = raw.getsockname()[1]
        self._srv = ctx.wrap_socket(raw, server_side=True)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except (OSError, ssl.SSLError):
                if getattr(self._srv, "_closed", False):
                    return
                continue
            with self._lock:
                self.connections += 1
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: ssl.SSLSocket) -> None:
        buf = b""
        try:
            while True:
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                head, _, buf = buf.partition(b"\r\n\r\n")
                lines = head.decode("latin-1").split("\r\n")
                headers: list[tuple[str, str]] = []
                for line in lines[1:]:
                    name, _, value = line.partition(":")
                    headers.append((name.strip().lower(), value.strip()))
                lookup = {}
                for name, value in headers:
                    lookup.setdefault(name, []).append(value)
                length = int(lookup.get("content-length", ["0"])[0] or 0)
                body = buf[:length]
                while len(body) < length:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    body += chunk
                buf = buf[len(body):]
                with self._lock:
                    self.requests.append({
                        "request_line": lines[0],
                        "headers": headers,
                        "lookup": lookup,
                        "body": body.decode("utf-8", errors="replace"),
                    })
                self._respond(conn, lines[0].split(" ")[0])
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def _respond(self, conn: ssl.SSLSocket, method: str) -> None:
        if self.mode == "redirect":
            conn.sendall(f"HTTP/1.1 302 Found\r\nLocation: {self.redirect_to}\r\n"
                         "Content-Length: 0\r\n\r\n".encode("ascii"))
            return
        if self.mode == "length":
            body = b'{"ok":true}'
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                         + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
            return
        # Real streamed SSE: chunked, NO Content-Length, several events with
        # gaps between them (C4).
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
                     b"Transfer-Encoding: chunked\r\n\r\n")
        events = [
            b'event: message_start\ndata: {"type":"message_start"}\n\n',
            b'event: content_block_delta\ndata: {"type":"content_block_delta",'
            b'"delta":{"type":"text_delta","text":"streamed"}}\n\n',
            b'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]
        for event in events:
            conn.sendall(f"{len(event):x}\r\n".encode("ascii") + event + b"\r\n")
            time.sleep(0.01)
        conn.sendall(b"0\r\n\r\n")

    def credential_values(self) -> list[str]:
        with self._lock:
            out = []
            for req in self.requests:
                out.extend(req["lookup"].get("x-api-key", []))
                out.extend(req["lookup"].get("authorization", []))
            return out


class BareLfUpstreamStub:
    """A TLS upstream that treats a BARE LF as a line terminator — which RFC
    9112 §2.2 explicitly permits a recipient to do, and which many real
    servers and proxies do.

    This is the rig Code Review round 4 built to reproduce finding D1, and it
    is here because a strict CRLF-only stub CANNOT see the bug: both smuggling
    attacks returned `200` to the sandbox, so a status-only assertion passes
    while a second request is being smuggled onto the credentialed upstream
    connection. What this stub records is what it actually PARSED — the list
    of request lines and the list of `x-api-key` header lines — which is the
    only assertion that catches a smuggled request or an attacker-chosen
    credential header."""

    _METHODS = ("GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH")

    def __init__(self, certfile: str, keyfile: str):
        self.request_lines: list[str] = []
        self.api_key_lines: list[str] = []
        self._lock = threading.Lock()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        raw = socket.socket()
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raw.bind(("127.0.0.1", 0))
        raw.listen(16)
        self.port = raw.getsockname()[1]
        self._srv = ctx.wrap_socket(raw, server_side=True)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except (OSError, ssl.SSLError):
                continue
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: ssl.SSLSocket) -> None:
        buf = b""
        try:
            while True:
                while b"\r\n\r\n" not in buf:
                    chunk = conn.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                head, _, buf = buf.partition(b"\r\n\r\n")
                length = 0
                # The bare-LF tolerance: split on LF, not CRLF, so a value
                # carrying a bare LF becomes two lines here exactly as it
                # would on a tolerant server.
                for line in head.decode("latin-1").split("\n"):
                    line = line.rstrip("\r")
                    parts = line.split(" ")
                    if len(parts) == 3 and parts[0] in self._METHODS \
                            and parts[2].startswith("HTTP/1."):
                        with self._lock:
                            self.request_lines.append(line)
                    lowered = line.lower()
                    if lowered.startswith("x-api-key:"):
                        with self._lock:
                            self.api_key_lines.append(line)
                    if lowered.startswith("content-length:"):
                        try:
                            length = int(line.split(":", 1)[1].strip())
                        except ValueError:
                            length = 0
                while len(buf) < length:
                    chunk = conn.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                buf = buf[length:]
                body = b'{"ok":true}'
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
        except (OSError, ssl.SSLError, ValueError):
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def snapshot(self) -> tuple[list[str], list[str]]:
        with self._lock:
            return (list(self.request_lines), list(self.api_key_lines))


class AttackerStub:
    """The host an attacker-controlled authority would point at. It exists
    only so the tests can assert it is NEVER connected to."""

    def __init__(self) -> None:
        self.connections = 0
        self.data = b""
        self._lock = threading.Lock()
        self._srv = socket.socket()
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind(("127.0.0.1", 0))
        self._srv.listen(8)
        self.port = self._srv.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self._srv.accept()
            except OSError:
                return
            with self._lock:
                self.connections += 1
            threading.Thread(target=self._drain, args=(conn,), daemon=True).start()

    def _drain(self, conn: socket.socket) -> None:
        try:
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    return
                with self._lock:
                    self.data += chunk
        except OSError:
            pass
        finally:
            conn.close()


def _write_credential(dirpath: Path, value: str = FAKE_CREDENTIAL, mode: int = 0o600) -> Path:
    path = dirpath / "model-api-credential"
    path.write_text(value + "\n")
    path.chmod(mode)
    return path


def _start_proxy(config: egress_proxy.AllowlistConfig, dirpath: Path,
                 name: str = "gw") -> tuple[egress_proxy.EgressProxy, str]:
    sock_path = str(dirpath / f"{name}.sock")
    proxy = egress_proxy.EgressProxy(socket_path=sock_path, config=config)
    threading.Thread(target=proxy.serve_forever, daemon=True).start()
    deadline = time.time() + 5.0
    while not Path(sock_path).exists() and time.time() < deadline:
        time.sleep(0.02)
    return proxy, sock_path


# ------------------------------------------------------------ tiny client --

def _connect(sock_path: str) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(15.0)
    sock.connect(sock_path)
    return sock


def _read_response(sock: socket.socket) -> tuple[bytes, bytes]:
    """Read one complete HTTP response (chunked, Content-Length, or bare)
    and return (head, body). Deliberately a separate, independent
    implementation from the gateway's own framing code."""
    buf = b""
    while b"\r\n\r\n" not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            return (buf, b"")
        buf += chunk
    head, _, rest = buf.partition(b"\r\n\r\n")
    lowered = head.decode("latin-1").lower()
    if "transfer-encoding: chunked" in lowered:
        body = b""
        while True:
            while b"\r\n" not in rest:
                chunk = sock.recv(65536)
                if not chunk:
                    return (head, body)
                rest += chunk
            line, _, rest = rest.partition(b"\r\n")
            size = int(line.split(b";")[0].strip(), 16)
            if size == 0:
                return (head, body)
            while len(rest) < size + 2:
                chunk = sock.recv(65536)
                if not chunk:
                    return (head, body)
                rest += chunk
            body += rest[:size]
            rest = rest[size + 2:]
    length = 0
    for line in head.decode("latin-1").split("\r\n")[1:]:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    while len(rest) < length:
        chunk = sock.recv(65536)
        if not chunk:
            break
        rest += chunk
    return (head, rest[:length])


def _one_shot(sock_path: str, raw: bytes) -> bytes:
    sock = _connect(sock_path)
    try:
        sock.sendall(raw)
        head, _ = _read_response(sock)
        return head.split(b"\r\n", 1)[0]
    except (OSError, ValueError) as exc:  # a closed connection is also fail-closed
        return f"<no response: {exc}>".encode("ascii")
    finally:
        sock.close()


def _post(path_or_uri: str, host_header: str, body: str = '{"stream":true}') -> bytes:
    payload = body.encode("utf-8")
    return (f"POST {path_or_uri} HTTP/1.1\r\nHost: {host_header}\r\n"
            f"Content-Type: application/json\r\n"
            f"x-api-key: {egress_proxy.SENTINEL_API_KEY}\r\n"
            f"Content-Length: {len(payload)}\r\n\r\n").encode("ascii") + payload


# ----------------------------------------------------------------- the run --

def main() -> int:  # noqa: C901 — a linear, readable sequence of contract checks
    tmp = Path(tempfile.mkdtemp(prefix="egress-gateway-test-"))
    # Leave no residue: certs, fake-credential files and socket files all
    # live under here and are removed when the process exits (the daemons
    # holding those sockets die with it). Registered rather than placed at
    # the end of `main()` so an early return or an exception still cleans up.
    atexit.register(shutil.rmtree, tmp, True)
    certfile, keyfile = _mint_tls_cert(tmp)
    upstream = UpstreamStub(certfile, keyfile)
    attacker = AttackerStub()
    cred_file = _write_credential(tmp)

    gateway = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=upstream.port,
        credential=FAKE_CREDENTIAL, credential_header="x-api-key",
        allowed_paths=frozenset({"/v1/messages", "/api/hello"}),
        ca_file=certfile,
    )
    config = egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=gateway)
    proxy, sock_path = _start_proxy(config, tmp)
    if not Path(sock_path).exists():
        print("[FAIL] gateway proxy never created its socket file")
        return 1

    # ---- C1: the finding that decides the review. Red Team's own two attack
    # shapes, driven at a real gateway over a real socket.

    # (a) absolute-form URI with an attacker authority.
    sock = _connect(sock_path)
    sock.sendall(_post(f"http://127.0.0.1:{attacker.port}/v1/messages", f"127.0.0.1:{attacker.port}"))
    head, body = _read_response(sock)
    sock.close()
    check("C1 absolute-form attacker authority: request still reaches the CONFIGURED upstream",
          b"200" in head.split(b"\r\n", 1)[0] and b"streamed" in body, f"{head!r}")
    check("C1 absolute-form attacker authority: attacker host received ZERO connections",
          attacker.connections == 0, f"connections={attacker.connections}")

    # (b) origin-form with an attacker `Host:` header.
    sock = _connect(sock_path)
    sock.sendall(_post("/v1/messages", f"127.0.0.1:{attacker.port}"))
    head, body = _read_response(sock)
    sock.close()
    check("C1 Host:-header attacker authority: request still reaches the CONFIGURED upstream",
          b"200" in head.split(b"\r\n", 1)[0] and b"streamed" in body, f"{head!r}")
    check("C1 Host:-header attacker authority: attacker host STILL received ZERO connections",
          attacker.connections == 0, f"connections={attacker.connections}")
    check("C1 the attacker host received not one byte of the credential",
          FAKE_CREDENTIAL.encode() not in attacker.data, "credential bytes reached the attacker")

    # ---- path allowlist (required): Red Team's `POST /steal`.
    before = len(upstream.requests)
    status = _one_shot(sock_path, _post("/steal", "127.0.0.1:8889"))
    check("path allowlist: POST /steal is denied 403 by the gateway",
          b"403" in status, str(status))
    check("path allowlist: the denied path never reached the upstream at all",
          len(upstream.requests) == before, f"{len(upstream.requests)} vs {before}")

    # ---- C3 + C4: per-request injection across a keep-alive session whose
    # responses are REAL streamed SSE.
    before = len(upstream.requests)
    sock = _connect(sock_path)
    bodies = []
    for _ in range(3):
        sock.sendall(_post("/v1/messages", "127.0.0.1:8889",
                           json.dumps({"stream": True, "prompt": PROMPT_MARKER})))
        head, body = _read_response(sock)
        bodies.append((head, body))
    sock.close()
    session = upstream.requests[before:]
    check("C3 keep-alive: all 3 requests on ONE client connection reached the upstream",
          len(session) == 3, f"got {len(session)}")
    check("C3 keep-alive: 3/3 upstream requests carried the injected credential (not just the first)",
          all(req["lookup"].get("x-api-key") == [FAKE_CREDENTIAL] for req in session),
          str([req["lookup"].get("x-api-key") for req in session]))
    check("C3 keep-alive: 0/3 upstream requests carried the sandbox sentinel",
          not any(egress_proxy.SENTINEL_API_KEY in v for v in upstream.credential_values()))
    check("C4 SSE: every response streamed back complete, with framing tracked per request",
          all(b"streamed" in body and b"message_stop" in body for _, body in bodies),
          str([len(b) for _, b in bodies]))
    check("C4 SSE: responses had no Content-Length (the real chunked shape, not a stub)",
          all(b"content-length" not in head.lower() for head, _ in bodies))
    check("C4 SSE: request bodies arrived upstream intact across the keep-alive session",
          all(PROMPT_MARKER in req["body"] for req in session))
    check("C3 the upstream saw exactly one x-api-key header per request",
          all(len(req["lookup"].get("x-api-key", [])) == 1 for req in session))

    # ---- C3: a client-supplied credential is REPLACED, never appended.
    before = len(upstream.requests)
    payload = b'{"x":1}'
    sock = _connect(sock_path)
    sock.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: 127.0.0.1:8889\r\n"
                 b"x-api-key: CLIENT-SUPPLIED-JUNK\r\n"
                 b"Authorization: Bearer CLIENT-SUPPLIED-BEARER\r\n"
                 b"Proxy-Authorization: Basic CLIENT-SUPPLIED-PROXY\r\n"
                 + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii") + payload)
    _read_response(sock)
    sock.close()
    req = upstream.requests[before]
    check("C3 a client-supplied x-api-key is replaced, not appended",
          req["lookup"].get("x-api-key") == [FAKE_CREDENTIAL],
          str(req["lookup"].get("x-api-key")))
    check("C3 client Authorization/Proxy-Authorization headers are dropped entirely",
          "authorization" not in req["lookup"] and "proxy-authorization" not in req["lookup"],
          str(sorted(req["lookup"])))

    # ---- C2/C5: fail-closed request handling.
    fail_closed = [
        ("C5 Content-Length + Transfer-Encoding together -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n"
         b"Transfer-Encoding: chunked\r\n\r\nhello"),
        ("C5 duplicate Content-Length -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nContent-Length: 5\r\n"
         b"Content-Length: 6\r\n\r\nhello"),
        ("C5 non-decimal Content-Length -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nContent-Length: 0x5\r\n\r\nhello"),
        ("C5 chunked request framing (unimplemented here) -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nTransfer-Encoding: chunked\r\n\r\n"
         b"5\r\nhello\r\n0\r\n\r\n"),
        ("C5 obs-fold header continuation (smuggling primitive) -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nX-Thing: a\r\n \tb\r\n\r\n"),
        ("C2 unknown method -> 400",
         b"DELETE /v1/messages HTTP/1.1\r\nHost: h\r\n\r\n"),
        ("C2 non-http absolute-form scheme -> 400",
         b"POST ftp://evil.example.com/v1/messages HTTP/1.1\r\nHost: h\r\n\r\n"),
        ("C5 header name with embedded whitespace -> 400",
         b"POST /v1/messages HTTP/1.1\r\nHost: h\r\nX-Bad Name: v\r\n\r\n"),
    ]
    before = len(upstream.requests)
    for label, raw in fail_closed:
        status = _one_shot(sock_path, raw)
        check(label, b"400" in status, str(status))
    check("C5 none of the fail-closed request shapes reached the upstream",
          len(upstream.requests) == before, f"{len(upstream.requests)} vs {before}")

    # ---- D1 (Code Review round 4): header VALUES were never checked for a
    # bare CR/LF, so a bare LF survived `value.strip()` and was written
    # verbatim into the upstream request. Two consequences, both reproduced
    # live from inside a real sandbox: a SECOND request smuggled past the
    # request-path allowlist onto the already-credentialed TLS connection,
    # and an attacker-chosen credential header ahead of the injected one.
    # Both returned `200`, so EVERY assertion below is on bytes or on what
    # the upstream PARSED — never on the client-visible status alone.

    SMUGGLE = "junk\nGET /steal HTTP/1.1\nHost: evil"
    CRED_INJECT = "junk\nx-api-key: ATTACKER-CHOSEN"

    def _head(header_line: bytes) -> bytes:
        return (b"POST /v1/messages HTTP/1.1\r\nHost: h\r\n" + header_line
                + b"\r\nContent-Length: 0\r\n\r\n")

    def _parses(raw: bytes) -> tuple[bool, str]:
        try:
            egress_proxy.parse_request_head(raw)
            return (True, "")
        except egress_proxy.RequestParseError as exc:
            return (False, f"{exc.status!r} {exc.detail}")

    # (a) byte-level, with no server at all: the shipped parser must refuse
    # each shape, so `_build_upstream_head()` can never be reached with it.
    for label, value in [
        ("bare LF (the smuggling shape)", SMUGGLE.encode("ascii")),
        ("bare LF (the credential-header shape)", CRED_INJECT.encode("ascii")),
        ("bare CR", b"junk\rGET /steal HTTP/1.1"),
        ("NUL", b"ju\x00nk"),
        ("bare LF alone at the end of a value", b"junk\n"),
    ]:
        accepted, detail = _parses(_head(b"X-Foo: " + value))
        check(f"D1 header value containing {label} -> fail-closed 400, never emitted",
              not accepted and "400" in detail, detail or "ACCEPTED")
    accepted, detail = _parses(_head(b"X-B\x00ad: v"))
    check("D1 header NAME containing a NUL -> 400 (the old isspace() check let it through)",
          not accepted and "400" in detail, detail or "ACCEPTED")

    # A REAL CRLF in the same position is not smuggling — it is simply two
    # header lines — and must still be handled the C3 way: the client's
    # `x-api-key` is dropped and replaced, never joined.
    crlf_head = egress_proxy.parse_request_head(
        _head(b"X-Foo: junk\r\nx-api-key: ATTACKER-CHOSEN"))
    emitted = proxy._build_upstream_head(gateway, crlf_head)
    check("D1 CRLF-in-value (two real headers): emitted head carries exactly ONE x-api-key",
          emitted.lower().count(b"x-api-key") == 1
          and b"ATTACKER-CHOSEN" not in emitted
          and FAKE_CREDENTIAL.encode() in emitted, repr(emitted))
    body_lines = emitted.split(b"\r\n")
    check("D1 every line of the emitted upstream head is free of bare CR/LF/NUL",
          all(not egress_proxy.breaks_header_framing(line.decode("latin-1"))
              for line in body_lines), repr(emitted))

    # (b) live, through the shipped gateway, over real TLS, against an
    # upstream that ACCEPTS bare LF as a line terminator.
    lf_upstream = BareLfUpstreamStub(certfile, keyfile)
    lf_gateway = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=lf_upstream.port,
        credential=FAKE_CREDENTIAL, ca_file=certfile,
        allowed_paths=frozenset({"/v1/messages"}),
    )
    lf_proxy, lf_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=lf_gateway),
        tmp, name="barelf")

    # The rig proves itself first: fed the EXACT bytes the pre-fix
    # `_build_upstream_head()` emitted (quoted from the round-4 review), this
    # upstream parses TWO requests and TWO x-api-key lines. Without this
    # control the tests below would pass against a stub that simply cannot
    # see the attack.
    ctx = ssl.create_default_context(cafile=certfile)
    direct = ctx.wrap_socket(socket.create_connection(("localhost", lf_upstream.port), timeout=10),
                             server_hostname="localhost")
    direct.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: localhost\r\n"
                   b"X-Foo: junk\nGET /steal HTTP/1.1\nHost: evil\r\n"
                   b"X-Bar: junk\nx-api-key: ATTACKER-CHOSEN\r\n"
                   b"x-api-key: " + FAKE_CREDENTIAL.encode("ascii") + b"\r\n"
                   b"Content-Length: 0\r\n\r\n")
    time.sleep(0.3)
    direct.close()
    parsed, keys = lf_upstream.snapshot()
    check("D1 CONTROL: the bare-LF upstream really does parse the pre-fix bytes as TWO "
          "requests and TWO credentials (so these assertions can fail)",
          "GET /steal HTTP/1.1" in parsed
          and any("ATTACKER-CHOSEN" in line for line in keys),
          f"parsed={parsed} keys={keys}")

    baseline_requests = len(lf_upstream.request_lines)
    statuses = []
    for value in (SMUGGLE, CRED_INJECT):
        statuses.append(_one_shot(lf_sock, _head(f"X-Foo: {value}".encode("ascii"))))
    time.sleep(0.3)
    parsed, keys = lf_upstream.snapshot()
    check("D1 live: both smuggling requests are refused 400 at the gateway",
          all(b"400" in s for s in statuses), str(statuses))
    check("D1 live: the bare-LF upstream parsed ZERO further requests (nothing smuggled)",
          len(parsed) == baseline_requests, f"{len(parsed) - baseline_requests} new: {parsed}")
    check("D1 live: `GET /steal` never reached the upstream, on the credentialed "
          "connection or any other",
          parsed.count("GET /steal HTTP/1.1") == 1,  # only the CONTROL's own
          str(parsed))
    check("D1 live: no attacker-chosen x-api-key line ever reached the upstream from "
          "the gateway",
          len([line for line in keys if "ATTACKER-CHOSEN" in line]) == 1,  # the CONTROL's
          str(keys))

    # And the gateway still works normally against that same upstream, so the
    # new check is not a blanket refusal.
    status = _one_shot(lf_sock, _post("/v1/messages", "h"))
    parsed, keys = lf_upstream.snapshot()
    check("D1 a legitimate request through the same gateway still succeeds, credentialed",
          b"200" in status
          and parsed[-1] == "POST /v1/messages HTTP/1.1"
          and keys[-1] == f"x-api-key: {FAKE_CREDENTIAL}",
          f"{status!r} parsed={parsed[-1:]} keys={keys[-1:]}")

    # (c) the shared helper itself: one primitive, used on both the untrusted
    # request path and the operator-written credential strings.
    check("D1 is_header_value() is strictly stronger than breaks_header_framing()",
          all(not egress_proxy.is_header_value(bad)
              for bad in ("a\rb", "a\nb", "a\x00b", "a\x0bb", "a\x7fb"))
          and egress_proxy.is_header_value("Bearer ")
          and egress_proxy.is_header_value("NOT-A-KEY-JUST-A-CHARSET-PROBE_-.~")
          and not egress_proxy.is_header_name("X Bad")
          and not egress_proxy.is_header_name("X\x00Bad")
          and egress_proxy.is_header_name("x-api-key"))

    # ---- Code Review round-4 non-blocking item: a bare-LF request head used
    # to hold a thread until the 30s idle timeout with no log line, because it
    # never satisfies the CRLFCRLF search. It is a head this parser can never
    # accept, so it must fail fast and audibly.
    started_at = time.time()
    status = _one_shot(lf_sock, b"POST /v1/messages HTTP/1.1\nHost: h\n\n")
    elapsed = time.time() - started_at
    check("non-blocking: an LF-only request head is rejected 400 immediately, not hung",
          b"400" in status and elapsed < 5.0, f"{status!r} after {elapsed:.1f}s")

    # ---- C4/C5 regression, found by reproducing it rather than reading it:
    # the FIRST request's head and a large body routinely arrive in ONE read
    # (the relay pumps in 64 KB chunks and the real CLI sends 4 KB and
    # 23,654-byte bodies in the same session). Bounding the read BUFFER
    # rather than the head block rejected that with a 400 before it reached
    # the gateway at all.
    before = len(upstream.requests)
    big_body = json.dumps({"prompt": "x" * 25000}).encode("utf-8")
    sock = _connect(sock_path)
    sock.sendall(b"POST /v1/messages HTTP/1.1\r\nHost: h\r\n"
                 + f"Content-Length: {len(big_body)}\r\n\r\n".encode("ascii") + big_body)
    head, body = _read_response(sock)
    sock.close()
    check("C4 a FIRST request whose head+25KB body arrive in one read is forwarded, not 400'd",
          b"200" in head.split(b"\r\n", 1)[0] and b"streamed" in body, f"{head!r}")
    check("C4 that large first request reached the upstream credentialed and intact",
          len(upstream.requests) == before + 1
          and upstream.requests[-1]["lookup"].get("x-api-key") == [FAKE_CREDENTIAL]
          and len(upstream.requests[-1]["body"]) == len(big_body),
          f"{len(upstream.requests) - before} new requests")

    # ---- CONNECT keeps its stricter, previously-reviewed rule: bytes
    # pipelined ahead of the 200 are about to be tunnelled OPAQUELY, so an
    # over-large burst is refused rather than forwarded.
    status = _one_shot(sock_path,
                       b"CONNECT localhost:443 HTTP/1.1\r\n\r\n" + b"A" * 50_000)
    check("CONNECT: a >16KB pipelined burst is still rejected 400 (unchanged behaviour)",
          b"400" in status, str(status))

    # ---- C5: an oversized header block is rejected, not buffered.
    flood = (b"POST /v1/messages HTTP/1.1\r\nHost: h\r\n"
             + b"".join(b"X-Pad-%d: %s\r\n" % (i, b"A" * 400) for i in range(60))
             + b"\r\n")
    status = _one_shot(sock_path, flood)
    check("C5 oversized request header block -> rejected, never buffered unbounded",
          b"400" in status or b"no response" in status, str(status))

    # ---- C5: a huge declared Content-Length is refused BEFORE any body is read.
    huge = (b"POST /v1/messages HTTP/1.1\r\nHost: h\r\n"
            b"Content-Length: 99999999999\r\n\r\n")
    status = _one_shot(sock_path, huge)
    check("C5 an absurd declared Content-Length is refused 413 (never OOMs the daemon)",
          b"413" in status, str(status))

    # ---- C6: no redirect following, no credential in the response path.
    upstream.mode = "redirect"
    upstream.redirect_to = f"http://127.0.0.1:{attacker.port}/collect"
    before_attacker = attacker.connections
    sock = _connect(sock_path)
    sock.sendall(_post("/v1/messages", "127.0.0.1:8889"))
    head, _ = _read_response(sock)
    sock.close()
    upstream.mode = "sse"
    check("C6 a 3xx is relayed to the client verbatim and NEVER followed",
          b"302" in head and b"Location:" in head and attacker.connections == before_attacker,
          f"head={head!r} attacker={attacker.connections}")
    check("C6 no response head returned to the client contains the injected credential",
          FAKE_CREDENTIAL.encode() not in head)

    # ---- C1 unit-level: the normalisation function cannot even return an
    # authority, so no caller can accidentally route on one.
    check("C1 _normalise_request_target() discards the authority and returns a path only",
          egress_proxy._normalise_request_target(
              "http://evil.example.com:9/v1/messages?beta=true") == "/v1/messages?beta=true")
    check("C1 _normalise_request_target() rejects a non-http scheme (fail closed)",
          egress_proxy._normalise_request_target("gopher://evil/x") is None)
    check("C1 _normalise_request_target() rejects a target that is not a path",
          egress_proxy._normalise_request_target("*") is None
          and egress_proxy._normalise_request_target("evil.example.com:443") is None)

    # ---- C7: no upstream connection is shared across client connections.
    upstream_before = upstream.connections
    for _ in range(2):
        sock = _connect(sock_path)
        sock.sendall(_post("/v1/messages", "h"))
        _read_response(sock)
        sock.close()
        time.sleep(0.05)
    check("C7 two client connections produce two distinct upstream connections (never pooled)",
          upstream.connections - upstream_before == 2,
          f"delta={upstream.connections - upstream_before}")

    # ---- C8: metadata-only logging. The capture is lock-protected because
    # the daemon logs from its own per-connection threads (a bare StringIO
    # loses interleaved writes and made this check flaky), and each request
    # waits for its own log line rather than racing a fixed sleep.
    class _Capture:
        def __init__(self) -> None:
            self._buf = io.StringIO()
            self._lock = threading.Lock()

        def write(self, text: str) -> int:
            with self._lock:
                return self._buf.write(text)

        def flush(self) -> None:
            pass

        def value(self) -> str:
            with self._lock:
                return self._buf.getvalue()

    def _await(cap: "_Capture", token: str) -> None:
        deadline = time.time() + 5.0
        while token not in cap.value() and time.time() < deadline:
            time.sleep(0.02)

    captured = _Capture()
    real_stderr = sys.stderr
    sys.stderr = captured
    try:
        sock = _connect(sock_path)
        sock.sendall(_post("/v1/messages", "h", json.dumps({"prompt": PROMPT_MARKER})))
        _read_response(sock)
        sock.close()
        _await(captured, "gateway_request")
        _one_shot(sock_path, _post("/steal", "h"))
        _await(captured, "gateway_denied_path")
    finally:
        sys.stderr = real_stderr
    log_text = captured.value()
    check("C8 the daemon's whole log output contains no part of the credential",
          FAKE_CREDENTIAL not in log_text and FAKE_CREDENTIAL[:12] not in log_text,
          "credential literal found in log output")
    check("C8 the daemon's whole log output contains no prompt/body text, but does log metadata",
          PROMPT_MARKER not in log_text and "gateway_request" in log_text,
          f"log={log_text[:300]!r}")

    # ---- C9: the empty-allowlist guard, reconciled rather than deleted.
    def _cfg_file(payload: dict) -> str:
        path = tmp / f"cfg-{abs(hash(json.dumps(payload, sort_keys=True)))}.json"
        path.write_text(json.dumps(payload))
        return str(path)

    def _loads(payload: dict) -> tuple[bool, str]:
        try:
            egress_proxy.AllowlistConfig.load(_cfg_file(payload))
            return (True, "")
        except (ValueError, OSError) as exc:
            return (False, str(exc))

    gw_payload = {"upstream": "localhost:443", "credential_file": str(cred_file),
                  "ca_file": certfile}
    ok, err = _loads({"allow": []})
    check("C9 empty allowlist AND no gateway -> still refuses to start (guard retained)",
          not ok and "permits nothing" in err, err)
    ok, err = _loads({"allow": [], "gateway": gw_payload})
    check("C9 empty allowlist WITH a valid gateway -> starts (the recommended posture)", ok, err)
    ok, err = _loads({"allow": ["api.anthropic.com:443"]})
    check("C9 a non-empty allowlist with no gateway still loads (CONNECT-only, unchanged)", ok, err)

    missing = dict(gw_payload, credential_file=str(tmp / "does-not-exist"))
    ok, err = _loads({"allow": [], "gateway": missing})
    check("C9 a missing credential file -> refuses to start (never forwards un-credentialed)",
          not ok and "credential_file" in err, err)

    loose_dir = tmp / "loose"
    loose_dir.mkdir(exist_ok=True)
    loose = _write_credential(loose_dir, mode=0o644)
    ok, err = _loads({"allow": [], "gateway": dict(gw_payload, credential_file=str(loose))})
    check("C9 a group/world-readable credential file -> refuses to start",
          not ok and "0600" in err, err)

    sentinel_file = tmp / "sentinel-cred"
    sentinel_file.write_text(egress_proxy.SENTINEL_API_KEY)
    sentinel_file.chmod(0o600)
    ok, err = _loads({"allow": [], "gateway": dict(gw_payload, credential_file=str(sentinel_file))})
    check("C9 a credential file holding the SENTINEL -> refuses to start (never forwards it)",
          not ok and "sentinel" in err, err)

    # ---- D1, config side: the ONE header-safety primitive now guards the
    # operator-written strings AND the sandbox-supplied ones. Before D1 the
    # credential_prefix check was the only one in the file.
    ok_prefix, err_prefix = _loads({"allow": [], "gateway": dict(
        gw_payload, credential_prefix="Bearer \nx-api-key: ATTACKER")})
    ctl_cred = tmp / "control-char-cred"
    ctl_cred.write_text("FAKE\x0bCREDENTIAL")
    ctl_cred.chmod(0o600)
    ok_cred, err_cred = _loads({"allow": [], "gateway": dict(
        gw_payload, credential_file=str(ctl_cred))})
    check("D1 config side: a header-unsafe credential_prefix and a control-character "
          "credential both refuse to start",
          not ok_prefix and "header-safe" in err_prefix
          and not ok_cred and "header-safe" in err_cred,
          f"{err_prefix} | {err_cred}")
    ok_host, err_host = _loads({"allow": [], "gateway": dict(
        gw_payload, upstream="local\x00host:443")})
    check("D1 config side: a NUL in gateway.upstream's host is refused (it becomes the "
          "emitted Host: header)",
          not ok_host and "upstream" in err_host, err_host)

    # ---- Code Review round-4 non-blocking item: an unknown `gateway.*` key
    # used to be ignored, so a typo in a ceiling silently reverted it to the
    # default. A mis-provisioned control must be loud.
    ok_typo, err_typo = _loads({"allow": [], "gateway": dict(
        gw_payload, max_requests_per_sesion=5)})
    ok_known, err_known = _loads({"allow": [], "gateway": dict(
        gw_payload, max_requests_per_session=5)})
    check("non-blocking: a mis-typed gateway.* key refuses to start instead of silently "
          "reverting the ceiling to its default",
          not ok_typo and "max_requests_per_sesion" in err_typo and ok_known,
          f"typo={err_typo} correct={err_known}")

    # ---- C10: TLS verification is real and cannot be turned off.
    ctx = gateway.ssl_context()
    check("C10 the gateway's TLS context verifies hostname and requires a certificate",
          ctx.check_hostname and ctx.verify_mode == ssl.CERT_REQUIRED)

    other_dir = tmp / "othercert"
    other_dir.mkdir(exist_ok=True)
    other_cert, other_key = _mint_tls_cert(other_dir)
    untrusted = UpstreamStub(other_cert, other_key)
    bad_gateway = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=untrusted.port,
        credential=FAKE_CREDENTIAL, ca_file=certfile,   # WRONG CA for this upstream
        allowed_paths=frozenset({"/v1/messages"}),
    )
    bad_proxy, bad_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=bad_gateway),
        tmp, name="badtls")
    status = _one_shot(bad_sock, _post("/v1/messages", "h"))
    check("C10 an untrusted upstream certificate fails CLOSED (502), never falls back to no TLS",
          b"502" in status, str(status))
    check("C10 the credential never reached the upstream whose certificate failed verification",
          not untrusted.requests, f"{len(untrusted.requests)} requests got through")

    # ---- the required gateway-side spend ceiling.
    tight = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=upstream.port,
        credential=FAKE_CREDENTIAL, ca_file=certfile,
        allowed_paths=frozenset({"/v1/messages"}),
        max_requests_per_session=2,
    )
    tight_proxy, tight_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=tight),
        tmp, name="budget")
    statuses = []
    for _ in range(3):
        sock = _connect(tight_sock)
        sock.sendall(_post("/v1/messages", "h"))
        head, _ = _read_response(sock)
        statuses.append(head.split(b"\r\n", 1)[0])
        sock.close()
    check("spend ceiling: the per-session REQUEST ceiling fails closed with 429",
          b"200" in statuses[0] and b"200" in statuses[1] and b"429" in statuses[2],
          str(statuses))

    byte_capped = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=upstream.port,
        credential=FAKE_CREDENTIAL, ca_file=certfile,
        allowed_paths=frozenset({"/v1/messages"}),
        max_request_bytes_per_session=200,
    )
    byte_proxy, byte_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=byte_capped),
        tmp, name="bytes")
    big = json.dumps({"prompt": "x" * 400})
    status = _one_shot(byte_sock, _post("/v1/messages", "h", big))
    check("spend ceiling: the per-session BYTE ceiling fails closed with 429",
          b"429" in status, str(status))

    # ---- D2 (Code Review round 4): the ADVERSARIAL-CLIENT budget case the
    # tests above could not see, because they all ran from one process. The
    # budget used to be keyed on the peer's SO_PEERCRED pid, so a `fork()`
    # per request minted a fresh budget: 12 forked requests against a ceiling
    # of 5 were all forwarded upstream CREDENTIALED. A ceiling that binds only
    # a cooperative client is exactly what Red Team rejected
    # `--max-budget-usd` for, so the regression test must fork.
    forkable = egress_proxy.GatewayConfig(
        upstream_host="localhost", upstream_port=upstream.port,
        credential=FAKE_CREDENTIAL, ca_file=certfile,
        allowed_paths=frozenset({"/v1/messages"}),
        max_requests_per_session=5,
    )
    fork_proxy, fork_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow=set(), upstream_proxy=None, gateway=forkable),
        tmp, name="forkbudget")

    upstream_before = len(upstream.requests)
    read_fd, write_fd = os.pipe()
    sys.stdout.flush()
    sys.stderr.flush()
    children = []
    for _ in range(12):
        pid = os.fork()
        if pid == 0:
            # CHILD: a brand-new process — new pid, new /proc start-time —
            # doing exactly what an attacker's three lines would do. It must
            # touch nothing else and leave via os._exit so no inherited
            # buffer is flushed twice.
            code = b"ERR"
            try:
                sock = _connect(fork_sock)
                sock.sendall(_post("/v1/messages", "h"))
                head, _ = _read_response(sock)
                sock.close()
                code = head.split(b"\r\n", 1)[0].split(b" ")[1][:3]
            except Exception:
                pass
            try:
                os.write(write_fd, code.ljust(3, b" ")[:3] + b"%06d" % os.getpid())
            except OSError:
                pass
            os._exit(0)
        children.append(pid)
        os.waitpid(pid, 0)          # strictly serial, so the order is exact
    os.close(write_fd)
    raw_results = b""
    while True:
        chunk = os.read(read_fd, 4096)
        if not chunk:
            break
        raw_results += chunk
    os.close(read_fd)
    records = [raw_results[i:i + 9] for i in range(0, len(raw_results), 9)]
    codes = [rec[:3].decode("ascii").strip() for rec in records]
    child_pids = {rec[3:].decode("ascii") for rec in records}
    forwarded = len(upstream.requests) - upstream_before

    check("D2 the forking probe really did use 12 DISTINCT processes (the attack the "
          "old pid-keyed budget reset)",
          len(records) == 12 and len(child_pids) == 12,
          f"{len(records)} records, {len(child_pids)} distinct pids")
    check("D2 a fork() per request can NO LONGER reset the spend ceiling: 5 x 200 then "
          "7 x 429",
          codes[:5] == ["200"] * 5 and codes[5:] == ["429"] * 7, str(codes))
    check("D2 only the 5 permitted requests reached the upstream credentialed",
          forwarded == 5, f"{forwarded} requests forwarded upstream")
    check("D2 all 12 forked processes shared ONE budget bucket",
          len(fork_proxy._sessions) == 1, str(list(fork_proxy._sessions)))

    # The key itself: unforgeable, and containing nothing a sandbox can change.
    probe = _connect(fork_sock)
    key = egress_proxy._peer_session_key(probe)
    probe.close()
    check("D2 the budget key is the peer uid and nothing else (no pid, no start-time, "
          "no namespace id — all three are mintable inside the sandbox)",
          key == ("uid", os.getuid()), str(key))

    # And the bounded session table can no longer be used to reset a budget:
    # when every tracked bucket is exhausted, a new key is REFUSED rather than
    # granted by evicting one.
    filler = egress_proxy.EgressProxy(socket_path=str(tmp / "unused.sock"))
    for i in range(egress_proxy._MAX_TRACKED_SESSIONS):
        bucket = filler._session(("uid", 100000 + i))
        bucket.exhausted = True
    check("D2 a full session table of EXHAUSTED buckets refuses a new one rather than "
          "evicting (an eviction would be a budget reset)",
          filler._session(("uid", 999999)) is None,
          f"tracked={len(filler._sessions)}")

    # ---- the CONNECT reserve path stays live and actively denies, with the
    # gateway configured on the same socket (Red Team §3(a)).
    status = _one_shot(sock_path, b"CONNECT api.anthropic.com:443 HTTP/1.1\r\n\r\n")
    check("CONNECT reserve: api.anthropic.com:443 is DENIED 403 with the empty allowlist",
          b"403" in status, str(status))
    status = _one_shot(sock_path,
                       b"CONNECT http-intake.logs.us5.datadoghq.com:443 HTTP/1.1\r\n\r\n")
    check("CONNECT reserve: the CLI's Datadog telemetry CONNECT is DENIED 403",
          b"403" in status, str(status))
    sock = _connect(sock_path)
    sock.sendall(_post("/v1/messages", "h"))
    head, body = _read_response(sock)
    sock.close()
    check("CONNECT denials do not disturb the gateway on the same socket",
          b"200" in head and b"streamed" in body, f"{head!r}")

    # ---- a proxy with NO gateway configured must refuse non-CONNECT traffic.
    connect_only, connect_sock = _start_proxy(
        egress_proxy.AllowlistConfig(allow={("localhost", 443)}, upstream_proxy=None),
        tmp, name="connectonly")
    status = _one_shot(connect_sock, _post("/v1/messages", "h"))
    check("no gateway configured -> a non-CONNECT request is refused 403, never guessed at",
          b"403" in status, str(status))

    print()
    if FAILURES:
        print(f"{len(FAILURES)} of {_N} check(s) FAILED: {FAILURES}")
        return 1
    print(f"All {_N} checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
