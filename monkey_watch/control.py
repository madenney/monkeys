"""Control inputs for monkey commands (stdin + socket)."""

from __future__ import annotations

import socketserver
import threading
from typing import Optional


class CommandDispatcher:
    def __init__(self, handler, print_lock: threading.Lock) -> None:
        self._handler = handler
        self._print_lock = print_lock

    def handle_line(self, line: str, source: str) -> str:
        response = self._handler(line, source)
        if not response:
            return "ok"
        return response

    def print_notice(self, message: str) -> None:
        with self._print_lock:
            print(message, flush=True)


def start_stdin_listener(
    dispatcher: CommandDispatcher,
    stop_event: threading.Event,
) -> threading.Thread:
    def run() -> None:
        while not stop_event.is_set():
            try:
                line = input()
            except EOFError:
                break
            except Exception:
                break
            if line is None:
                continue
            line = line.strip()
            if not line:
                continue
            response = dispatcher.handle_line(line, "stdin")
            if response not in ("ok", ""):
                dispatcher.print_notice(response)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


class _ControlHandler(socketserver.StreamRequestHandler):
    dispatcher: Optional[CommandDispatcher] = None

    def handle(self) -> None:
        if not self.dispatcher:
            return
        for raw in self.rfile:
            try:
                line = raw.decode("utf-8", errors="replace").strip()
            except Exception:
                continue
            if not line:
                continue
            response = self.dispatcher.handle_line(line, "socket")
            try:
                self.wfile.write((response + "\n").encode("utf-8"))
            except Exception:
                return


def start_control_server(
    dispatcher: CommandDispatcher,
    host: str,
    port: int,
    stop_event: threading.Event,
) -> socketserver.ThreadingTCPServer:
    _ControlHandler.dispatcher = dispatcher
    server = socketserver.ThreadingTCPServer((host, port), _ControlHandler)
    server.daemon_threads = True

    def run() -> None:
        with server:
            server.serve_forever(poll_interval=0.5)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    def shutdown() -> None:
        stop_event.wait()
        try:
            server.shutdown()
        except Exception:
            pass

    shutdown_thread = threading.Thread(target=shutdown, daemon=True)
    shutdown_thread.start()
    return server
