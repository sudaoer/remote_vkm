from __future__ import annotations

from .evdev import KEY_CODES_BY_CHAR, SHIFTED_CHAR_TO_BASE

SPECIAL_KEYSYMS: dict[str, int] = {
    "Escape": 1,
    "BackSpace": 14,
    "Tab": 15,
    "Return": 28,
    "Control_L": 29,
    "Control_R": 97,
    "Shift_L": 42,
    "Shift_R": 54,
    "Alt_L": 56,
    "Alt_R": 100,
    "space": 57,
    "Caps_Lock": 58,
    "F1": 59,
    "F2": 60,
    "F3": 61,
    "F4": 62,
    "F5": 63,
    "F6": 64,
    "F7": 65,
    "F8": 66,
    "F9": 67,
    "F10": 68,
    "Num_Lock": 69,
    "Scroll_Lock": 70,
    "F11": 87,
    "F12": 88,
    "KP_Enter": 96,
    "Home": 102,
    "Up": 103,
    "Prior": 104,
    "Left": 105,
    "Right": 106,
    "End": 107,
    "Down": 108,
    "Next": 109,
    "Insert": 110,
    "Delete": 111,
    "Super_L": 125,
    "Super_R": 126,
}

SYMBOL_KEYSYMS: dict[str, str] = {
    "minus": "-",
    "equal": "=",
    "bracketleft": "[",
    "bracketright": "]",
    "backslash": "\\",
    "semicolon": ";",
    "apostrophe": "'",
    "quoteleft": "`",
    "comma": ",",
    "period": ".",
    "slash": "/",
}

NUMPAD_KEYSYMS: dict[str, int] = {
    "KP_0": 82,
    "KP_1": 79,
    "KP_2": 80,
    "KP_3": 81,
    "KP_4": 75,
    "KP_5": 76,
    "KP_6": 77,
    "KP_7": 71,
    "KP_8": 72,
    "KP_9": 73,
    "KP_Decimal": 83,
    "KP_Divide": 98,
    "KP_Multiply": 55,
    "KP_Subtract": 74,
    "KP_Add": 78,
}

MOUSE_BUTTON_CODES: dict[int, int] = {
    1: 0x110,
    2: 0x112,
    3: 0x111,
}


def tk_key_to_evdev_code(keysym: str, char: str | None = None) -> int | None:
    if keysym in SPECIAL_KEYSYMS:
        return SPECIAL_KEYSYMS[keysym]
    if keysym in NUMPAD_KEYSYMS:
        return NUMPAD_KEYSYMS[keysym]
    if keysym in SYMBOL_KEYSYMS:
        return KEY_CODES_BY_CHAR[SYMBOL_KEYSYMS[keysym]]

    char = char or ""
    if len(char) == 1 and char >= " ":
        return _char_to_evdev_code(char)

    if len(keysym) == 1:
        return _char_to_evdev_code(keysym)

    return None


def mouse_button_to_evdev_code(button: int) -> int | None:
    return MOUSE_BUTTON_CODES.get(button)


def normalize_hotkey_key(keysym: str) -> str | None:
    if keysym in {"Control_L", "Control_R"}:
        return "Control"
    if keysym in {"Alt_L", "Alt_R"}:
        return "Alt"
    return None


def is_deferred_modifier(keysym: str) -> bool:
    return keysym in {"Control_L", "Control_R", "Alt_L", "Alt_R"}


def _char_to_evdev_code(char: str) -> int | None:
    base = SHIFTED_CHAR_TO_BASE.get(char, char.lower())
    return KEY_CODES_BY_CHAR.get(base)
