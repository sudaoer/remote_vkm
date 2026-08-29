from __future__ import annotations

from pathlib import Path

import pytest

from remote_vkm_host import deploy as deploy_module
from remote_vkm_host.deploy import (
    AcceptNewHostKeyPolicy,
    DeploymentConfig,
    DeploymentError,
    build_parser,
    build_receiver_command,
    deploy_receiver,
    run_remote_command,
)


class FakeChannel:
    def __init__(self, exit_status: int = 0) -> None:
        self.exit_status = exit_status

    def recv_exit_status(self) -> int:
        return self.exit_status


class FakeStream:
    def __init__(self, data: bytes = b"", exit_status: int = 0) -> None:
        self.data = data
        self.channel = FakeChannel(exit_status)

    def read(self) -> bytes:
        return self.data


class FakeSftp:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, str]] = []
        self.closed = False

    def put(self, local_path: str, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))

    def close(self) -> None:
        self.closed = True


class FakeSshClient:
    def __init__(self) -> None:
        self.connect_kwargs: dict[str, object] = {}
        self.commands: list[str] = []
        self.loaded_system_keys = False
        self.loaded_host_keys: list[str] = []
        self.policy = None
        self.sftp = FakeSftp()
        self.closed = False

    def load_system_host_keys(self) -> None:
        self.loaded_system_keys = True

    def load_host_keys(self, path: str) -> None:
        self.loaded_host_keys.append(path)

    def set_missing_host_key_policy(self, policy: object) -> None:
        self.policy = policy

    def connect(self, **kwargs: object) -> None:
        self.connect_kwargs = kwargs

    def exec_command(self, command: str) -> tuple[None, FakeStream, FakeStream]:
        self.commands.append(command)
        return None, FakeStream(), FakeStream()

    def open_sftp(self) -> FakeSftp:
        return self.sftp

    def close(self) -> None:
        self.closed = True


def make_config(tmp_path: Path, *, auth: str = "password", dry_run: bool = False) -> DeploymentConfig:
    local_source = tmp_path / "main.cpp"
    local_source.write_text("int main() {}", encoding="utf-8")
    return DeploymentConfig(
        host="board.example",
        user="root",
        auth=auth,
        local_source=local_source,
        known_hosts=tmp_path / "known_hosts",
        dry_run=dry_run,
    )


def test_password_deployment_prompts_once_and_disables_key_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_client = FakeSshClient()
    prompts: list[str] = []

    monkeypatch.setattr(deploy_module.paramiko, "SSHClient", lambda: fake_client)

    def get_password(prompt: str) -> str:
        prompts.append(prompt)
        return "not-logged"

    config = make_config(tmp_path)
    deploy_receiver(config, password_getter=get_password)

    assert prompts == ["SSH password for root@board.example: "]
    assert fake_client.connect_kwargs["password"] == "not-logged"
    assert fake_client.connect_kwargs["allow_agent"] is False
    assert fake_client.connect_kwargs["look_for_keys"] is False
    assert len(fake_client.commands) == 2
    assert fake_client.sftp.uploads == [(str(config.local_source), config.remote_source)]
    assert fake_client.sftp.closed
    assert fake_client.closed
    captured = capsys.readouterr()
    assert "not-logged" not in captured.out
    assert "not-logged" not in captured.err


def test_key_deployment_does_not_request_password(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeSshClient()
    monkeypatch.setattr(deploy_module.paramiko, "SSHClient", lambda: fake_client)

    config = make_config(tmp_path, auth="key")
    deploy_receiver(config, password_getter=lambda _prompt: pytest.fail("password was requested"))

    assert fake_client.connect_kwargs["password"] is None
    assert fake_client.connect_kwargs["allow_agent"] is True
    assert fake_client.connect_kwargs["look_for_keys"] is True


def test_receiver_command_handles_root_sudo_and_dry_run(tmp_path: Path) -> None:
    command = build_receiver_command(make_config(tmp_path, dry_run=True))

    assert 'if [ "$(id -u)" -eq 0 ]; then' in command
    assert 'nohup "$receiver"' in command
    assert 'nohup sudo -n "$receiver"' in command
    assert command.count(" --dry-run") == 2


def test_accept_new_host_key_is_persisted(tmp_path: Path) -> None:
    saved: list[str] = []
    added: list[tuple[str, str, object]] = []

    class FakeHostKeys:
        def add(self, hostname: str, key_type: str, key: object) -> None:
            added.append((hostname, key_type, key))

        def save(self, path: str) -> None:
            saved.append(path)

    class FakeKey:
        def asbytes(self) -> bytes:
            return b"host-key"

        def get_name(self) -> str:
            return "ssh-ed25519"

    class FakeClient:
        def get_host_keys(self) -> FakeHostKeys:
            return FakeHostKeys()

    known_hosts = tmp_path / "nested" / "known_hosts"
    key = FakeKey()
    AcceptNewHostKeyPolicy(known_hosts).missing_host_key(FakeClient(), "board.example", key)  # type: ignore[arg-type]

    assert added == [("board.example", "ssh-ed25519", key)]
    assert saved == [str(known_hosts)]
    assert known_hosts.parent.is_dir()


def test_remote_failure_reports_exit_status(capsys: pytest.CaptureFixture[str]) -> None:
    class FailedClient:
        def exec_command(self, _command: str) -> tuple[None, FakeStream, FakeStream]:
            return None, FakeStream(b"partial output\n", 7), FakeStream(b"compiler failed\n")

    with pytest.raises(DeploymentError, match="build failed with exit status 7"):
        run_remote_command(FailedClient(), "false", "build")  # type: ignore[arg-type]

    captured = capsys.readouterr()
    assert captured.out == "partial output\n"
    assert captured.err == "compiler failed\n"


def test_deploy_cli_validates_ports() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--host", "board", "--user", "root", "--ssh-port", "0"])

    assert exc_info.value.code == 2
