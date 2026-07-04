#!/usr/bin/env python3
"""IPv6-only TCP proxy for exposing the IPv4-bound server over IPv6."""

from __future__ import annotations

import argparse
import signal
import socket
import sys
import threading
from typing import Optional


BUFFER_SIZE = 65536
stop_event = threading.Event()


def handle_signal(_signum, _frame) -> None:
    stop_event.set()


def relay(src: socket.socket, dst: socket.socket) -> None:
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def close_socket(sock: Optional[socket.socket]) -> None:
    if sock is None:
        return
    try:
        sock.close()
    except OSError:
        pass


def handle_client(client: socket.socket, addr, target_host: str, target_port: int) -> None:
    upstream: Optional[socket.socket] = None
    try:
        upstream = socket.create_connection((target_host, target_port), timeout=10)
        client.settimeout(None)
        upstream.settimeout(None)
        client_to_upstream = threading.Thread(target=relay, args=(client, upstream), daemon=True)
        upstream_to_client = threading.Thread(target=relay, args=(upstream, client), daemon=True)
        client_to_upstream.start()
        upstream_to_client.start()
        client_to_upstream.join()
        upstream_to_client.join()
    except OSError as exc:
        print(f"IPv6 proxy connection error from {addr}: {exc}", file=sys.stderr, flush=True)
    finally:
        close_socket(client)
        close_socket(upstream)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Expose an IPv4 listener through an IPv6-only TCP proxy.")
    parser.add_argument("--listen-host", default="::")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--target-host", default="127.0.0.1")
    parser.add_argument("--target-port", type=int, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    server.bind((args.listen_host, args.listen_port))
    server.listen(256)
    server.settimeout(1.0)
    print(
        f"IPv6 proxy listening=[{args.listen_host}]:{args.listen_port} "
        f"target={args.target_host}:{args.target_port}",
        flush=True,
    )

    try:
        while not stop_event.is_set():
            try:
                client, addr = server.accept()
            except socket.timeout:
                continue
            thread = threading.Thread(
                target=handle_client,
                args=(client, addr, args.target_host, args.target_port),
                daemon=True,
            )
            thread.start()
    finally:
        close_socket(server)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
