import socket as socket_module

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


def test_send_failure_closes_socket_and_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_socket = FakeSocket()
    created = []

    def create_connection(address: tuple[str, int], timeout: float) -> FakeSocket:
        created.append((address, timeout))
        return fake_socket

    monkeypatch.setattr(client_module.socket, "create_connection", create_connection)

    client = RemoteVkmClient("board", 5533, timeout=2.5)
    client.connect()

    assert client._sock is fake_socket
    fake_socket.failures = 1

    frame = Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=30, sequence=1)
    with pytest.raises(ConnectionError, match="connection lost"):
        client.send(frame)

    assert fake_socket.closed
    assert client._sock is None
    assert created == [(("board", 5533), 2.5)]
    assert fake_socket.options == [(socket_module.IPPROTO_TCP, socket_module.TCP_NODELAY, 1)]
    assert fake_socket.sent == [hello_frame().pack()]


def test_send_without_connection_fails() -> None:
    client = RemoteVkmClient("board", 5533)
    frame = Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=30, sequence=1)

    with pytest.raises(RuntimeError, match="client is not connected"):
        client.send(frame)


def test_cli_rejects_reconnect_options() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--host", "board", "--reconnect-attempts", "5"])

    assert exc_info.value.code == 2
