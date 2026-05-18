from __future__ import annotations

import logging
import threading
from dataclasses import replace

from pynput import keyboard, mouse
from pynput.keyboard import Key

from .client import RemoteVkmClient
from .evdev import key_to_evdev_code, mouse_button_to_evdev_code
from .protocol import ACTION_NONE, ACTION_PRESS, ACTION_RELEASE, Frame, TYPE_BUTTON, TYPE_KEY, TYPE_REL, TYPE_WHEEL

LOG = logging.getLogger(__name__)


class InputForwarder:
    def __init__(self, client: RemoteVkmClient) -> None:
        self.client = client
        self._paused = threading.Event()
        self._stop = threading.Event()
        self._pressed_hotkeys: set[object] = set()
        self._suppressed_hotkey_releases: set[object] = set()
        self._pending_modifier_codes: dict[object, int] = {}
        self._remote_key_codes: dict[object, int] = {}
        self._remote_button_codes: dict[mouse.Button, int] = {}
        self._last_pos: tuple[int, int] | None = None
        self._fatal_error: Exception | None = None

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def run(self) -> None:
        LOG.info("starting input capture; Ctrl+Alt+P pauses, Ctrl+Alt+Esc exits")
        with keyboard.Listener(on_press=self._on_key_press, on_release=self._on_key_release) as keyboard_listener:
            with mouse.Listener(
                on_move=self._on_mouse_move,
                on_click=self._on_mouse_click,
                on_scroll=self._on_mouse_scroll,
            ) as mouse_listener:
                self._stop.wait()
                keyboard_listener.stop()
                mouse_listener.stop()
        if self._fatal_error is not None:
            raise self._fatal_error

    def _send(self, frame: Frame, respect_pause: bool = True) -> None:
        if respect_pause and self.paused:
            return
        sequence = self.client.next_sequence()
        try:
            self.client.send(replace(frame, sequence=sequence))
        except Exception as exc:
            self._handle_send_error(exc)
            raise

    def _handle_send_error(self, exc: Exception) -> None:
        if self._fatal_error is None:
            self._fatal_error = exc
            LOG.error("connection failed; stopping host client: %s", exc)
        self._stop.set()

    def _release_all_remote_inputs(self) -> None:
        try:
            if self._fatal_error is None:
                for code in list(self._remote_key_codes.values()):
                    self._send(Frame(event_type=TYPE_KEY, action=ACTION_RELEASE, code=code), respect_pause=False)
                for code in list(self._remote_button_codes.values()):
                    self._send(Frame(event_type=TYPE_BUTTON, action=ACTION_RELEASE, code=code), respect_pause=False)
        finally:
            self._remote_key_codes.clear()
            self._remote_button_codes.clear()
            self._pending_modifier_codes.clear()

    def _flush_pending_modifiers(self) -> None:
        if self.paused:
            self._pending_modifier_codes.clear()
            return
        for key, code in list(self._pending_modifier_codes.items()):
            self._send(Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=code))
            self._remote_key_codes[key] = code
        self._pending_modifier_codes.clear()

    def _update_hotkeys(self, key: object, pressed: bool) -> bool:
        normalized = self._normalize_hotkey_key(key)
        if normalized is None:
            return False

        if not pressed and normalized in self._suppressed_hotkey_releases:
            self._pressed_hotkeys.discard(normalized)
            self._suppressed_hotkey_releases.discard(normalized)
            return True

        if pressed:
            self._pressed_hotkeys.add(normalized)
        else:
            self._pressed_hotkeys.discard(normalized)

        ctrl_alt = Key.ctrl_l in self._pressed_hotkeys and Key.alt_l in self._pressed_hotkeys
        if pressed and ctrl_alt and normalized == Key.esc:
            LOG.info("exit hotkey pressed")
            self._suppressed_hotkey_releases.update({Key.ctrl_l, Key.alt_l, normalized})
            self._release_all_remote_inputs()
            self._stop.set()
            return True
        if pressed and ctrl_alt and normalized == KeyCodeP:
            self._suppressed_hotkey_releases.update({Key.ctrl_l, Key.alt_l, normalized})
            self._release_all_remote_inputs()
            if self.paused:
                self._paused.clear()
                LOG.info("forwarding resumed")
            else:
                self._paused.set()
                LOG.info("forwarding paused")
            return True
        return ctrl_alt and normalized in {Key.esc, KeyCodeP}

    def _on_key_press(self, key: object) -> bool | None:
        if self._update_hotkeys(key, pressed=True):
            return None
        if self.paused:
            return None

        code = key_to_evdev_code(key)
        if code is None:
            LOG.warning("unmapped key press skipped: %r", key)
            return None
        if self._is_deferred_modifier(key):
            self._pending_modifier_codes[key] = code
            return None
        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=code))
        self._remote_key_codes[key] = code
        return None

    def _on_key_release(self, key: object) -> bool | None:
        if self._update_hotkeys(key, pressed=False):
            return None
        if self.paused:
            self._pending_modifier_codes.pop(key, None)
            self._remote_key_codes.pop(key, None)
            return None

        pending_code = self._pending_modifier_codes.pop(key, None)
        if pending_code is not None:
            return None

        code = self._remote_key_codes.pop(key, None)
        if code is None:
            code = key_to_evdev_code(key)
        if code is None:
            LOG.warning("unmapped key release skipped: %r", key)
            return None
        self._send(Frame(event_type=TYPE_KEY, action=ACTION_RELEASE, code=code))
        return None

    def _on_mouse_move(self, x: int, y: int) -> None:
        current = (int(x), int(y))
        if self._last_pos is None:
            self._last_pos = current
            return

        dx = current[0] - self._last_pos[0]
        dy = current[1] - self._last_pos[1]
        self._last_pos = current
        if dx == 0 and dy == 0:
            return
        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_REL, action=ACTION_NONE, value1=dx, value2=dy))

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        self._last_pos = (int(x), int(y))
        if self.paused:
            self._remote_button_codes.pop(button, None)
            return
        code = mouse_button_to_evdev_code(button)
        if code is None:
            LOG.warning("unmapped mouse button skipped: %r", button)
            return
        if pressed:
            self._flush_pending_modifiers()
        action = ACTION_PRESS if pressed else ACTION_RELEASE
        self._send(Frame(event_type=TYPE_BUTTON, action=action, code=code))
        if pressed:
            self._remote_button_codes[button] = code
        else:
            self._remote_button_codes.pop(button, None)

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        self._last_pos = (int(x), int(y))
        if dx == 0 and dy == 0:
            return
        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_WHEEL, action=ACTION_NONE, value1=int(dy), value2=int(dx)))

    @staticmethod
    def _normalize_hotkey_key(key: object) -> Key | object | None:
        if key in {Key.ctrl_l, Key.ctrl_r}:
            return Key.ctrl_l
        if key in {Key.alt_l, Key.alt_r}:
            return Key.alt_l
        if key == Key.esc:
            return Key.esc
        char = getattr(key, "char", None)
        if char and char.lower() == "p":
            return KeyCodeP
        return None

    @staticmethod
    def _is_deferred_modifier(key: object) -> bool:
        return key in {Key.ctrl_l, Key.ctrl_r, Key.alt_l, Key.alt_r}


class _KeyCodeP:
    pass


KeyCodeP = _KeyCodeP()
