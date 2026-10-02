import subprocess
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from publication_pipeline.application.errors import (
    HttpClientError,
    RemoteExecutionError,
    SourceControlError,
)
from publication_pipeline.infrastructure import urllib_http_client
from publication_pipeline.infrastructure.git_source_control import GitSourceControl
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
)
from publication_pipeline.infrastructure.urllib_http_client import UrllibHttpClient


def test_git_failure_is_translated_to_source_control_error(tmp_path: Path) -> None:
    with pytest.raises(SourceControlError, match="Git command failed"):
        GitSourceControl(tmp_path).revision()


def test_http_transport_failure_is_translated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport_error = OSError("network unavailable")
    request = Mock(side_effect=transport_error)
    monkeypatch.setattr(urllib_http_client, "urlopen", request)

    with pytest.raises(HttpClientError, match="HTTP request failed") as captured:
        UrllibHttpClient().fetch("https://example.test/")

    assert captured.value.__cause__ is transport_error


def test_ssh_command_has_deadline_and_translates_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = SshRsyncReleaseGateway(_ssh_settings(tmp_path))
    timeout_error = subprocess.TimeoutExpired(cmd="ssh", timeout=60)
    run = Mock(side_effect=timeout_error)
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(RemoteExecutionError, match="SSH command exceeded") as captured:
        gateway._run_ssh_command("true")

    assert captured.value.__cause__ is timeout_error
    assert run.call_args.kwargs["timeout"] == 60


def test_rsync_has_deadline_and_translates_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = SshRsyncReleaseGateway(_ssh_settings(tmp_path))
    timeout_error = subprocess.TimeoutExpired(cmd="rsync", timeout=300)
    run = Mock(side_effect=timeout_error)
    monkeypatch.setattr(subprocess, "run", run)

    with pytest.raises(RemoteExecutionError, match="rsync exceeded") as captured:
        gateway._transfer_with_rsync(tmp_path, PurePosixPath("deployments/release"))

    assert captured.value.__cause__ is timeout_error
    assert run.call_args.kwargs["timeout"] == 300


def _ssh_settings(tmp_path: Path) -> SshRsyncSettings:
    return SshRsyncSettings.create(
        host="helios.example.edu",
        user="student",
        port=2222,
        private_key=tmp_path / "key",
        known_hosts=tmp_path / "known_hosts",
        deployment_root="deployments/mkdocs-deployment-lab",
        public_path="public_html/mkdocs-deployment-lab",
    )
