"""SSH/rsync adapter for publishing immutable releases on Linux and FreeBSD."""

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, Self

from publication_pipeline.application.errors import RemoteExecutionError
from publication_pipeline.application.models import (
    BranchSlug,
    DeploymentReceipt,
    PreviewCleanupReceipt,
    Release,
    RsyncTransferMetrics,
    validate_remote_relative_path,
)

_REMOTE_ID: Final = re.compile(r"^[A-Za-z0-9._-]+$")
_REMOTE_ACCOUNT: Final = re.compile(r"^[A-Za-z0-9._-]+$")
_SSH_CONNECT_TIMEOUT_SECONDS: Final = 15
_SSH_COMMAND_TIMEOUT_SECONDS: Final = 60
_RSYNC_TIMEOUT_SECONDS: Final = 300


@dataclass(frozen=True, slots=True, kw_only=True)
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
    ) -> Self:
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

        self._run_ssh_command(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/releases/.staging-{release.release_id}"; '
            'mkdir -p "$root/releases" "$root/preview-releases" "$root/shared-previews"; '
            'rm -rf -- "$stage"; mkdir -p "$stage"'
        )
        transfer = self._transfer_with_rsync(source, staging_relative)
        self._run_ssh_command(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f"{self._home_assignment('public', self._settings.public_path)} "
            f"{_production_link_transaction_guard()} "
            f'stage="$root/releases/.staging-{release.release_id}"; '
            f'final="$root/releases/{release.release_id}"; '
            'test -f "$stage/index.html"; test -f "$stage/release.json"; '
            'ln -s "$root/shared-previews" "$stage/previews"; '
            'test ! -e "$final"; mv "$stage" "$final"; '
            'if [ -n "$old_current" ]; then '
            '  ln -sfn "$old_current" "$root/previous.next"; '
            '  replace_symlink_atomically "$root/previous.next" "$root/previous"; '
            "fi; "
            'mkdir -p "$(dirname "$public")"; '
            'ln -sfn "$root/current" "$public.next"; '
            'replace_symlink_atomically "$public.next" "$public"; '
            f'ln -sfn releases/{shlex.quote(release.release_id)} "$root/current.next"; '
            'replace_symlink_atomically "$root/current.next" "$root/current"; '
            "transaction_committed=1; trap - EXIT"
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
        branch_slug: BranchSlug,
    ) -> DeploymentReceipt:
        slug = branch_slug.value
        self._validate_local_credentials()
        _validate_remote_identifier(release.release_id, "release ID")
        branch_root = self._settings.deployment_root / "preview-releases" / slug
        staging_relative = branch_root / f".staging-{release.release_id}"

        self._run_ssh_command(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/preview-releases/{slug}/.staging-{release.release_id}"; '
            f'mkdir -p "$root/preview-releases/{slug}" "$root/shared-previews"; '
            'rm -rf -- "$stage"; mkdir -p "$stage"'
        )
        transfer = self._transfer_with_rsync(source, staging_relative)
        self._run_ssh_command(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f'stage="$root/preview-releases/{slug}/.staging-{release.release_id}"; '
            f'final="$root/preview-releases/{slug}/{release.release_id}"; '
            'test -f "$stage/index.html"; test -f "$stage/release.json"; '
            'test ! -e "$final"; mv "$stage" "$final"; '
            f"ln -sfn ../preview-releases/{slug}/{release.release_id} "
            f'"$root/shared-previews/.{slug}.next"; '
            f'replace_symlink_atomically "$root/shared-previews/.{slug}.next" '
            f'"$root/shared-previews/{slug}"'
        )
        return DeploymentReceipt(
            release_id=release.release_id,
            location=f"{self._settings.public_path}/previews/{slug}",
            transfer=transfer,
        )

    def rollback(self) -> DeploymentReceipt:
        self._validate_local_credentials()
        output = self._capture_ssh_output(
            f"set -eu; {_atomic_symlink_replacer()} "
            f"{self._home_assignment('root', self._settings.deployment_root)} "
            f"{self._home_assignment('public', self._settings.public_path)} "
            f"{_production_link_transaction_guard()} "
            'test -n "$old_current"; test -n "$old_previous"; '
            "release_id=${old_previous##*/}; "
            'ln -sfn "$root/current" "$public.next"; '
            'replace_symlink_atomically "$public.next" "$public"; '
            'ln -sfn "$old_current" "$root/previous.next"; '
            'replace_symlink_atomically "$root/previous.next" "$root/previous"; '
            'ln -sfn "$old_previous" "$root/current.next"; '
            'replace_symlink_atomically "$root/current.next" "$root/current"; '
            'transaction_committed=1; trap - EXIT; printf "%s\\n" "$release_id"'
        )
        release_id = _last_output_line(output, "rollback release ID")
        _validate_remote_identifier(release_id, "release ID")
        return DeploymentReceipt(release_id=release_id, location=str(self._settings.public_path))

    def cleanup_preview(self, branch_slug: BranchSlug) -> PreviewCleanupReceipt:
        slug = branch_slug.value
        self._validate_local_credentials()
        output = self._capture_ssh_output(
            f"set -eu; {self._home_assignment('root', self._settings.deployment_root)} "
            f'branch="$root/preview-releases/{slug}"; '
            f'link="$root/shared-previews/{slug}"; '
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
        count_text = _last_output_line(output, "preview cleanup count")
        try:
            removed_release_count = int(count_text)
        except ValueError as error:
            raise RemoteExecutionError(
                f"Remote preview cleanup returned an invalid count: {count_text!r}"
            ) from error
        return PreviewCleanupReceipt(
            branch_slug=branch_slug,
            location=f"{self._settings.public_path}/previews/{slug}",
            removed_release_count=removed_release_count,
        )

    def _validate_local_credentials(self) -> None:
        if not self._settings.private_key.is_file():
            raise RemoteExecutionError(
                f"SSH private key file does not exist: {self._settings.private_key}"
            )
        if not self._settings.known_hosts.is_file():
            raise RemoteExecutionError(
                f"known_hosts file does not exist: {self._settings.known_hosts}"
            )

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
            "-o",
            f"ConnectTimeout={_SSH_CONNECT_TIMEOUT_SECONDS}",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
        ]

    def _run_ssh_command(self, script: str) -> None:
        command = [
            *self._ssh_arguments(),
            f"{self._settings.user}@{self._settings.host}",
            script,
        ]
        process = _run_remote_process(command, timeout_seconds=_SSH_COMMAND_TIMEOUT_SECONDS)
        if process.returncode != 0:
            raise RemoteExecutionError(_process_failure_message("SSH command", process))

    def _capture_ssh_output(self, script: str) -> str:
        command = [
            *self._ssh_arguments(),
            f"{self._settings.user}@{self._settings.host}",
            script,
        ]
        process = _run_remote_process(command, timeout_seconds=_SSH_COMMAND_TIMEOUT_SECONDS)
        if process.returncode != 0:
            raise RemoteExecutionError(_process_failure_message("SSH command", process))
        return process.stdout

    def _transfer_with_rsync(
        self,
        source: Path,
        destination: PurePosixPath,
    ) -> RsyncTransferMetrics:
        ssh_transport = " ".join(shlex.quote(value) for value in self._ssh_arguments())
        remote = f"{self._settings.user}@{self._settings.host}:{destination.as_posix()}/"
        started_at = time.perf_counter()
        command = [
            "rsync",
            "--archive",
            "--compress",
            "--delete-delay",
            "--stats",
            "-e",
            ssh_transport,
            f"{source}/",
            remote,
        ]
        try:
            process = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                env={**os.environ, "LC_ALL": "C"},
                timeout=_RSYNC_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise RemoteExecutionError(
                f"rsync exceeded {_RSYNC_TIMEOUT_SECONDS} seconds"
            ) from error
        except OSError as error:
            raise RemoteExecutionError("Could not start rsync") from error
        duration_seconds = time.perf_counter() - started_at
        if process.returncode != 0:
            raise RemoteExecutionError(_process_failure_message("rsync", process))
        return _parse_rsync_metrics(process.stdout, duration_seconds=duration_seconds)

    @staticmethod
    def _home_assignment(name: str, relative_path: PurePosixPath) -> str:
        return f'{name}="$HOME/{relative_path.as_posix()}";'


