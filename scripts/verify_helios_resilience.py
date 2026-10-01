"""Run destructive deployment checks only against the dedicated Helios sandbox."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from publication_pipeline.application.build_release import load_release
from publication_pipeline.application.errors import HealthcheckError, PublicationError
from publication_pipeline.application.models import (
    DeploymentReceipt,
    Release,
    branch_to_slug,
)
from publication_pipeline.application.verify_release import VerifyRelease
from publication_pipeline.infrastructure.git_gateway import GitGateway
from publication_pipeline.infrastructure.http_gateway import UrllibHttpGateway
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
)

_CONTROL_TEXT = "publication-site-control"
_SANDBOX_DEPLOYMENT_ROOT = PurePosixPath(".deployments/mkdocs-deployment-lab-sandbox")
_SANDBOX_PUBLIC_PATH = PurePosixPath("public_html/mkdocs-deployment-lab-sandbox")
_SANDBOX_URL_SUFFIX = "/mkdocs-deployment-lab-sandbox/"
_CLEANUP_ENV = "ALLOW_DESTRUCTIVE_TEST_CLEANUP"

ScenarioValue = str | int | float | bool


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(arguments)
    repository_root = Path(cast(str, args.repository_root)).resolve()
    output = _resolve_path(repository_root, cast(str, args.output))
    base_url = _normalized_url(cast(str, args.base_url))
    production_url = _normalized_url(cast(str, args.production_url))
    settings = SshRsyncSettings.create(
        host=cast(str, args.host),
        user=cast(str, args.user),
        port=cast(int, args.port),
        private_key=Path(cast(str, args.ssh_key)).resolve(),
        known_hosts=Path(cast(str, args.known_hosts)).resolve(),
        deployment_root=cast(str, args.deployment_root),
        public_path=cast(str, args.public_path),
    )
    _validate_sandbox_targets(settings, base_url)
    revision = GitGateway(repository_root).revision()
    if revision.dirty:
        raise PublicationError("Resilience evidence must be produced from a clean revision")
    _assert_sandbox_absent(settings)

    scenarios: list[dict[str, ScenarioValue]] = []
    gateway = SshRsyncReleaseGateway(settings)
    with tempfile.TemporaryDirectory(prefix="mkdocs-helios-resilience-") as temporary:
        temporary_root = Path(temporary)
        first_site = _build_site(repository_root, temporary_root / "first", base_url)
        first_release = load_release(first_site)
        _wait_for_distinct_release_id(first_release)
        second_site = _build_site(repository_root, temporary_root / "second", base_url)
        second_release = load_release(second_site)
        _wait_for_distinct_release_id(second_release)
        third_site = _build_site(repository_root, temporary_root / "third", base_url)
        third_release = load_release(third_site)
        _wait_for_distinct_release_id(third_release)
        invalid_site = _build_site(repository_root, temporary_root / "invalid", base_url)
        invalid_release = load_release(invalid_site)

        first_receipt = gateway.publish(first_release, first_site)
        _verify_release(base_url, first_release)
        scenarios.append(_successful_deploy("initial-deploy", first_receipt))

        second_receipt = gateway.publish(second_release, second_site)
        _verify_release(base_url, second_release)
        _assert_active_release(settings, second_release.release_id)
        scenarios.append(_successful_deploy("second-deploy", second_receipt))

        rollback_started = time.perf_counter()
        rollback_receipt = gateway.rollback()
        rollback_duration = time.perf_counter() - rollback_started
        _verify_release(base_url, first_release)
        _assert_active_release(settings, first_release.release_id)
        scenarios.append(
            {
                "name": "manual-rollback",
                "result": "success",
                "release_id": rollback_receipt.release_id,
                "duration_seconds": rollback_duration,
            }
        )

        gateway.publish(third_release, third_site)
        try:
            VerifyRelease(UrllibHttpGateway()).execute(
                base_url,
                (_CONTROL_TEXT, "deliberately-missing-healthcheck-marker"),
                attempts=1,
                delay_seconds=0,
            )
        except HealthcheckError:
            automatic_rollback_started = time.perf_counter()
            automatic_receipt = gateway.rollback()
            automatic_rollback_duration = time.perf_counter() - automatic_rollback_started
        else:
            raise AssertionError("The deliberately failing healthcheck unexpectedly succeeded")
        _verify_release(base_url, first_release)
        _assert_active_release(settings, first_release.release_id)
        scenarios.append(
            {
                "name": "automatic-rollback-after-healthcheck-failure",
                "result": "success",
                "release_id": automatic_receipt.release_id,
                "duration_seconds": automatic_rollback_duration,
            }
        )

        repeat_error = _expect_publication_failure(
            lambda: gateway.publish(first_release, first_site)
        )
        _assert_active_release(settings, first_release.release_id)
        _remove_staging_directory(settings, f".staging-{first_release.release_id}")
        scenarios.append(
            {
                "name": "repeat-identical-release",
                "result": "safe-failure",
                "active_release_id": first_release.release_id,
                "error_type": repeat_error,
            }
        )

        interrupted_stage = f".staging-interrupted-{third_release.release_id}"
        _upload_partial_staging(settings, third_site / "release.json", interrupted_stage)
        _assert_active_release(settings, first_release.release_id)
        _remove_staging_directory(settings, interrupted_stage)
        scenarios.append(
            {
                "name": "interrupted-rsync-before-switch",
                "result": "active-release-preserved",
                "active_release_id": first_release.release_id,
            }
        )

        (invalid_site / "index.html").unlink()
        invalid_error = _expect_publication_failure(
            lambda: gateway.publish(invalid_release, invalid_site)
        )
        _assert_active_release(settings, first_release.release_id)
        _verify_release(base_url, first_release)
        _remove_staging_directory(settings, f".staging-{invalid_release.release_id}")
        scenarios.append(
            {
                "name": "invalid-new-release",
                "result": "active-release-preserved",
                "active_release_id": first_release.release_id,
                "error_type": invalid_error,
            }
        )

        preview_branch = "test/helios-sandbox-cleanup"
        preview_slug = branch_to_slug(preview_branch)
        gateway.publish_preview(third_release, third_site, preview_slug)
        preview_url = urljoin(base_url, f"previews/{preview_slug}/")
        _verify_release(preview_url, third_release)
        cleanup_receipt = gateway.cleanup_preview(preview_slug)
        _verify_http_status(preview_url, expected_status=404)
        scenarios.append(
            {
                "name": "stale-preview-cleanup",
                "result": "success",
                "branch_slug": preview_slug,
                "removed_release_count": cleanup_receipt.removed_release_count,
            }
        )

        VerifyRelease(UrllibHttpGateway()).execute(
            production_url,
            (_CONTROL_TEXT,),
            attempts=3,
            delay_seconds=1,
        )
        scenarios.append(
            {
                "name": "production-site-isolation",
                "result": "success",
                "url": production_url,
            }
        )

    cleanup_requested = cast(bool, args.cleanup)
    if cleanup_requested:
        if os.getenv(_CLEANUP_ENV) != "1":
            raise PublicationError(f"Sandbox cleanup requires {_CLEANUP_ENV}=1")
        _cleanup_sandbox(settings)
        _verify_http_status(base_url, expected_status=404)

    evidence = {
        "schema_version": 1,
        "executed_at_utc": datetime.now(UTC).isoformat(),
        "commit_sha": revision.commit_sha,
        "branch": revision.branch,
        "sandbox": {
            "deployment_root": settings.deployment_root.as_posix(),
            "public_path": settings.public_path.as_posix(),
            "base_url": base_url,
            "removed_after_test": cleanup_requested,
        },
        "scenarios": scenarios,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="verify-helios-resilience")
    parser.add_argument("--repository-root", default=".")
    parser.add_argument("--host", default=os.getenv("HELIOS_HOST"), required=False)
    parser.add_argument("--user", default=os.getenv("HELIOS_USER"), required=False)
    parser.add_argument("--port", type=int, default=int(os.getenv("HELIOS_PORT", "2222")))
    parser.add_argument("--ssh-key", default=os.getenv("HELIOS_SSH_KEY_PATH"), required=False)
    parser.add_argument(
        "--known-hosts",
        default=os.getenv("HELIOS_KNOWN_HOSTS_PATH"),
        required=False,
    )
    parser.add_argument(
        "--deployment-root",
        default=_SANDBOX_DEPLOYMENT_ROOT.as_posix(),
    )
    parser.add_argument("--public-path", default=_SANDBOX_PUBLIC_PATH.as_posix())
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--production-url", required=True)
    parser.add_argument(
        "--output",
        default="evidence/logs/helios-resilience.json",
    )
    parser.add_argument("--cleanup", action="store_true")
    return parser


def _validate_sandbox_targets(settings: SshRsyncSettings, base_url: str) -> None:
    if settings.deployment_root != _SANDBOX_DEPLOYMENT_ROOT:
        raise PublicationError("Resilience checks require the dedicated sandbox deployment root")
    if settings.public_path != _SANDBOX_PUBLIC_PATH:
        raise PublicationError("Resilience checks require the dedicated sandbox public path")
    expected_url_path = f"/~{settings.user}{_SANDBOX_URL_SUFFIX}"
    if urlsplit(base_url).path != expected_url_path:
        raise PublicationError("Resilience checks require the dedicated sandbox URL")
    if not settings.private_key.is_file() or not settings.known_hosts.is_file():
        raise PublicationError("SSH credentials for the sandbox check are unavailable")


def _build_site(repository_root: Path, destination: Path, base_url: str) -> Path:
    environment = {**os.environ, "SITE_URL": base_url}
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "publication_pipeline",
            "build",
            "--repository-root",
            str(repository_root),
            "--site-dir",
            str(destination),
        ],
        cwd=repository_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise PublicationError(f"Sandbox site build failed: {process.stderr[-2000:]}")
    return destination


def _wait_for_distinct_release_id(release: Release) -> None:
    while datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") == release.built_at.strftime(
        "%Y%m%dT%H%M%SZ"
    ):
        time.sleep(0.05)


def _verify_release(base_url: str, release: Release) -> None:
    VerifyRelease(UrllibHttpGateway()).execute(
        base_url,
        (_CONTROL_TEXT, release.marker),
        attempts=5,
        delay_seconds=1,
    )


def _successful_deploy(name: str, receipt: DeploymentReceipt) -> dict[str, ScenarioValue]:
    if receipt.transfer is None:
        raise AssertionError("SSH deployment did not return rsync metrics")
    return {
        "name": name,
        "result": "success",
        "release_id": receipt.release_id,
        "rsync_duration_seconds": receipt.transfer.duration_seconds,
        "rsync_sent_bytes": receipt.transfer.sent_bytes,
        "rsync_received_bytes": receipt.transfer.received_bytes,
        "transferred_file_size_bytes": receipt.transfer.transferred_file_size_bytes,
    }


def _expect_publication_failure(action: Callable[[], DeploymentReceipt]) -> str:
    try:
        action()
    except (PublicationError, subprocess.CalledProcessError) as error:
        return type(error).__name__
    raise AssertionError("The unsafe publication unexpectedly succeeded")


def _assert_sandbox_absent(settings: SshRsyncSettings) -> None:
    root = settings.deployment_root.as_posix()
    public = settings.public_path.as_posix()
    _ssh_capture(
        settings,
        f'root="$HOME/{root}"; public="$HOME/{public}"; '
        'test ! -e "$root"; test ! -L "$public"; test ! -e "$public"; printf "clean\\n"',
    )


def _assert_active_release(settings: SshRsyncSettings, expected_release_id: str) -> None:
    root = settings.deployment_root.as_posix()
    active = _ssh_capture(
        settings,
        f'root="$HOME/{root}"; basename "$(readlink "$root/current")"',
    ).strip()
    if active != expected_release_id:
        raise AssertionError(f"Active release is {active!r}, expected {expected_release_id!r}")


def _upload_partial_staging(
    settings: SshRsyncSettings,
    release_file: Path,
    staging_name: str,
) -> None:
    root = settings.deployment_root.as_posix()
    _ssh_capture(
        settings,
        f'root="$HOME/{root}"; stage="$root/releases/{staging_name}"; '
        'test ! -e "$stage"; mkdir -p "$stage"',
    )
    ssh_transport = " ".join(shlex.quote(value) for value in _ssh_arguments(settings))
    remote = (
        f"{settings.user}@{settings.host}:"
        f"{settings.deployment_root.as_posix()}/releases/{staging_name}/"
    )
    subprocess.run(
        ["rsync", "--archive", "-e", ssh_transport, str(release_file), remote],
        check=True,
    )


def _remove_staging_directory(settings: SshRsyncSettings, staging_name: str) -> None:
    if not staging_name.startswith(".staging-") or "/" in staging_name:
        raise PublicationError(f"Unsafe staging cleanup target: {staging_name!r}")
    root = settings.deployment_root.as_posix()
    _ssh_capture(
        settings,
        f'root="$HOME/{root}"; stage="$root/releases/{staging_name}"; rm -rf -- "$stage"',
    )


def _cleanup_sandbox(settings: SshRsyncSettings) -> None:
    root = settings.deployment_root.as_posix()
    public = settings.public_path.as_posix()
    _ssh_capture(
        settings,
        f'root="$HOME/{root}"; public="$HOME/{public}"; '
        'if [ -e "$public" ] && [ ! -L "$public" ]; then '
        '  echo "Sandbox public path is not a symlink" >&2; exit 1; '
        "fi; "
        'rm -f -- "$public"; rm -rf -- "$root"; '
        'test ! -e "$root"; test ! -L "$public"; test ! -e "$public"',
    )


def _verify_http_status(url: str, *, expected_status: int) -> None:
    last_status = 0
    for attempt in range(1, 6):
        request = Request(
            f"{url}?resilience_probe={time.time_ns()}",
            headers={"Cache-Control": "no-cache", "User-Agent": "resilience-check/0.1"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                last_status = response.status
        except HTTPError as error:
            last_status = error.code
        if last_status == expected_status:
            return
        if attempt < 5:
            time.sleep(1)
    raise AssertionError(f"HTTP status for {url} is {last_status}, expected {expected_status}")


def _ssh_capture(settings: SshRsyncSettings, script: str) -> str:
    process = subprocess.run(
        [*_ssh_arguments(settings), f"{settings.user}@{settings.host}", f"set -eu; {script}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return process.stdout


def _ssh_arguments(settings: SshRsyncSettings) -> tuple[str, ...]:
    return (
        "ssh",
        "-p",
        str(settings.port),
        "-i",
        str(settings.private_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={settings.known_hosts}",
    )


def _normalized_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be absolute HTTP(S)")
    return raw_url.rstrip("/") + "/"


def _resolve_path(repository_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (repository_root / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
