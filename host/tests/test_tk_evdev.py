from remote_vkm_host.tk_evdev import mouse_button_to_evdev_code, tk_key_to_evdev_code


def test_tk_letter_maps_from_keysym_when_ctrl_char_is_control_code() -> None:
    assert tk_key_to_evdev_code("c", "\x03") == 46


def test_tk_special_keys_map_to_evdev() -> None:
    assert tk_key_to_evdev_code("Return", "\r") == 28
    assert tk_key_to_evdev_code("Control_L", "") == 29
    assert tk_key_to_evdev_code("Alt_R", "") == 100


def test_tk_mouse_buttons_map_to_evdev() -> None:
    assert mouse_button_to_evdev_code(1) == 0x110
    assert mouse_button_to_evdev_code(2) == 0x112
    assert mouse_button_to_evdev_code(3) == 0x111
