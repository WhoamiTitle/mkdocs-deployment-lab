"""SSH/rsync adapter for publishing immutable releases on Linux and FreeBSD."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final

from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import (
    DeploymentReceipt,
    PreviewCleanupReceipt,
    Release,
    RsyncTransferMetrics,
    validate_remote_relative_path,
)

_REMOTE_ID: Final = re.compile(r"^[A-Za-z0-9._-]+$")
_REMOTE_ACCOUNT: Final = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True)
class SshRsyncSettings:
    host: str
    user: str
    port: int
    private_key: Path
    known_hosts: Path
    deployment_root: PurePosixPath
    public_path: PurePosixPath

    @classmethod
    def create(
        cls,
        *,
        host: str,
        user: str,
        port: int,
        private_key: Path,
        known_hosts: Path,
        deployment_root: str,
        public_path: str,
    ) -> SshRsyncSettings:
        if not _REMOTE_ACCOUNT.fullmatch(host) or not _REMOTE_ACCOUNT.fullmatch(user):
            raise ValueError(
                "SSH host and user may contain letters, digits, dots, dashes and underscores"
            )
        if not 1 <= port <= 65535:
            raise ValueError("SSH port must be between 1 and 65535")
        return cls(
            host=host,
            user=user,
            port=port,
            private_key=private_key,
            known_hosts=known_hosts,
            deployment_root=validate_remote_relative_path(deployment_root),
            public_path=validate_remote_relative_path(public_path),
        )


class SshRsyncReleaseGateway:
    def __init__(self, settings: SshRsyncSettings) -> None:
        self._settings = settings

    def publish(self, release: Release, source: Path) -> DeploymentReceipt:
        self._validate_local_credentials()
        _validate_remote_identifier(release.release_id, "release ID")
        staging_relative = (
            self._settings.deployment_root / "releases" / (f".staging-{release.release_id}")
        )

        self._ssh(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/releases/.staging-{release.release_id}"; '
            'mkdir -p "$root/releases" "$root/preview-releases" "$root/shared-previews"; '
            'rm -rf -- "$stage"; mkdir -p "$stage"'
        )
        transfer = self._rsync(source, staging_relative)
        self._ssh(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f"{self._home_assignment('public', self._settings.public_path)} "
            f'stage="$root/releases/.staging-{release.release_id}"; '
            f'final="$root/releases/{release.release_id}"; '
            'test -f "$stage/index.html"; test -f "$stage/release.json"; '
            'ln -s "$root/shared-previews" "$stage/previews"; '
            'test ! -e "$final"; mv "$stage" "$final"; '
            'old=$(readlink "$root/current" 2>/dev/null || true); '
            'if [ -n "$old" ]; then '
            '  ln -sfn "$old" "$root/previous.next"; '
            '  replace_symlink_atomically "$root/previous.next" "$root/previous"; '
            "fi; "
            f'ln -sfn releases/{shlex.quote(release.release_id)} "$root/current.next"; '
            'replace_symlink_atomically "$root/current.next" "$root/current"; '
            'mkdir -p "$(dirname "$public")"; '
            'ln -sfn "$final" "$public.next"; '
            'replace_symlink_atomically "$public.next" "$public"'
        )
        return DeploymentReceipt(
            release_id=release.release_id,
            location=str(self._settings.public_path),
            transfer=transfer,
        )

    def publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: str,
    ) -> DeploymentReceipt:
        self._validate_local_credentials()
        _validate_remote_identifier(release.release_id, "release ID")
        _validate_remote_identifier(branch_slug, "branch slug")
        branch_root = self._settings.deployment_root / "preview-releases" / branch_slug
        staging_relative = branch_root / f".staging-{release.release_id}"

        self._ssh(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/preview-releases/{branch_slug}/.staging-{release.release_id}"; '
            f'mkdir -p "$root/preview-releases/{branch_slug}" "$root/shared-previews"; '
            'rm -rf -- "$stage"; mkdir -p "$stage"'
        )
        transfer = self._rsync(source, staging_relative)
        self._ssh(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/preview-releases/{branch_slug}/.staging-{release.release_id}"; '
            f'final="$root/preview-releases/{branch_slug}/{release.release_id}"; '
            'test -f "$stage/index.html"; test -f "$stage/release.json"; '
            'test ! -e "$final"; mv "$stage" "$final"; '
            f"ln -sfn ../preview-releases/{branch_slug}/{release.release_id} "
            f'"$root/shared-previews/.{branch_slug}.next"; '
            f'replace_symlink_atomically "$root/shared-previews/.{branch_slug}.next" '
            f'"$root/shared-previews/{branch_slug}"'
        )
        return DeploymentReceipt(
            release_id=release.release_id,
            location=f"{self._settings.public_path}/previews/{branch_slug}",
            transfer=transfer,
        )

    def rollback(self) -> DeploymentReceipt:
        self._validate_local_credentials()
        output = self._ssh_capture(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f"{self._home_assignment('public', self._settings.public_path)} "
            'current=$(readlink "$root/current"); previous=$(readlink "$root/previous"); '
            'test -n "$current"; test -n "$previous"; '
            'ln -sfn "$previous" "$root/current.next"; '
            'replace_symlink_atomically "$root/current.next" "$root/current"; '
            'ln -sfn "$current" "$root/previous.next"; '
            'replace_symlink_atomically "$root/previous.next" "$root/previous"; '
            'target="$root/$previous"; '
            'ln -sfn "$target" "$public.next"; '
            'replace_symlink_atomically "$public.next" "$public"; '
            'basename "$previous"'
        )
        release_id = output.strip().splitlines()[-1]
        return DeploymentReceipt(release_id=release_id, location=str(self._settings.public_path))

    def cleanup_preview(self, branch_slug: str) -> PreviewCleanupReceipt:
        self._validate_local_credentials()
        _validate_remote_identifier(branch_slug, "branch slug")
        output = self._ssh_capture(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'branch="$root/preview-releases/{branch_slug}"; '
            f'link="$root/shared-previews/{branch_slug}"; '
            'if [ -e "$link" ] && [ ! -L "$link" ]; then '
            '  echo "Refusing to remove a preview path that is not a symlink" >&2; '
            "  exit 1; "
            "fi; "
            "count=0; "
            'if [ -d "$branch" ]; then '
            '  for release in "$branch"/*; do '
            '    [ -d "$release" ] || continue; count=$((count + 1)); '
            "  done; "
            "fi; "
            'rm -f -- "$link"; rm -rf -- "$branch"; printf "%s\\n" "$count"'
        )
        removed_release_count = int(output.strip().splitlines()[-1])
        return PreviewCleanupReceipt(
            branch_slug=branch_slug,
            location=f"{self._settings.public_path}/previews/{branch_slug}",
            removed_release_count=removed_release_count,
        )

    def _validate_local_credentials(self) -> None:
        if not self._settings.private_key.is_file():
            raise PublicationError(
                f"SSH private key file does not exist: {self._settings.private_key}"
            )
        if not self._settings.known_hosts.is_file():
            raise PublicationError(f"known_hosts file does not exist: {self._settings.known_hosts}")

    def _ssh_arguments(self) -> list[str]:
        return [
            "ssh",
            "-p",
            str(self._settings.port),
            "-i",
            str(self._settings.private_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self._settings.known_hosts}",
        ]

    def _ssh(self, script: str) -> None:
        subprocess.run(
            [*self._ssh_arguments(), f"{self._settings.user}@{self._settings.host}", script],
            check=True,
        )

    def _ssh_capture(self, script: str) -> str:
        process = subprocess.run(
            [*self._ssh_arguments(), f"{self._settings.user}@{self._settings.host}", script],
            check=True,
            capture_output=True,
            text=True,
        )
        return process.stdout

    def _rsync(self, source: Path, destination: PurePosixPath) -> RsyncTransferMetrics:
        ssh_transport = " ".join(shlex.quote(value) for value in self._ssh_arguments())
        remote = f"{self._settings.user}@{self._settings.host}:{destination.as_posix()}/"
        started_at = time.perf_counter()
        process = subprocess.run(
            [
                "rsync",
                "--archive",
                "--compress",
                "--delete-delay",
                "--stats",
                "-e",
                ssh_transport,
                f"{source}/",
                remote,
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "LC_ALL": "C"},
        )
        duration_seconds = time.perf_counter() - started_at
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip() or "no diagnostic output"
            raise PublicationError(f"rsync failed with exit code {process.returncode}: {detail}")
        return _parse_rsync_metrics(process.stdout, duration_seconds=duration_seconds)

    @staticmethod
    def _home_assignment(name: str, relative_path: PurePosixPath) -> str:
        return f'{name}="$HOME/{relative_path.as_posix()}";'


def _validate_remote_identifier(value: str, label: str) -> None:
    if not _REMOTE_ID.fullmatch(value):
        raise ValueError(f"Unsafe {label}: {value!r}")


def _atomic_symlink_replacer() -> str:
    """Return a fail-closed shell helper for atomic symlink replacement."""

    return (
        "remote_platform=$(uname -s); "
        "replace_symlink_atomically() { "
        'case "$remote_platform" in '
        'Linux) mv -Tf "$1" "$2" ;; '
        'FreeBSD) mv -fh "$1" "$2" ;; '
        '*) echo "Unsupported remote platform for atomic symlink replacement: '
        '$remote_platform" >&2; return 1 ;; '
        "esac; "
        "};"
    )


def _parse_rsync_metrics(output: str, *, duration_seconds: float) -> RsyncTransferMetrics:
    return RsyncTransferMetrics(
        duration_seconds=duration_seconds,
        file_count=_rsync_stat(output, "Number of files"),
        transferred_file_count=_rsync_stat(
            output,
            "Number of regular files transferred",
            fallback_label="Number of files transferred",
        ),
        total_file_size_bytes=_rsync_stat(output, "Total file size"),
        transferred_file_size_bytes=_rsync_stat(output, "Total transferred file size"),
        sent_bytes=_rsync_stat(output, "Total bytes sent"),
        received_bytes=_rsync_stat(output, "Total bytes received"),
    )


def _rsync_stat(output: str, label: str, *, fallback_label: str | None = None) -> int:
    labels = (label,) if fallback_label is None else (label, fallback_label)
    pattern = "|".join(re.escape(item) for item in labels)
    match = re.search(rf"^(?:{pattern}):\s*([0-9,]+)", output, flags=re.MULTILINE)
    if match is None:
        raise PublicationError(f"rsync output has no {label!r} statistic")
    return int(match.group(1).replace(",", ""))
