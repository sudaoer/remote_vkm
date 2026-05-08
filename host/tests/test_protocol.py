from remote_vkm_host.protocol import ACTION_PRESS, FRAME_SIZE, TYPE_KEY, Frame, hello_frame


def test_frame_round_trip() -> None:
    frame = Frame(event_type=TYPE_KEY, action=ACTION_PRESS, code=30, value1=-1, value2=2, sequence=42)

    payload = frame.pack()

    assert len(payload) == FRAME_SIZE
    assert Frame.unpack(payload) == frame


def test_hello_frame_uses_protocol_type() -> None:
    frame = Frame.unpack(hello_frame().pack())

    assert frame.event_type == 0
    assert frame.sequence == 0
