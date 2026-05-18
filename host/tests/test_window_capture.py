from types import SimpleNamespace

from pynput.keyboard import Key, KeyCode
import pytest

from remote_vkm_host.protocol import ACTION_PRESS, ACTION_RELEASE, TYPE_KEY
from remote_vkm_host.window_capture import WindowForwarder


class FakeClient:
    def __init__(self) -> None:
        self.sequence = 0
        self.frames = []

    def next_sequence(self) -> int:
        self.sequence += 1
        return self.sequence

    def send(self, frame) -> None:
        self.frames.append(frame)


class FailingClient(FakeClient):
    def send(self, frame) -> None:
        raise ConnectionError("connection gone")


def event(**kwargs):
    return SimpleNamespace(**kwargs)


def test_first_capture_click_release_is_not_forwarded() -> None:
    client = FakeClient()
    forwarder = WindowForwarder(client)  # type: ignore[arg-type]

    forwarder._on_button_press(event(num=1))
    forwarder._on_button_release(event(num=1))

    assert client.frames == []


def test_ctrl_shortcut_flushes_modifier_in_window_mode() -> None:
    client = FakeClient()
    forwarder = WindowForwarder(client)  # type: ignore[arg-type]
    forwarder.captured = True

    forwarder._on_global_key_press(Key.ctrl_l)
    forwarder._on_global_key_press(KeyCode.from_char("c"))
    forwarder._on_global_key_release(KeyCode.from_char("c"))
    forwarder._on_global_key_release(Key.ctrl_l)

    assert [(frame.event_type, frame.action, frame.code) for frame in client.frames] == [
        (TYPE_KEY, ACTION_PRESS, 29),
        (TYPE_KEY, ACTION_PRESS, 46),
        (TYPE_KEY, ACTION_RELEASE, 46),
        (TYPE_KEY, ACTION_RELEASE, 29),
    ]


def test_ctrl_alt_requests_window_capture_release_without_forwarding_modifiers() -> None:
    client = FakeClient()
    forwarder = WindowForwarder(client)  # type: ignore[arg-type]
    forwarder.captured = True

    forwarder._on_global_key_press(Key.ctrl_l)
    forwarder._on_global_key_press(Key.alt_l)

    assert forwarder._release_requested.is_set()
    assert client.frames == []


def test_connection_failure_requests_window_close() -> None:
    client = FailingClient()
    forwarder = WindowForwarder(client)  # type: ignore[arg-type]
    forwarder.captured = True

    with pytest.raises(ConnectionError, match="connection gone"):
        forwarder._on_global_key_press(KeyCode.from_char("a"))

    assert forwarder._fatal_requested.is_set()
