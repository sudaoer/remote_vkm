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

WINDOWS_VK_TO_EVDEV: dict[int, int] = {
    0x30: 11,
    0x31: 2,
    0x32: 3,
    0x33: 4,
    0x34: 5,
    0x35: 6,
    0x36: 7,
    0x37: 8,
    0x38: 9,
    0x39: 10,
    0x41: 30,
    0x42: 48,
    0x43: 46,
    0x44: 32,
    0x45: 18,
    0x46: 33,
    0x47: 34,
    0x48: 35,
    0x49: 23,
    0x4A: 36,
    0x4B: 37,
    0x4C: 38,
    0x4D: 50,
    0x4E: 49,
    0x4F: 24,
    0x50: 25,
    0x51: 16,
    0x52: 19,
    0x53: 31,
    0x54: 20,
    0x55: 22,
    0x56: 47,
    0x57: 17,
    0x58: 45,
    0x59: 21,
    0x5A: 44,
    0x60: 82,
    0x61: 79,
    0x62: 80,
    0x63: 81,
    0x64: 75,
    0x65: 76,
    0x66: 77,
    0x67: 71,
    0x68: 72,
    0x69: 73,
    0x6A: 55,
    0x6B: 78,
    0x6D: 74,
    0x6E: 83,
    0x6F: 98,
    0xBA: 39,
    0xBB: 13,
    0xBC: 51,
    0xBD: 12,
    0xBE: 52,
    0xBF: 53,
    0xC0: 41,
    0xDB: 26,
    0xDC: 43,
    0xDD: 27,
    0xDE: 40,
}


def key_to_evdev_code(key: Key | object) -> int | None:
    if key in KEY_CODES_BY_SPECIAL:
        return KEY_CODES_BY_SPECIAL[key]  # type: ignore[index]

    vk = getattr(key, "vk", None)
    if isinstance(vk, int) and vk in WINDOWS_VK_TO_EVDEV:
        return WINDOWS_VK_TO_EVDEV[vk]

    char = getattr(key, "char", None)
    if not char:
        return None

    if len(char) != 1:
        return None

    base = SHIFTED_CHAR_TO_BASE.get(char, char.lower())
    return KEY_CODES_BY_CHAR.get(base)


def mouse_button_to_evdev_code(button: Button) -> int | None:
    return MOUSE_BUTTON_CODES.get(button)
