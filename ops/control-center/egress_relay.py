#!/usr/bin/env python3
"""ops/control-center/egress_relay.py — TASK-023 (risks.id=3 durable
closure), finding B3: the in-sandbox loopback -> Unix-socket relay.

This runs INSIDE the sandbox and is deliberately UNTRUSTED-BUT-HARMLESS
(`ops/reviews/red-team-task023-addendum-review.md`, angle 3): all egress
enforcement is 100% host-side, in `egress_proxy.py`. The sandbox has no
network route at all (`--unshare-net`), so the ONLY reachable egress is the
single bind-mounted Unix socket to the host-side proxy. Whatever the
Developer does to this relay — replace it, rewrite it — changes nothing
about what the host proxy will forward.

Why a relay at all: the Node `claude` CLI honours `HTTPS_PROXY` as a
`host:port` TCP endpoint, not a Unix socket. This relay binds the
sandbox's own loopback (`127.0.0.1`, which bwrap brings up inside the new
netns), forwards every accepted connection byte-for-byte to the
bind-mounted Unix socket, and sets `HTTPS_PROXY`/`HTTP_PROXY` to point
`claude` at itself. It parses NOTHING — it is a dumb byte forwarder; the
CONNECT request-line parsing and allow/deny decision happen host-side.

DESIGN — bind-then-fork, NOT exec-after-bind: the listening socket and its
accept loop live in THIS (parent) process; the parent forks a child that
`exec`s the real `claude` with the argv passed straight through
(sys.argv[1:]). This matters two ways:
  * Readiness: the loopback listener is bound and listening BEFORE the
    child (claude) is exec'd, so claude's first API call can never race an
    unbound port.
  * Task content is NEVER shell-interpreted: the prompt and every other
    claude argument arrive as ordinary argv elements and are passed to
    `os.execv` unchanged — no `sh -c`, no command substitution, no
    concatenation into a shell string (the wrapper's "content is data,
    never shell" discipline, cto-task023-architecture.md §4.1 step 3).

When claude exits, this parent exits with claude's exact status. The outer
`/usr/bin/timeout --signal=KILL` (in launch_developer_sandboxed.sh) and
bwrap's `--die-with-parent` handle wall-clock enforcement and teardown: if
timeout kills this process tree, the sandbox PID-namespace init exiting
reaps the relay too.

Usage (from launch_developer_sandboxed.sh, inside bwrap):
    python3 egress_relay.py <claude-bin> <claude-arg> [<claude-arg> ...]
Environment:
    EGRESS_UNIX_SOCKET   absolute path to the bind-mounted host-proxy socket
    EGRESS_RELAY_HOST    loopback bind host (default 127.0.0.1)
    EGRESS_RELAY_PORT    loopback bind port (default 8889)
"""
from __future__ import annotations

import os
import select
import socket
import sys
import threading

_RECV = 65_536
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8889


def _pump(a: socket.socket, b: socket.socket) -> None:
    socks = [a, b]
    while True:
        try:
            readable, _, _ = select.select(socks, [], [], None)
        except (OSError, ValueError):
            return
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


def _forward(inbound: socket.socket, unix_path: str) -> None:
    try:
        upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        upstream.connect(unix_path)
    except OSError:
        inbound.close()
        return
    try:
        _pump(inbound, upstream)
    finally:
        inbound.close()
        upstream.close()


def _accept_loop(server: socket.socket, unix_path: str) -> None:
    while True:
        try:
            conn, _ = server.accept()
        except OSError:
            return
        threading.Thread(target=_forward, args=(conn, unix_path), daemon=True).start()


def main() -> int:
    claude_argv = sys.argv[1:]
    if not claude_argv:
        sys.stderr.write("egress_relay: no claude argv given\n")
        return 64
    unix_path = os.environ.get("EGRESS_UNIX_SOCKET")
    if not unix_path:
        sys.stderr.write("egress_relay: EGRESS_UNIX_SOCKET is not set\n")
        return 78
    host = os.environ.get("EGRESS_RELAY_HOST", _DEFAULT_HOST)
    port = int(os.environ.get("EGRESS_RELAY_PORT", str(_DEFAULT_PORT)))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(64)  # bound + listening BEFORE the fork/exec of claude below

    pid = os.fork()
    if pid == 0:
        # Child: point claude at this relay, then exec it. The listening
        # socket belongs to the parent; close our copy here.
        server.close()
        os.environ["HTTPS_PROXY"] = f"http://{host}:{port}"
        os.environ["HTTP_PROXY"] = f"http://{host}:{port}"
        os.environ["https_proxy"] = f"http://{host}:{port}"
        os.environ["http_proxy"] = f"http://{host}:{port}"
        try:
            os.execv(claude_argv[0], claude_argv)
        except OSError as exc:
            sys.stderr.write(f"egress_relay: could not exec {claude_argv[0]!r}: {exc}\n")
            os._exit(127)

    # Parent: serve the relay until claude exits, then mirror its status.
    threading.Thread(target=_accept_loop, args=(server, unix_path), daemon=True).start()
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    raise SystemExit(main())
