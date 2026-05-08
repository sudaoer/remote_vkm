from types import SimpleNamespace

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

    forwarder._on_key_press(event(keysym="Control_L", char=""))
    forwarder._on_key_press(event(keysym="c", char="\x03"))
    forwarder._on_key_release(event(keysym="c", char="\x03"))
    forwarder._on_key_release(event(keysym="Control_L", char=""))

    assert [(frame.event_type, frame.action, frame.code) for frame in client.frames] == [
        (TYPE_KEY, ACTION_PRESS, 29),
        (TYPE_KEY, ACTION_PRESS, 46),
        (TYPE_KEY, ACTION_RELEASE, 46),
        (TYPE_KEY, ACTION_RELEASE, 29),
    ]
