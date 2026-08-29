from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Sequence

import paramiko


class DeploymentError(RuntimeError):
    """Raised when the remote receiver deployment fails."""


@dataclass(frozen=True)
class DeploymentConfig:
    host: str
    user: str
    local_source: Path
    known_hosts: Path
    ssh_port: int = 22
    auth: str = "password"
    connect_timeout: float = 8.0
    remote_root: str = "/tmp/remote-vkm-board"
    remote_source: str = "/tmp/remote-vkm-board/src/main.cpp"
    receiver: str = "/tmp/remote-vkm-board/remote-vkm-receiver"
    remote_log: str = "/tmp/remote-vkm-board/receiver.log"
    listen: str = "0.0.0.0"
    receiver_port: int = 5533
    dry_run: bool = False


class AcceptNewHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Accept a first-seen host key and persist it for later mismatch checks."""

    def __init__(self, known_hosts: Path) -> None:
        self.known_hosts = known_hosts

    def missing_host_key(
        self,
        client: paramiko.SSHClient,
        hostname: str,
        key: paramiko.PKey,
    ) -> None:
        fingerprint = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode("ascii").rstrip("=")
        print(
            f"Accepting new SSH host key for {hostname}: {key.get_name()} SHA256:{fingerprint}",
            file=sys.stderr,
        )
        host_keys = client.get_host_keys()
        host_keys.add(hostname, key.get_name(), key)
        self.known_hosts.parent.mkdir(parents=True, exist_ok=True)
        host_keys.save(str(self.known_hosts))


def _quote(value: str | Path) -> str:
    return shlex.quote(str(value))


def build_prepare_command(config: DeploymentConfig) -> str:
    directories = {
        config.remote_root,
        str(PurePosixPath(config.remote_source).parent),
        str(PurePosixPath(config.receiver).parent),
        str(PurePosixPath(config.remote_log).parent),
    }
    quoted = " ".join(_quote(path) for path in sorted(directories))
    return f"set -eu\nmkdir -p -- {quoted}\n"


def build_receiver_command(config: DeploymentConfig) -> str:
    dry_run_arg = " --dry-run" if config.dry_run else ""
    return f"""set -eu
source_file={_quote(config.remote_source)}
receiver={_quote(config.receiver)}
log_file={_quote(config.remote_log)}
listen_addr={_quote(config.listen)}
port={config.receiver_port}

if ! command -v c++ >/dev/null 2>&1; then
    echo "required compiler 'c++' was not found on target host" >&2
    exit 2
fi

if ! command -v ss >/dev/null 2>&1; then
    echo "required command 'ss' was not found on target host" >&2
    exit 2
fi

if [ ! -f "$source_file" ]; then
    echo "source file not found: $source_file" >&2
    exit 2
fi

echo "building remote-vkm receiver with c++"
tmp_receiver="$receiver.new"
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -o "$tmp_receiver" "$source_file"
chmod +x "$tmp_receiver"
mv -f "$tmp_receiver" "$receiver"

if [ ! -x "$receiver" ]; then
    echo "receiver not found or not executable: $receiver" >&2
    exit 2
fi

if ss -ltn "sport = :$port" | grep -q LISTEN; then
    echo "remote-vkm receiver already listening on port $port"
else
    mkdir -p "$(dirname "$log_file")"
    if [ "$(id -u)" -eq 0 ]; then
        nohup "$receiver" --listen "$listen_addr" --port "$port"{dry_run_arg} > "$log_file" 2>&1 < /dev/null &
    else
        if ! command -v sudo >/dev/null 2>&1; then
            echo "receiver needs root access, but sudo was not found" >&2
            exit 2
        fi
        nohup sudo -n "$receiver" --listen "$listen_addr" --port "$port"{dry_run_arg} > "$log_file" 2>&1 < /dev/null &
    fi
    pid=$!
    sleep 0.75
    if ! kill -0 "$pid" 2>/dev/null; then
        echo "remote-vkm receiver failed to start; log follows:" >&2
        tail -n 80 "$log_file" >&2 || true
        exit 1
    fi
    echo "started remote-vkm receiver pid=$pid, log=$log_file"
