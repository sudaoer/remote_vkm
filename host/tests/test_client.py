import socket

import pytest

from remote_vkm_host import client as client_module
from remote_vkm_host.__main__ import build_parser
from remote_vkm_host.client import RemoteVkmClient
from remote_vkm_host.protocol import ACTION_PRESS, TYPE_KEY, Frame, hello_frame


class FakeSocket:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.closed = False
        self.options = []
        self.sent = []

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self.options.append((level, option, value))

    def sendall(self, payload: bytes) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise OSError("simulated socket failure")
        self.sent.append(payload)

    def close(self) -> None:
        self.closed = True


def test_send_reconnects_and_resends_current_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    sockets = [FakeSocket(), FakeSocket()]
    created = []
    sleeps = []

    def create_connection(address: tuple[str, int], timeout: float) -> FakeSocket:
        created.append((address, timeout))
        return sockets.pop(0)

    monkeypatch.setattr(client_module.socket, "create_connection", create_connection)
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)

    client = RemoteVkmClient("board", 5533, timeout=2.5, reconnect_attempts=5, reconnect_delay=1.0)
    client.connect()

    first_socket = client._sock
    assert isinstance(first_socket, FakeSocket)
    first_socket.failures = 1

    frame = Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=30, sequence=1)
    client.send(frame)

    second_socket = client._sock
    assert isinstance(second_socket, FakeSocket)
    assert first_socket.closed
    assert created == [(("board", 5533), 2.5), (("board", 5533), 2.5)]
    assert sleeps == [1.0]
    assert second_socket.options == [(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)]
    assert second_socket.sent == [hello_frame().pack(), frame.pack()]


def test_send_exits_after_reconnect_attempts_are_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    sockets = [FakeSocket(), FakeSocket(failures=1), FakeSocket(failures=1)]
    sleeps = []

    def create_connection(address: tuple[str, int], timeout: float) -> FakeSocket:
        return sockets.pop(0)

    monkeypatch.setattr(client_module.socket, "create_connection", create_connection)
    monkeypatch.setattr(client_module.time, "sleep", sleeps.append)

    client = RemoteVkmClient("board", 5533, reconnect_attempts=2, reconnect_delay=0.25)
    client.connect()
    assert client._sock is not None
    client._sock.failures = 1

    frame = Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=30, sequence=1)
    with pytest.raises(ConnectionError, match="failed to reconnect after 2 attempts"):
        client.send(frame)

    assert sleeps == [0.25, 0.5]
    assert client._sock is None


def test_cli_reconnect_defaults() -> None:
    args = build_parser().parse_args(["--host", "board"])

    assert args.reconnect_attempts == 5
    assert args.reconnect_delay == 1.0
