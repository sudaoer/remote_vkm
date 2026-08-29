# remote-vkm

[中文版本](README.zh-CN.md)

`remote-vkm` forwards keyboard and mouse events from a Windows host to a Linux development board.

- Host: Python managed by pixi, opens a VM-style capture window by default.
- Board: C++17 receiver, injects events through `/dev/uinput`.
- Transport: plain TCP on port `5533` by default.

The SSH deployment stage uses SSH authentication and encryption. After deployment, keyboard and mouse events still use an unauthenticated, unencrypted TCP connection, so the project is intended only for a trusted local network.

## Repository Layout

```text
host/                 Python host-side capture and sender
board/                C++ receiver for the Linux development board
pixi.toml             Host-side Python environment and tasks
pyproject.toml        Python package metadata
```

## Build The Board Receiver

Copy or clone this repository on the development board, then build directly with `c++`:

```sh
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -o board/remote-vkm-receiver board/src/main.cpp
```

For a network-only smoke test that does not inject input:

```sh
board/remote-vkm-receiver --listen 0.0.0.0 --port 5533 --dry-run
```

For real keyboard and mouse injection:

```sh
sudo board/remote-vkm-receiver --listen 0.0.0.0 --port 5533
```

The non-dry-run mode requires `/dev/uinput`. If opening `/dev/uinput` fails, run with `sudo` first; for long-term use, add a udev rule that grants the intended user access to `uinput`.

## Run The Host Client

Install the host environment and run the client from this repository on Windows:

```powershell
pixi run host --host <board-ip-or-hostname> --port 5533
```

To upload, build, and start the receiver on the board, then open the local capture client:

```powershell
.\scripts\start-remote-vkm.ps1
```

The script connects to `root@192.168.31.215:22` by default and securely prompts once for the SSH password. The password exists only in the current Python process; it is not placed in command-line arguments, environment variables, the repository, or logs. New board host keys are saved in the gitignored `.deploy_known_hosts` file, while changed host keys still fail validation.

To use SSH key authentication:

```powershell
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -BoardUser sudoer -SshAuth key
```

If the event receiver address differs from the SSH address, or SSH uses a non-default port, specify them separately:

```powershell
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -SshHost 192.168.1.39 -SshPort 2222
```

To start or check only the board receiver without opening the local capture window:

```powershell
.\scripts\start-remote-vkm.ps1 -ReceiverOnly
```

Useful flags:

```powershell
pixi run host --host <board-ip-or-hostname> --verbose
pixi run host --host <board-ip-or-hostname> --capture global
pixi run test
```

The `host` argument remains required when invoking `pixi run host` directly; the deployment script uses the default board address described above.

## Safety Controls

The default host mode opens a window:

- Click inside the window to capture keyboard and mouse.
- The first click only enters capture mode; it is not forwarded to the board.
- While captured, the cursor is hidden, locked to the window, recentered after movement, and sent as relative mouse motion.
- Keyboard capture uses a low-level hook while captured, suppresses local key delivery, and maps Windows virtual-key codes before text characters, so active IMEs do not transform the forwarded key events.
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

If SSH to the board works, one simple manual workflow is:

```powershell
ssh <board-ip-or-hostname> "mkdir -p /tmp/remote-vkm-board/src"
scp board/src/main.cpp <board-ip-or-hostname>:/tmp/remote-vkm-board/src/main.cpp
ssh <board-ip-or-hostname> "c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -o /tmp/remote-vkm-board/remote-vkm-receiver /tmp/remote-vkm-board/src/main.cpp"
```

Then start the receiver on the board and run the host client locally.
