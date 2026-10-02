import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import pytest

from publication_pipeline.application.errors import RemoteExecutionError
from publication_pipeline.application.models import (
    Release,
    RsyncTransferMetrics,
    SourceRevision,
)
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
    _atomic_symlink_replacer,
    _parse_rsync_metrics,
)


class _RecordingSshGateway(SshRsyncReleaseGateway):
    def __init__(self, settings: SshRsyncSettings) -> None:
        super().__init__(settings)
        self.commands: list[str] = []
        self.capture_output = "previous-release\n"

    def _validate_local_credentials(self) -> None:
        return

    def _run_ssh_command(self, script: str) -> None:
        self.commands.append(script)

    def _capture_ssh_output(self, script: str) -> str:
        self.commands.append(script)
        return self.capture_output

    def _transfer_with_rsync(
        self,
        source: Path,
        destination: PurePosixPath,
    ) -> RsyncTransferMetrics:
        return RsyncTransferMetrics(
            duration_seconds=0.25,
            file_count=10,
            transferred_file_count=8,
            total_file_size_bytes=1000,
            transferred_file_size_bytes=800,
            sent_bytes=400,
            received_bytes=40,
        )


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
        SourceRevision(
            commit_sha=CommitSha("a" * 40),
            branch=BranchName("main"),
            dirty=False,
        ),
        built_at=UtcDatetime(datetime(2026, 1, 1, tzinfo=UTC)),
    )

    gateway.publish(release, tmp_path / "production")
    production_command = gateway.commands[-1]
    gateway.publish_preview(
        release,
        tmp_path / "preview",
        BranchSlug("feature-report-abcd1234"),
    )
    preview_command = gateway.commands[-1]
    gateway.rollback()
    rollback_command = gateway.commands[-1]

    assert 'replace_symlink_atomically "$root/current.next" "$root/current"' in (production_command)
    assert 'replace_symlink_atomically "$public.next" "$public"' in production_command
    assert 'ln -sfn "$root/current" "$public.next"' in production_command
    assert production_command.index('replace_symlink_atomically "$public.next" "$public"') < (
        production_command.index('replace_symlink_atomically "$root/current.next" "$root/current"')
    )
    assert "trap restore_production_links EXIT" in production_command
    assert "replace_symlink_atomically" in preview_command
    assert 'replace_symlink_atomically "$root/current.next" "$root/current"' in rollback_command
    assert 'replace_symlink_atomically "$root/previous.next" "$root/previous"' in rollback_command
    assert 'replace_symlink_atomically "$public.next" "$public"' in rollback_command
    assert rollback_command.index('replace_symlink_atomically "$public.next" "$public"') < (
        rollback_command.index('replace_symlink_atomically "$root/current.next" "$root/current"')
    )

    for command in (production_command, rollback_command):
        process = subprocess.run(
            ["sh", "-n", "-c", command],
            check=False,
            capture_output=True,
            text=True,
        )
        assert process.returncode == 0, process.stderr


def test_rsync_statistics_are_parsed_as_exact_bytes() -> None:
    output = """
Number of files: 131 (reg: 120, dir: 11)
Number of regular files transferred: 120
Total file size: 4,509,378 bytes
Total transferred file size: 4,509,378 bytes
Total bytes sent: 1,234,567
Total bytes received: 8,765
"""

    metrics = _parse_rsync_metrics(output, duration_seconds=1.25)

    assert metrics.duration_seconds == 1.25
    assert metrics.file_count == 131
    assert metrics.transferred_file_count == 120
    assert metrics.total_file_size_bytes == 4_509_378
    assert metrics.transferred_file_size_bytes == 4_509_378
    assert metrics.sent_bytes == 1_234_567
    assert metrics.received_bytes == 8_765


def test_rsync_statistics_accept_legacy_transferred_file_label() -> None:
    output = """
Number of files: 2
Number of files transferred: 1
Total file size: 100 bytes
Total transferred file size: 80 bytes
Total sent: 90 B
Total received: 10 B
"""

    metrics = _parse_rsync_metrics(output, duration_seconds=0.5)

    assert metrics.transferred_file_count == 1
    assert metrics.sent_bytes == 90
    assert metrics.received_bytes == 10


def test_cleanup_preview_removes_only_validated_branch_paths(tmp_path: Path) -> None:
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
    gateway.capture_output = "2\n"

    receipt = gateway.cleanup_preview(BranchSlug("feature-report-abcd1234"))

    assert receipt.branch_slug == BranchSlug("feature-report-abcd1234")
    assert receipt.removed_release_count == 2
    assert "shared-previews/feature-report-abcd1234" in gateway.commands[-1]
    assert "preview-releases/feature-report-abcd1234" in gateway.commands[-1]


def test_rollback_rejects_unsafe_remote_release_id(tmp_path: Path) -> None:
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
    gateway.capture_output = "../../escaped-release\n"

    with pytest.raises(
        RemoteExecutionError,
        match="Remote rollback returned an invalid release ID",
    ) as captured:
        gateway.rollback()

    assert isinstance(captured.value.__cause__, ValueError)
