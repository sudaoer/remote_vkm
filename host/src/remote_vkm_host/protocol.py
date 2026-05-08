from __future__ import annotations

from dataclasses import dataclass
import struct

MAGIC = 0x4D4B5652  # b"RVKM" on the wire when packed little-endian.
VERSION = 1
FRAME_FORMAT = "<IBBBBIiiQI"
FRAME_SIZE = struct.calcsize(FRAME_FORMAT)

TYPE_HELLO = 0
TYPE_KEY = 1
TYPE_REL = 2
TYPE_BUTTON = 3
TYPE_WHEEL = 4

ACTION_NONE = 0
ACTION_PRESS = 1
ACTION_RELEASE = 2


@dataclass(frozen=True)
class Frame:
    event_type: int
    action: int = ACTION_NONE
    code: int = 0
    value1: int = 0
    value2: int = 0
    sequence: int = 0
    flags: int = 0
    reserved: int = 0

    def pack(self) -> bytes:
        return struct.pack(
            FRAME_FORMAT,
            MAGIC,
            VERSION,
            self.event_type,
            self.action,
            self.flags,
            self.code,
            self.value1,
            self.value2,
            self.sequence,
            self.reserved,
        )

    @classmethod
    def unpack(cls, payload: bytes) -> "Frame":
        if len(payload) != FRAME_SIZE:
            raise ValueError(f"expected {FRAME_SIZE} bytes, got {len(payload)}")

        magic, version, event_type, action, flags, code, value1, value2, sequence, reserved = struct.unpack(
            FRAME_FORMAT, payload
        )
        if magic != MAGIC:
            raise ValueError(f"bad magic: 0x{magic:08x}")
        if version != VERSION:
            raise ValueError(f"unsupported protocol version: {version}")

        return cls(
            event_type=event_type,
            action=action,
            flags=flags,
            code=code,
            value1=value1,
            value2=value2,
            sequence=sequence,
            reserved=reserved,
        )


def hello_frame() -> Frame:
    return Frame(event_type=TYPE_HELLO)
