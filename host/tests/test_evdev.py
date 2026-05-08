from pynput.keyboard import Key, KeyCode
from pynput.mouse import Button

from remote_vkm_host.evdev import key_to_evdev_code, mouse_button_to_evdev_code


def test_letter_key_maps_to_linux_evdev_code() -> None:
    assert key_to_evdev_code(KeyCode.from_char("a")) == 30
    assert key_to_evdev_code(KeyCode.from_char("A")) == 30


def test_shifted_symbol_maps_to_base_key() -> None:
    assert key_to_evdev_code(KeyCode.from_char("!")) == 2
    assert key_to_evdev_code(KeyCode.from_char("?")) == 53


def test_special_key_maps_to_linux_evdev_code() -> None:
    assert key_to_evdev_code(Key.enter) == 28
    assert key_to_evdev_code(Key.esc) == 1


def test_mouse_button_maps_to_linux_evdev_code() -> None:
    assert mouse_button_to_evdev_code(Button.left) == 0x110
    assert mouse_button_to_evdev_code(Button.right) == 0x111
