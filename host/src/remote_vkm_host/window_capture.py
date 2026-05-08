from __future__ import annotations

import ctypes
import logging
import sys
import tkinter as tk
from dataclasses import replace

from .client import RemoteVkmClient
from .protocol import ACTION_NONE, ACTION_PRESS, ACTION_RELEASE, Frame, TYPE_BUTTON, TYPE_KEY, TYPE_REL, TYPE_WHEEL
from .tk_evdev import (
    is_deferred_modifier,
    mouse_button_to_evdev_code,
    normalize_hotkey_key,
    tk_key_to_evdev_code,
)

LOG = logging.getLogger(__name__)


class WindowForwarder:
    def __init__(self, client: RemoteVkmClient, width: int = 960, height: int = 540) -> None:
        self.client = client
        self.width = width
        self.height = height
        self.root: tk.Tk | None = None
        self.status: tk.StringVar | None = None
        self.pointer: Win32PointerCapture | None = None
        self.captured = False
        self._closed = False
        self._pressed_hotkeys: set[str] = set()
        self._pending_modifier_codes: dict[str, int] = {}
        self._remote_key_codes: dict[str, int] = {}
        self._remote_button_codes: dict[int, int] = {}
        self._suppressed_button_releases: set[int] = set()

    def run(self) -> None:
        root = tk.Tk()
        self.root = root
        self.pointer = Win32PointerCapture(root)

        root.title("remote-vkm")
        root.geometry(f"{self.width}x{self.height}")
        root.minsize(520, 300)
        root.configure(bg="#101820")
        root.protocol("WM_DELETE_WINDOW", self._close)

        self.status = tk.StringVar(value=self._idle_text())
        label = tk.Label(
            root,
            textvariable=self.status,
            bg="#101820",
            fg="#f2efe7",
            font=("Segoe UI", 16),
            justify="center",
            padx=32,
            pady=32,
        )
        label.pack(expand=True, fill="both")

        root.bind("<ButtonPress>", self._on_button_press)
        root.bind("<ButtonRelease>", self._on_button_release)
        root.bind("<Motion>", self._on_motion)
        root.bind("<MouseWheel>", self._on_mouse_wheel)
        root.bind("<Button-4>", self._on_x11_wheel)
        root.bind("<Button-5>", self._on_x11_wheel)
        root.bind("<KeyPress>", self._on_key_press)
        root.bind("<KeyRelease>", self._on_key_release)
        root.bind("<FocusOut>", self._on_focus_out)

        LOG.info("open window; click inside it to capture keyboard and mouse")
        root.mainloop()

    def _send(self, frame: Frame) -> None:
        sequence = self.client.next_sequence()
        self.client.send(replace(frame, sequence=sequence))

    def _enter_capture(self) -> None:
        if self.captured or self.root is None or self.pointer is None:
            return
        self._pressed_hotkeys.clear()
        self._pending_modifier_codes.clear()
        self.root.focus_force()
        self.root.configure(cursor="none")
        try:
            self.pointer.capture()
            self.pointer.center_cursor()
        except Exception:
            self.root.configure(cursor="")
            raise
        self.captured = True
        self._set_status(self._captured_text())
        LOG.info("input captured; press Ctrl+Alt to release")

    def _release_capture(self) -> None:
        if not self.captured:
            return
        self._release_all_remote_inputs()
        self._pressed_hotkeys.clear()
        self.captured = False
        if self.root is not None:
            self.root.configure(cursor="")
        if self.pointer is not None:
            self.pointer.release()
        self._set_status(self._idle_text())
        LOG.info("input released")

    def _release_all_remote_inputs(self) -> None:
        for code in list(self._remote_key_codes.values()):
            self._send(Frame(event_type=TYPE_KEY, action=ACTION_RELEASE, code=code))
        for code in list(self._remote_button_codes.values()):
            self._send(Frame(event_type=TYPE_BUTTON, action=ACTION_RELEASE, code=code))
        self._remote_key_codes.clear()
        self._remote_button_codes.clear()
        self._pending_modifier_codes.clear()

    def _flush_pending_modifiers(self) -> None:
        for keysym, code in list(self._pending_modifier_codes.items()):
            self._send(Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=code))
            self._remote_key_codes[keysym] = code
        self._pending_modifier_codes.clear()

    def _on_button_press(self, event: tk.Event) -> str:
        if not self.captured:
            self._suppressed_button_releases.add(int(event.num))
            self._enter_capture()
            return "break"
        code = mouse_button_to_evdev_code(int(event.num))
        if code is None:
            return "break"
        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_BUTTON, action=ACTION_PRESS, code=code))
        self._remote_button_codes[int(event.num)] = code
        return "break"

    def _on_button_release(self, event: tk.Event) -> str:
        button = int(event.num)
        if button in self._suppressed_button_releases:
            self._suppressed_button_releases.discard(button)
            return "break"
        if not self.captured:
            return "break"
        code = self._remote_button_codes.pop(button, None)
        if code is None:
            code = mouse_button_to_evdev_code(button)
        if code is not None:
            self._send(Frame(event_type=TYPE_BUTTON, action=ACTION_RELEASE, code=code))
        return "break"

    def _on_motion(self, event: tk.Event) -> str:
        if not self.captured or self.pointer is None:
            return "break"
        center_x, center_y = self.pointer.center()
        dx = int(event.x_root) - center_x
        dy = int(event.y_root) - center_y
        if dx or dy:
            self._flush_pending_modifiers()
            self._send(Frame(event_type=TYPE_REL, action=ACTION_NONE, value1=dx, value2=dy))
            self.pointer.center_cursor()
        return "break"

    def _on_mouse_wheel(self, event: tk.Event) -> str:
        if not self.captured:
            return "break"
        delta = int(event.delta)
        if delta:
            steps = delta // 120 if abs(delta) >= 120 else (1 if delta > 0 else -1)
            self._flush_pending_modifiers()
            self._send(Frame(event_type=TYPE_WHEEL, action=ACTION_NONE, value1=steps, value2=0))
        return "break"

    def _on_x11_wheel(self, event: tk.Event) -> str:
        if not self.captured:
            return "break"
        steps = 1 if int(event.num) == 4 else -1
        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_WHEEL, action=ACTION_NONE, value1=steps, value2=0))
        return "break"

    def _on_key_press(self, event: tk.Event) -> str:
        if not self.captured:
            return "break"

        normalized = normalize_hotkey_key(str(event.keysym))
        if normalized is not None:
            self._pressed_hotkeys.add(normalized)
            if {"Control", "Alt"}.issubset(self._pressed_hotkeys):
                self._release_capture()
                return "break"

        key_id = str(event.keysym)
        if key_id in self._remote_key_codes or key_id in self._pending_modifier_codes:
            return "break"

        code = tk_key_to_evdev_code(str(event.keysym), str(event.char))
        if code is None:
            LOG.warning("unmapped key press skipped: keysym=%s char=%r", event.keysym, event.char)
            return "break"

        if is_deferred_modifier(str(event.keysym)):
            self._pending_modifier_codes[key_id] = code
            return "break"

        self._flush_pending_modifiers()
        self._send(Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=code))
        self._remote_key_codes[key_id] = code
        return "break"

    def _on_key_release(self, event: tk.Event) -> str:
        normalized = normalize_hotkey_key(str(event.keysym))
        if normalized is not None:
            self._pressed_hotkeys.discard(normalized)

        if not self.captured:
            return "break"

        key_id = str(event.keysym)
        pending_code = self._pending_modifier_codes.pop(key_id, None)
        if pending_code is not None:
            return "break"

        code = self._remote_key_codes.pop(key_id, None)
        if code is None:
            code = tk_key_to_evdev_code(str(event.keysym), str(event.char))
        if code is None:
            LOG.warning("unmapped key release skipped: keysym=%s char=%r", event.keysym, event.char)
            return "break"

        self._send(Frame(event_type=TYPE_KEY, action=ACTION_RELEASE, code=code))
        return "break"

    def _on_focus_out(self, _event: tk.Event) -> None:
        self._release_capture()

    def _close(self) -> None:
        self._closed = True
        self._release_capture()
        if self.root is not None:
            self.root.destroy()

    def _set_status(self, value: str) -> None:
        if self.status is not None:
            self.status.set(value)

    @staticmethod
    def _idle_text() -> str:
        return (
            "remote-vkm\n\n"
            "Click inside this window to capture keyboard and mouse.\n"
            "The first click only enters capture mode."
        )

    @staticmethod
    def _captured_text() -> str:
        return (
            "Input captured\n\n"
            "Mouse is locked to this window and sent as relative movement.\n"
            "Press Ctrl+Alt to release capture."
        )


class Win32PointerCapture:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self._active = False
        self._user32 = ctypes.windll.user32 if sys.platform == "win32" else None

    def capture(self) -> None:
        self._active = True
        if self._user32 is None:
            return
        left, top, right, bottom = self._client_rect()
        rect = RECT(left, top, right, bottom)
        if not self._user32.ClipCursor(ctypes.byref(rect)):
            raise ctypes.WinError()

    def release(self) -> None:
        self._active = False
        if self._user32 is not None:
            self._user32.ClipCursor(None)

    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self._client_rect()
        return ((left + right) // 2, (top + bottom) // 2)

    def center_cursor(self) -> None:
        if self._user32 is None:
            return
        x, y = self.center()
        self._user32.SetCursorPos(x, y)

    def _client_rect(self) -> tuple[int, int, int, int]:
        self.root.update_idletasks()
        left = int(self.root.winfo_rootx())
        top = int(self.root.winfo_rooty())
        right = left + max(1, int(self.root.winfo_width()))
        bottom = top + max(1, int(self.root.winfo_height()))
        return left, top, right, bottom


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]
