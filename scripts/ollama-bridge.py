"""Forward the Docker bridge address to Ollama on 127.0.0.1.

Ollama listens on 127.0.0.1:11434. The API container reaches this machine
as host.docker.internal, which is the docker0 address (172.17.0.1 here).
This process listens on that address and forwards each connection to Ollama.
"""

import socket
import sys
import threading

LISTEN = ("172.17.0.1", 11434)
TARGET = ("127.0.0.1", 11434)


def _pipe(source: socket.socket, dest: socket.socket) -> None:
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            dest.sendall(data)
    except OSError:
        pass
    finally:
        for sock, how in ((source, socket.SHUT_RD), (dest, socket.SHUT_WR)):
            try:
                sock.shutdown(how)
            except OSError:
                pass


def _handle(client: socket.socket) -> None:
    try:
        upstream = socket.create_connection(TARGET, timeout=10)
        upstream.settimeout(None)
    except OSError as exc:
        print(f"ollama bridge: upstream {exc}", flush=True)
        client.close()
        return
    threading.Thread(target=_pipe, args=(client, upstream), daemon=True).start()
    _pipe(upstream, client)
    client.close()
    upstream.close()


def main() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    print(f"ollama bridge {LISTEN[0]}:{LISTEN[1]} -> {TARGET[0]}:{TARGET[1]}", flush=True)
    while True:
        client, _addr = server.accept()
        threading.Thread(target=_handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except OSError as exc:
        print(f"ollama bridge failed: {exc}", file=sys.stderr)
        sys.exit(1)
