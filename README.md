# remote-vkm

[中文版本](README.zh-CN.md)

`remote-vkm` forwards keyboard and mouse events from a Windows host to a Linux development board.

- Host: Python managed by pixi, opens a VM-style capture window by default.
- Board: C++17/CMake receiver, injects events through `/dev/uinput`.
- Transport: plain TCP on port `5533` by default.

This is intended for a trusted local network. It does not implement authentication or encryption.

## Repository Layout

```text
host/                 Python host-side capture and sender
board/                C++ receiver for the Linux development board
pixi.toml             Host-side Python environment and tasks
pyproject.toml        Python package metadata
```

## Build The Board Receiver

Copy or clone this repository on the development board, then build:

```sh
cmake -S board -B board/build
cmake --build board/build
```

For a network-only smoke test that does not inject input:

```sh
board/build/remote-vkm-receiver --listen 0.0.0.0 --port 5533 --dry-run
```

For real keyboard and mouse injection:

```sh
sudo board/build/remote-vkm-receiver --listen 0.0.0.0 --port 5533
```

The non-dry-run mode requires `/dev/uinput`. If opening `/dev/uinput` fails, run with `sudo` first; for long-term use, add a udev rule that grants the intended user access to `uinput`.

## Run The Host Client

Install the host environment and run the client from this repository on Windows:

```powershell
pixi run host --host <board-ip-or-hostname> --port 5533
```

Useful flags:

```powershell
pixi run host --host <board-ip-or-hostname> --verbose
pixi run host --host <board-ip-or-hostname> --capture global
pixi run test
```

The host target is required. The project does not assume `k1`, because this machine currently cannot resolve that SSH alias.

## Safety Controls

The default host mode opens a window:

- Click inside the window to capture keyboard and mouse.
- The first click only enters capture mode; it is not forwarded to the board.
- While captured, the cursor is hidden, locked to the window, recentered after movement, and sent as relative mouse motion.
- Press `Ctrl+Alt` to release capture, like a virtual machine console.
- Close the window or stop the console process to exit.

The legacy global hook mode is still available with `--capture global`. In that mode, `Ctrl+Alt+P` pauses/resumes forwarding and `Ctrl+Alt+Esc` exits. These safety hotkeys are consumed locally. If modifiers or mouse buttons were already sent to the board, the host sends release events before pausing/releasing/exiting to avoid stuck remote input.

## Protocol

Every message is a fixed 32-byte little-endian frame:

```text
uint32 magic      "RVKM"
uint8  version    1
uint8  type       0 hello, 1 key, 2 relative move, 3 mouse button, 4 wheel
uint8  action     0 none, 1 press, 2 release
uint8  flags      reserved
uint32 code       Linux evdev key/button code
int32  value1     dx or vertical wheel
int32  value2     dy or horizontal wheel
uint64 sequence
uint32 reserved
```

The host sends one hello frame immediately after connecting. The receiver validates magic and protocol version before accepting input events.

## Deployment Notes

If SSH to the board works, one simple workflow is:

```powershell
scp -r board <board-ip-or-hostname>:/tmp/remote-vkm-board
ssh <board-ip-or-hostname> "cmake -S /tmp/remote-vkm-board -B /tmp/remote-vkm-board/build && cmake --build /tmp/remote-vkm-board/build"
```

Then start the receiver on the board and run the host client locally.
