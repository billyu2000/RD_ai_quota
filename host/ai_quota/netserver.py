from __future__ import annotations

import socket
import threading


class NetServer:
    """Tiny TCP server speaking the same newline-delimited JSON protocol as USB."""

    def __init__(self, port: int, on_line, on_connect=None, log=None) -> None:
        self.port = port
        self.on_line = on_line
        self.on_connect = on_connect
        self.emit = log or (lambda msg: None)
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._srv: socket.socket | None = None
        self._stopped = False

    def start(self) -> bool:
        try:
            self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._srv.bind(("", self.port))
            self._srv.listen(4)
            self._srv.settimeout(1.0)
        except OSError as exc:
            self.emit(f"ai-quota: tcp listen failed on {self.port} ({exc})")
            self._srv = None
            return False
        threading.Thread(target=self._accept_loop, daemon=True, name="ai-quota-tcp").start()
        self.emit(f"ai-quota: tcp listening on :{self.port}")
        return True

    def stop(self) -> None:
        self._stopped = True
        with self._lock:
            for conn in self._clients:
                try:
                    conn.close()
                except OSError:
                    pass
            self._clients = []
        if self._srv:
            try:
                self._srv.close()
            except OSError:
                pass

    def client_count(self) -> int:
        with self._lock:
            return len(self._clients)

    def broadcast(self, line: str) -> None:
        data = (line + "\n").encode("utf-8")
        with self._lock:
            clients = list(self._clients)
        for conn in clients:
            try:
                conn.sendall(data)
            except OSError:
                self._drop(conn)

    def _accept_loop(self) -> None:
        while not self._stopped:
            if not self._srv:
                break
            try:
                conn, addr = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn.settimeout(None)
            with self._lock:
                self._clients.append(conn)
            self.emit(f"ai-quota: wifi client {addr[0]} connected")
            if self.on_connect:
                try:
                    self.on_connect(addr)
                except Exception:
                    pass
            threading.Thread(target=self._client_loop, args=(conn, addr), daemon=True).start()

    def _client_loop(self, conn: socket.socket, addr) -> None:
        buf = b""
        try:
            while not self._stopped:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").strip()
                    if line and self.on_line:
                        try:
                            self.on_line(line)
                        except Exception:
                            pass
        except OSError:
            pass
        finally:
            self._drop(conn)
            self.emit(f"ai-quota: wifi client {addr[0]} disconnected")

    def _drop(self, conn: socket.socket) -> None:
        with self._lock:
            if conn in self._clients:
                self._clients.remove(conn)
        try:
            conn.close()
        except OSError:
            pass
