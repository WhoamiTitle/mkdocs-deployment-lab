from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from publication_pipeline.application.models import Release, SourceRevision
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
    _atomic_symlink_replacer,
)


class _RecordingSshGateway(SshRsyncReleaseGateway):
    def __init__(self, settings: SshRsyncSettings) -> None:
        super().__init__(settings)
        self.commands: list[str] = []

    def _validate_local_credentials(self) -> None:
        return

    def _ssh(self, script: str) -> None:
        self.commands.append(script)

    def _ssh_capture(self, script: str) -> str:
        self.commands.append(script)
        return "previous-release\n"

    def _rsync(self, source: Path, destination: PurePosixPath) -> None:
        return


@pytest.mark.parametrize(
    ("platform", "expected_arguments"),
    [
        ("Linux", "-Tf source.next target"),
        ("FreeBSD", "-fh source.next target"),
    ],
)
def test_atomic_symlink_replacer_selects_platform_command(
    platform: str,
    expected_arguments: str,
) -> None:
    shell = (
        f'uname() {{ printf "%s\\n" "{platform}"; }}; '
        'mv() { printf "%s\\n" "$*"; }; '
        f"{_atomic_symlink_replacer()} "
        "replace_symlink_atomically source.next target"
    )

    process = subprocess.run(
        ["sh", "-c", shell],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0
    assert process.stdout.strip() == expected_arguments


def test_atomic_symlink_replacer_rejects_unknown_platform() -> None:
    shell = (
        'uname() { printf "%s\\n" "Darwin"; }; '
        'mv() { printf "%s\\n" "$*"; }; '
        f"{_atomic_symlink_replacer()} "
        "replace_symlink_atomically source.next target"
    )

    process = subprocess.run(
        ["sh", "-c", shell],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 1
    assert process.stdout == ""
    assert "Unsupported remote platform" in process.stderr


def test_all_link_switches_use_platform_aware_atomic_replacer(tmp_path: Path) -> None:
    settings = SshRsyncSettings.create(
        host="helios.example.edu",
        user="student",
        port=2222,
        private_key=tmp_path / "key",
        known_hosts=tmp_path / "known_hosts",
        deployment_root=".deployments/mkdocs-deployment-lab",
        public_path="public_html/mkdocs-deployment-lab",
    )
    gateway = _RecordingSshGateway(settings)
    release = Release.create(
        SourceRevision(commit_sha="a" * 40, branch="main", dirty=False),
        built_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    gateway.publish(release, tmp_path / "production")
    production_command = gateway.commands[-1]
    gateway.publish_preview(release, tmp_path / "preview", "feature-report-abcd1234")
    preview_command = gateway.commands[-1]
    gateway.rollback()
    rollback_command = gateway.commands[-1]

    assert 'replace_symlink_atomically "$root/current.next" "$root/current"' in (production_command)
    assert 'replace_symlink_atomically "$public.next" "$public"' in production_command
    assert "replace_symlink_atomically" in preview_command
    assert 'replace_symlink_atomically "$root/current.next" "$root/current"' in rollback_command
    assert 'replace_symlink_atomically "$root/previous.next" "$root/previous"' in rollback_command
    assert 'replace_symlink_atomically "$public.next" "$public"' in rollback_command
