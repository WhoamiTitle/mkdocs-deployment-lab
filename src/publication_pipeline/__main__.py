"""Command-line composition root for local use and CI workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from publication_pipeline.application.build_release import BuildRelease, load_release
from publication_pipeline.application.deploy_release import DeployRelease
from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import DeploymentReceipt, branch_to_slug
from publication_pipeline.application.publish_preview import PublishPreview
from publication_pipeline.application.rollback_release import RollbackRelease
from publication_pipeline.application.verify_offline_assets import VerifyOfflineAssets
from publication_pipeline.application.verify_release import VerifyRelease
from publication_pipeline.infrastructure.git_gateway import GitGateway
from publication_pipeline.infrastructure.http_gateway import UrllibHttpGateway
from publication_pipeline.infrastructure.local_release_gateway import LocalReleaseGateway
from publication_pipeline.infrastructure.mkdocs_gateway import MkDocsGateway
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
)

_CONTROL_TEXT = "publication-site-control"


def main(arguments: list[str] | None = None) -> int:
    parser = _create_parser()
    args = parser.parse_args(arguments)
    try:
        return _execute(args)
    except (PublicationError, OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="publication-pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build a strict site artifact")
    build.add_argument("--repository-root", default=".")
    build.add_argument("--config-file", default="mkdocs.yml")
    build.add_argument("--site-dir", default="site")

    deploy_local = subparsers.add_parser("deploy-local", help="publish locally")
    _add_local_arguments(deploy_local)

    preview_local = subparsers.add_parser("preview-local", help="publish a local preview")
    _add_local_arguments(preview_local)
    preview_local.add_argument("--branch", required=True)

    rollback_local = subparsers.add_parser("rollback-local", help="rollback locally")
    rollback_local.add_argument("--state-root", required=True)
    rollback_local.add_argument("--public-path", required=True)

    deploy_ssh = subparsers.add_parser("deploy-ssh", help="publish production over SSH")
    _add_ssh_arguments(deploy_ssh, include_site=True)

    preview_ssh = subparsers.add_parser("preview-ssh", help="publish a branch preview over SSH")
    _add_ssh_arguments(preview_ssh, include_site=True)
    preview_ssh.add_argument("--branch", default=os.getenv("GITHUB_REF_NAME"), required=False)

    rollback_ssh = subparsers.add_parser("rollback-ssh", help="rollback production over SSH")
    _add_ssh_arguments(rollback_ssh, include_site=False)

    healthcheck = subparsers.add_parser("healthcheck", help="verify a published HTML page")
    healthcheck.add_argument("--url", required=True)
    healthcheck.add_argument("--release-file")
    healthcheck.add_argument("--expected-text", action="append", default=[])
    healthcheck.add_argument("--attempts", type=int, default=3)
    healthcheck.add_argument("--delay-seconds", type=float, default=2)

    offline_check = subparsers.add_parser(
        "offline-check",
        help="reject external runtime assets in a generated site",
    )
    offline_check.add_argument("--site-dir", default="site")

    slug = subparsers.add_parser("branch-slug", help="print a safe preview slug")
    slug.add_argument("--branch", required=True)
    return parser


def _add_local_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--site-dir", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--public-path", required=True)


def _add_ssh_arguments(parser: argparse.ArgumentParser, *, include_site: bool) -> None:
    if include_site:
        parser.add_argument("--site-dir", required=True)
    parser.add_argument("--host", default=os.getenv("HELIOS_HOST"))
    parser.add_argument("--user", default=os.getenv("HELIOS_USER"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HELIOS_PORT", "22")))
    parser.add_argument("--ssh-key", default=os.getenv("HELIOS_SSH_KEY_PATH"))
    parser.add_argument("--known-hosts", default=os.getenv("HELIOS_KNOWN_HOSTS_PATH"))
    parser.add_argument("--deployment-root", default=os.getenv("HELIOS_DEPLOYMENT_ROOT"))
    parser.add_argument("--public-path", default=os.getenv("HELIOS_PUBLIC_PATH"))


def _execute(args: argparse.Namespace) -> int:
    command = _required_str(args, "command")
    if command == "build":
        repository_root = Path(_required_str(args, "repository_root")).resolve()
        config_file = repository_root / _required_str(args, "config_file")
        site_dir = Path(_required_str(args, "site_dir")).resolve()
        release = BuildRelease(
            MkDocsGateway(repository_root, config_file),
            GitGateway(repository_root),
        ).execute(site_dir)
        _print_json(release.as_dict())
        return 0

    if command == "branch-slug":
        print(branch_to_slug(_required_str(args, "branch")))
        return 0

    if command == "healthcheck":
        expected_texts = [_CONTROL_TEXT, *_string_list(args, "expected_text")]
        release_file = _optional_str(args, "release_file")
        if release_file is not None:
            expected_texts.append(load_release(Path(release_file).parent).marker)
        result = VerifyRelease(UrllibHttpGateway()).execute(
            _required_str(args, "url"),
            tuple(dict.fromkeys(expected_texts)),
            attempts=_required_int(args, "attempts"),
            delay_seconds=_required_float(args, "delay_seconds"),
        )
        _print_json(
            {
                "url": result.url,
                "status_code": result.status_code,
                "attempts": result.attempts,
                "checked_texts": list(result.checked_texts),
            }
        )
        return 0

    if command == "offline-check":
        report = VerifyOfflineAssets().execute(Path(_required_str(args, "site_dir")))
        _print_json(
            {
                "scanned_html_files": report.scanned_html_files,
                "scanned_css_files": report.scanned_css_files,
                "external_assets": len(report.external_assets),
            }
        )
        return 0

    if command.endswith("-local"):
        local_gateway = LocalReleaseGateway(
            Path(_required_str(args, "state_root")),
            Path(_required_str(args, "public_path")),
        )
        if command == "rollback-local":
            _print_receipt(RollbackRelease(local_gateway).execute())
            return 0
        site_dir = Path(_required_str(args, "site_dir"))
        release = load_release(site_dir)
        if command == "deploy-local":
            _print_receipt(DeployRelease(local_gateway).execute(release, site_dir))
            return 0
        if command == "preview-local":
            _print_receipt(
                PublishPreview(local_gateway).execute(
                    release,
                    site_dir,
                    _required_str(args, "branch"),
                )
            )
            return 0

    if command.endswith("-ssh"):
        ssh_gateway = SshRsyncReleaseGateway(_ssh_settings(args))
        if command == "rollback-ssh":
            _print_receipt(RollbackRelease(ssh_gateway).execute())
            return 0
        site_dir = Path(_required_str(args, "site_dir"))
        release = load_release(site_dir)
        if command == "deploy-ssh":
            _print_receipt(DeployRelease(ssh_gateway).execute(release, site_dir))
            return 0
        if command == "preview-ssh":
            _print_receipt(
                PublishPreview(ssh_gateway).execute(
                    release,
                    site_dir,
                    _required_str(args, "branch"),
                )
            )
            return 0

    raise ValueError(f"Unknown command: {command}")


def _ssh_settings(args: argparse.Namespace) -> SshRsyncSettings:
    return SshRsyncSettings.create(
        host=_required_str(args, "host"),
        user=_required_str(args, "user"),
        port=_required_int(args, "port"),
        private_key=Path(_required_str(args, "ssh_key")),
        known_hosts=Path(_required_str(args, "known_hosts")),
        deployment_root=_required_str(args, "deployment_root"),
        public_path=_required_str(args, "public_path"),
    )


def _required_str(args: argparse.Namespace, name: str) -> str:
    value: object = getattr(args, name, None)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing required value: {name.replace('_', '-')}")
    return value


def _optional_str(args: argparse.Namespace, name: str) -> str | None:
    value: object = getattr(args, name, None)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid value: {name.replace('_', '-')}")
    return value


def _required_int(args: argparse.Namespace, name: str) -> int:
    value: object = getattr(args, name, None)
    if not isinstance(value, int):
        raise ValueError(f"Missing integer value: {name.replace('_', '-')}")
    return value


def _required_float(args: argparse.Namespace, name: str) -> float:
    value: object = getattr(args, name, None)
    if not isinstance(value, (int, float)):
        raise ValueError(f"Missing numeric value: {name.replace('_', '-')}")
    return float(value)


def _string_list(args: argparse.Namespace, name: str) -> list[str]:
    value: object = getattr(args, name, None)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Invalid list value: {name.replace('_', '-')}")
    return value


def _print_receipt(receipt: DeploymentReceipt) -> None:
    _print_json(
        {
            "release_id": receipt.release_id,
            "location": receipt.location,
            "previous_release_id": receipt.previous_release_id,
        }
    )


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
