from pynput.keyboard import Key, KeyCode
import pytest

from remote_vkm_host.capture import InputForwarder
from remote_vkm_host.protocol import ACTION_PRESS, ACTION_RELEASE, TYPE_KEY


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


def test_ctrl_alt_p_is_consumed_and_does_not_leave_remote_modifiers_pressed() -> None:
    client = FakeClient()
    forwarder = InputForwarder(client)  # type: ignore[arg-type]

    forwarder._on_key_press(Key.ctrl_l)
    forwarder._on_key_press(Key.alt_l)
    forwarder._on_key_press(KeyCode.from_char("p"))

    assert forwarder.paused
    assert client.frames == []


def test_regular_ctrl_shortcut_flushes_modifier_before_key() -> None:
    client = FakeClient()
    forwarder = InputForwarder(client)  # type: ignore[arg-type]

    forwarder._on_key_press(Key.ctrl_l)
    forwarder._on_key_press(KeyCode.from_char("c"))
    forwarder._on_key_release(KeyCode.from_char("c"))
    forwarder._on_key_release(Key.ctrl_l)

    assert [(frame.event_type, frame.action, frame.code) for frame in client.frames] == [
        (TYPE_KEY, ACTION_PRESS, 29),
        (TYPE_KEY, ACTION_PRESS, 46),
        (TYPE_KEY, ACTION_RELEASE, 46),
        (TYPE_KEY, ACTION_RELEASE, 29),
    ]


def test_unpause_hotkey_releases_are_consumed() -> None:
    client = FakeClient()
    forwarder = InputForwarder(client)  # type: ignore[arg-type]

    forwarder._on_key_press(Key.ctrl_l)
    forwarder._on_key_press(Key.alt_l)
    forwarder._on_key_press(KeyCode.from_char("p"))
    forwarder._on_key_release(KeyCode.from_char("p"))
    forwarder._on_key_release(Key.alt_l)
    forwarder._on_key_release(Key.ctrl_l)

    assert forwarder.paused
    assert client.frames == []

    forwarder._on_key_press(Key.ctrl_l)
    forwarder._on_key_press(Key.alt_l)
    forwarder._on_key_press(KeyCode.from_char("p"))
    forwarder._on_key_release(KeyCode.from_char("p"))
    forwarder._on_key_release(Key.alt_l)
    forwarder._on_key_release(Key.ctrl_l)

    assert not forwarder.paused
    assert client.frames == []


def test_connection_failure_stops_global_forwarder() -> None:
    client = FailingClient()
    forwarder = InputForwarder(client)  # type: ignore[arg-type]

    with pytest.raises(ConnectionError, match="connection gone"):
        forwarder._on_mouse_scroll(0, 0, 0, 1)

    assert forwarder.stopped
