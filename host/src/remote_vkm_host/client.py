from __future__ import annotations

import logging
import socket
import threading
from typing import Self

from .protocol import Frame, hello_frame

LOG = logging.getLogger(__name__)


class RemoteVkmClient:
    def __init__(self, host: str, port: int, timeout: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._lock = threading.Lock()
        self._sequence = 0

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def connect(self) -> None:
        LOG.info("connecting to %s:%s", self.host, self.port)
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock = sock
        self.send(hello_frame())
        LOG.info("connected")

    def close(self) -> None:
        with self._lock:
            sock = self._sock
            self._sock = None
        if sock is not None:
            sock.close()

    def next_sequence(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def send(self, frame: Frame) -> None:
        payload = frame.pack()
        with self._lock:
            if self._sock is None:
                raise RuntimeError("client is not connected")
            self._sock.sendall(payload)
