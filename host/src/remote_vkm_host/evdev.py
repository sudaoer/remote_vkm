from __future__ import annotations

from pynput.keyboard import Key
from pynput.mouse import Button

# Linux input-event-codes.h values used by the receiver.
KEY_CODES_BY_CHAR: dict[str, int] = {
    "1": 2,
    "2": 3,
    "3": 4,
    "4": 5,
    "5": 6,
    "6": 7,
    "7": 8,
    "8": 9,
    "9": 10,
    "0": 11,
    "-": 12,
    "=": 13,
    "q": 16,
    "w": 17,
    "e": 18,
    "r": 19,
    "t": 20,
    "y": 21,
    "u": 22,
    "i": 23,
    "o": 24,
    "p": 25,
    "[": 26,
    "]": 27,
    "\n": 28,
    "a": 30,
    "s": 31,
    "d": 32,
    "f": 33,
    "g": 34,
    "h": 35,
    "j": 36,
    "k": 37,
    "l": 38,
    ";": 39,
    "'": 40,
    "`": 41,
    "\\": 43,
    "z": 44,
    "x": 45,
    "c": 46,
    "v": 47,
    "b": 48,
    "n": 49,
    "m": 50,
    ",": 51,
    ".": 52,
    "/": 53,
    " ": 57,
}

SHIFTED_CHAR_TO_BASE: dict[str, str] = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
    "_": "-",
    "+": "=",
    "{": "[",
    "}": "]",
    "|": "\\",
    ":": ";",
    '"': "'",
    "~": "`",
    "<": ",",
    ">": ".",
    "?": "/",
}

KEY_CODES_BY_SPECIAL: dict[Key, int] = {
    Key.esc: 1,
    Key.backspace: 14,
    Key.tab: 15,
    Key.enter: 28,
    Key.ctrl_l: 29,
    Key.ctrl_r: 97,
    Key.shift_l: 42,
    Key.shift_r: 54,
    Key.alt_l: 56,
    Key.alt_r: 100,
    Key.space: 57,
    Key.caps_lock: 58,
    Key.f1: 59,
    Key.f2: 60,
    Key.f3: 61,
    Key.f4: 62,
    Key.f5: 63,
    Key.f6: 64,
    Key.f7: 65,
    Key.f8: 66,
    Key.f9: 67,
    Key.f10: 68,
    Key.num_lock: 69,
    Key.scroll_lock: 70,
    Key.home: 102,
    Key.up: 103,
    Key.page_up: 104,
    Key.left: 105,
    Key.right: 106,
    Key.end: 107,
    Key.down: 108,
    Key.page_down: 109,
    Key.insert: 110,
    Key.delete: 111,
    Key.f11: 87,
    Key.f12: 88,
}

try:
    KEY_CODES_BY_SPECIAL[Key.cmd_l] = 125
    KEY_CODES_BY_SPECIAL[Key.cmd_r] = 126
except AttributeError:
    pass

MOUSE_BUTTON_CODES: dict[Button, int] = {
    Button.left: 0x110,
    Button.right: 0x111,
    Button.middle: 0x112,
}


def key_to_evdev_code(key: Key | object) -> int | None:
    if key in KEY_CODES_BY_SPECIAL:
        return KEY_CODES_BY_SPECIAL[key]  # type: ignore[index]

    char = getattr(key, "char", None)
    if not char:
        return None

    if len(char) != 1:
        return None

    base = SHIFTED_CHAR_TO_BASE.get(char, char.lower())
    return KEY_CODES_BY_CHAR.get(base)


def mouse_button_to_evdev_code(button: Button) -> int | None:
    return MOUSE_BUTTON_CODES.get(button)
