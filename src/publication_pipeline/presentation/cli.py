"""Published command-line grammar and its typed parse result."""

import argparse
import os
from dataclasses import dataclass


@dataclass(slots=True, init=False)
class ParsedCliArguments:
    """Typed representation of values produced by the CLI parser."""

    command: str
    repository_root: str
    config_file: str
    site_dir: str
    deployment_root: str
    public_path: str
    branch: str
    confirm_branch: str
    host: str
    user: str
    port: int
    ssh_key: str
    known_hosts: str
    url: str
    release_file: str | None
    expected_text: list[str]
    attempts: int
    delay_seconds: float


def parse_cli_arguments(arguments: list[str] | None = None) -> ParsedCliArguments:
    parsed_arguments = ParsedCliArguments()
    create_cli_parser().parse_args(arguments, namespace=parsed_arguments)
    return parsed_arguments


def create_cli_parser() -> argparse.ArgumentParser:
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
    _add_local_deployment_root_argument(rollback_local)
    rollback_local.add_argument("--public-path", required=True)

    cleanup_preview_local = subparsers.add_parser(
        "cleanup-preview-local",
        help="remove one local branch preview",
    )
    _add_local_deployment_root_argument(cleanup_preview_local)
    cleanup_preview_local.add_argument("--public-path", required=True)
    _add_preview_cleanup_arguments(cleanup_preview_local)

    deploy_ssh = subparsers.add_parser("deploy-ssh", help="publish production over SSH")
    _add_ssh_arguments(deploy_ssh, include_site=True)

    preview_ssh = subparsers.add_parser("preview-ssh", help="publish a branch preview over SSH")
    _add_ssh_arguments(preview_ssh, include_site=True)
    preview_ssh.add_argument("--branch", default=os.getenv("GITHUB_REF_NAME") or "")

    rollback_ssh = subparsers.add_parser("rollback-ssh", help="rollback production over SSH")
    _add_ssh_arguments(rollback_ssh, include_site=False)

    cleanup_preview_ssh = subparsers.add_parser(
        "cleanup-preview-ssh",
        help="remove one branch preview over SSH",
    )
    _add_ssh_arguments(cleanup_preview_ssh, include_site=False)
    _add_preview_cleanup_arguments(cleanup_preview_ssh)

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
    _add_local_deployment_root_argument(parser)
    parser.add_argument("--public-path", required=True)


def _add_local_deployment_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--deployment-root",
        "--state-root",
        dest="deployment_root",
        required=True,
        help="local deployment root (--state-root is retained for compatibility)",
    )


def _add_ssh_arguments(parser: argparse.ArgumentParser, *, include_site: bool) -> None:
    if include_site:
        parser.add_argument("--site-dir", required=True)
    parser.add_argument("--host", default=os.getenv("HELIOS_HOST") or "")
    parser.add_argument("--user", default=os.getenv("HELIOS_USER") or "")
    parser.add_argument("--port", type=int, default=int(os.getenv("HELIOS_PORT", "22")))
    parser.add_argument("--ssh-key", default=os.getenv("HELIOS_SSH_KEY_PATH") or "")
    parser.add_argument("--known-hosts", default=os.getenv("HELIOS_KNOWN_HOSTS_PATH") or "")
    parser.add_argument("--deployment-root", default=os.getenv("HELIOS_DEPLOYMENT_ROOT") or "")
    parser.add_argument("--public-path", default=os.getenv("HELIOS_PUBLIC_PATH") or "")


def _add_preview_cleanup_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--branch", required=True)
    parser.add_argument("--confirm-branch", required=True)