fi
"""


def _decode_stream(stream: object) -> str:
    data = stream.read()  # type: ignore[attr-defined]
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def run_remote_command(client: paramiko.SSHClient, command: str, description: str) -> None:
    _stdin, stdout, stderr = client.exec_command(command)
    stdout_text = _decode_stream(stdout)
    stderr_text = _decode_stream(stderr)
    exit_status = stdout.channel.recv_exit_status()

    if stdout_text:
        print(stdout_text, end="" if stdout_text.endswith("\n") else "\n")
    if stderr_text:
        print(stderr_text, end="" if stderr_text.endswith("\n") else "\n", file=sys.stderr)
    if exit_status != 0:
        raise DeploymentError(f"{description} failed with exit status {exit_status}")


def deploy_receiver(
    config: DeploymentConfig,
    password_getter: Callable[[str], str] | None = None,
) -> None:
    if not config.local_source.is_file():
        raise DeploymentError(f"local board source was not found: {config.local_source}")

    get_password = password_getter or getpass.getpass
    password = None
    use_password = config.auth == "password"
    if use_password:
        password = get_password(f"SSH password for {config.user}@{config.host}: ")

    client = paramiko.SSHClient()
    try:
        client.load_system_host_keys()
        if config.known_hosts.is_file():
            client.load_host_keys(str(config.known_hosts))
        client.set_missing_host_key_policy(AcceptNewHostKeyPolicy(config.known_hosts))
        client.connect(
            hostname=config.host,
            port=config.ssh_port,
            username=config.user,
            password=password,
            timeout=config.connect_timeout,
            banner_timeout=config.connect_timeout,
            auth_timeout=config.connect_timeout,
            allow_agent=not use_password,
            look_for_keys=not use_password,
        )
        run_remote_command(client, build_prepare_command(config), "remote directory preparation")

        print(f"Uploading {config.local_source} to {config.host}:{config.remote_source} ...")
        sftp = client.open_sftp()
        try:
            sftp.put(str(config.local_source), config.remote_source)
        finally:
            sftp.close()

        run_remote_command(client, build_receiver_command(config), "remote receiver build/start")
    except paramiko.AuthenticationException as exc:
        raise DeploymentError(f"SSH authentication failed for {config.user}@{config.host}") from exc
    except paramiko.BadHostKeyException as exc:
        raise DeploymentError(f"SSH host key mismatch for {config.host}") from exc
    except (OSError, paramiko.SSHException) as exc:
        raise DeploymentError(f"SSH connection to {config.user}@{config.host} failed: {exc}") from exc
    finally:
        client.close()


def _port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be in range 1..65535")
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy and start the remote-vkm Linux receiver over SSH.")
    parser.add_argument("--host", required=True, help="SSH host name or IP address")
    parser.add_argument("--user", required=True, help="SSH user")
    parser.add_argument("--ssh-port", type=_port, default=22, help="SSH port")
    parser.add_argument("--auth", choices=["password", "key"], default="password", help="SSH authentication mode")
    parser.add_argument("--connect-timeout", type=float, default=8.0, help="SSH timeout in seconds")
    parser.add_argument("--known-hosts", type=Path, default=Path(".deploy_known_hosts"))
    parser.add_argument("--local-source", type=Path, default=Path("board/src/main.cpp"))
    parser.add_argument("--remote-root", default="/tmp/remote-vkm-board")
    parser.add_argument("--remote-source", default="/tmp/remote-vkm-board/src/main.cpp")
    parser.add_argument("--receiver", default="/tmp/remote-vkm-board/remote-vkm-receiver")
    parser.add_argument("--remote-log", default="/tmp/remote-vkm-board/receiver.log")
    parser.add_argument("--listen", default="0.0.0.0")
    parser.add_argument("--receiver-port", type=_port, default=5533)
    parser.add_argument("--dry-run", action="store_true", help="start the receiver without injecting input")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = DeploymentConfig(
        host=args.host,
        user=args.user,
        ssh_port=args.ssh_port,
        auth=args.auth,
        connect_timeout=args.connect_timeout,
        known_hosts=args.known_hosts.resolve(),
        local_source=args.local_source.resolve(),
        remote_root=args.remote_root,
        remote_source=args.remote_source,
        receiver=args.receiver,
        remote_log=args.remote_log,
        listen=args.listen,
        receiver_port=args.receiver_port,
        dry_run=args.dry_run,
    )

    try:
        deploy_receiver(config)
    except DeploymentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