def _run_remote_process(
    command: list[str],
    *,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise RemoteExecutionError(f"SSH command exceeded {timeout_seconds} seconds") from error
    except OSError as error:
        raise RemoteExecutionError("Could not start SSH command") from error


def _process_failure_message(
    operation: str,
    process: subprocess.CompletedProcess[str],
) -> str:
    detail = process.stderr.strip() or process.stdout.strip() or "no diagnostic output"
    return f"{operation} failed with exit code {process.returncode}: {detail}"


def _last_output_line(output: str, label: str) -> str:
    lines = output.strip().splitlines()
    if not lines:
        raise RemoteExecutionError(f"Remote command returned no {label}")
    return lines[-1]


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


def _production_link_transaction_guard() -> str:
    """Return shell setup that restores production links before commit."""

    return (
        'if [ -e "$public" ] && [ ! -L "$public" ]; then '
        '  echo "Refusing to replace a public path that is not a symlink" >&2; exit 1; '
        "fi; "
        'old_current=$(readlink "$root/current" 2>/dev/null || true); '
        'old_previous=$(readlink "$root/previous" 2>/dev/null || true); '
        'old_public=$(readlink "$public" 2>/dev/null || true); '
        "transaction_committed=0; "
        "restore_symlink() { "
        '  restore_target="$1"; restore_link="$2"; '
        '  if [ -n "$restore_target" ]; then '
        '    ln -sfn "$restore_target" "$restore_link.restore"; '
        '    replace_symlink_atomically "$restore_link.restore" "$restore_link"; '
        "  else "
        '    rm -f -- "$restore_link"; '
        "  fi; "
        "}; "
        "restore_production_links() { "
        "  transaction_status=$?; trap - EXIT; "
        '  if [ "$transaction_committed" -eq 0 ]; then '
        "    set +e; "
        '    restore_symlink "$old_current" "$root/current"; '
        '    restore_symlink "$old_previous" "$root/previous"; '
        '    restore_symlink "$old_public" "$public"; '
        "  fi; "
        '  exit "$transaction_status"; '
        "}; "
        "trap restore_production_links EXIT;"
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
        sent_bytes=_rsync_stat(output, "Total bytes sent", fallback_label="Total sent"),
        received_bytes=_rsync_stat(
            output,
            "Total bytes received",
            fallback_label="Total received",
        ),
    )


def _rsync_stat(output: str, label: str, *, fallback_label: str | None = None) -> int:
    labels = (label,) if fallback_label is None else (label, fallback_label)
    pattern = "|".join(re.escape(item) for item in labels)
    match = re.search(rf"^(?:{pattern}):\s*([0-9,]+)", output, flags=re.MULTILINE)
    if match is None:
        raise RemoteExecutionError(f"rsync output has no {label!r} statistic")
    return int(match.group(1).replace(",", ""))
