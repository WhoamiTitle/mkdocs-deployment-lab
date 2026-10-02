"""Composition root for the publication pipeline command-line application."""

import sys
import time
from pathlib import Path

from publication_pipeline.application.build_release import BuildRelease, BuildReleaseRequest
from publication_pipeline.application.cleanup_preview import (
    CleanupPreview,
    CleanupPreviewRequest,
)
from publication_pipeline.application.deploy_release import DeployRelease, DeployReleaseRequest
from publication_pipeline.application.deployment_document import deployment_receipt_to_document
from publication_pipeline.application.errors import InvalidArtifactError, PublicationError
from publication_pipeline.application.models import DeploymentReceipt
from publication_pipeline.application.publish_preview import (
    PublishPreview,
    PublishPreviewRequest,
)
from publication_pipeline.application.rollback_release import RollbackRelease
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from publication_pipeline.application.verify_offline_assets import (
    VerifyOfflineAssets,
    VerifyOfflineAssetsRequest,
)
from publication_pipeline.application.verify_release import VerifyRelease, VerifyReleaseRequest
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from publication_pipeline.infrastructure.git_source_control import GitSourceControl
from publication_pipeline.infrastructure.local_release_gateway import LocalReleaseGateway
from publication_pipeline.infrastructure.mkdocs_site_builder import MkDocsSiteBuilder
from publication_pipeline.infrastructure.ssh_rsync_gateway import (
    SshRsyncReleaseGateway,
    SshRsyncSettings,
)
from publication_pipeline.infrastructure.urllib_http_client import UrllibHttpClient
from publication_pipeline.presentation.cli import ParsedCliArguments, parse_cli_arguments
from publication_pipeline.presentation.cli_document import (
    build_release_to_document,
    healthcheck_to_document,
    offline_check_to_document,
    preview_cleanup_to_document,
    write_cli_document,
)

_CONTROL_TEXT = "publication-site-control"


def main(arguments: list[str] | None = None) -> int:
    parsed_arguments = parse_cli_arguments(arguments)
    try:
        return _dispatch_command(parsed_arguments)
    except (PublicationError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


def _dispatch_command(arguments: ParsedCliArguments) -> int:
    if arguments.command == "build":
        return _build_release(arguments)
    if arguments.command == "branch-slug":
        print(BranchSlug.from_branch(BranchName(arguments.branch)).value)
        return 0
    if arguments.command == "healthcheck":
        return _verify_published_release(arguments)
    if arguments.command == "offline-check":
        report = VerifyOfflineAssets().execute(
            VerifyOfflineAssetsRequest(site_directory=Path(arguments.site_dir))
        )
        write_cli_document(offline_check_to_document(report))
        return 0
    if arguments.command.endswith("-local"):
        return _dispatch_local_command(arguments)
    if arguments.command.endswith("-ssh"):
        return _dispatch_ssh_command(arguments)
    raise ValueError(f"Unknown command: {arguments.command}")


def _build_release(arguments: ParsedCliArguments) -> int:
    repository_root = Path(arguments.repository_root).resolve()
    config_file = repository_root / arguments.config_file
    site_directory = Path(arguments.site_dir).resolve()
    artifact_store = FilesystemReleaseArtifactStore()
    started_at = time.perf_counter()
    release = BuildRelease(
        MkDocsSiteBuilder(repository_root, config_file),
        GitSourceControl(repository_root),
        artifact_store,
    ).execute(BuildReleaseRequest(destination=site_directory))
    artifact_size_bytes, file_count = _measure_artifact(site_directory)
    write_cli_document(
        build_release_to_document(
            release,
            duration_seconds=time.perf_counter() - started_at,
            artifact_size_bytes=artifact_size_bytes,
            file_count=file_count,
        )
    )
    return 0


def _verify_published_release(arguments: ParsedCliArguments) -> int:
    expected_texts = [_CONTROL_TEXT, *arguments.expected_text]
    if arguments.release_file is not None:
        release_store = FilesystemReleaseArtifactStore()
        expected_texts.append(release_store.read(Path(arguments.release_file).parent).marker)
    started_at = time.perf_counter()
    result = VerifyRelease(UrllibHttpClient()).execute(
        VerifyReleaseRequest(
            url=arguments.url,
            expected_texts=tuple(dict.fromkeys(expected_texts)),
            attempts=arguments.attempts,
            delay_seconds=arguments.delay_seconds,
        )
    )
    write_cli_document(
        healthcheck_to_document(
            result,
            duration_seconds=time.perf_counter() - started_at,
        )
    )
    return 0


def _dispatch_local_command(arguments: ParsedCliArguments) -> int:
    local_gateway = LocalReleaseGateway(
        Path(arguments.deployment_root),
        Path(arguments.public_path),
    )
    if arguments.command == "cleanup-preview-local":
        cleanup_receipt = CleanupPreview(local_gateway).execute(
            CleanupPreviewRequest(
                branch=arguments.branch,
                confirmed_branch=arguments.confirm_branch,
            )
        )
        write_cli_document(preview_cleanup_to_document(cleanup_receipt))
        return 0
    if arguments.command == "rollback-local":
        _write_deployment_receipt(RollbackRelease(local_gateway).execute())
        return 0

    site_directory = Path(arguments.site_dir)
    release = FilesystemReleaseArtifactStore().read(site_directory)
    if arguments.command == "deploy-local":
        deployment_receipt = DeployRelease(local_gateway).execute(
            DeployReleaseRequest(release=release, source=site_directory)
        )
        _write_deployment_receipt(deployment_receipt)
        return 0
    if arguments.command == "preview-local":
        preview_receipt = PublishPreview(local_gateway).execute(
            PublishPreviewRequest(
                release=release,
                source=site_directory,
                branch=arguments.branch,
            )
        )
        _write_deployment_receipt(preview_receipt)
        return 0
    raise ValueError(f"Unknown local command: {arguments.command}")


def _dispatch_ssh_command(arguments: ParsedCliArguments) -> int:
    ssh_gateway = SshRsyncReleaseGateway(_build_ssh_settings(arguments))
    if arguments.command == "cleanup-preview-ssh":
        cleanup_receipt = CleanupPreview(ssh_gateway).execute(
            CleanupPreviewRequest(
                branch=arguments.branch,
                confirmed_branch=arguments.confirm_branch,
            )
        )
        write_cli_document(preview_cleanup_to_document(cleanup_receipt))
        return 0
    if arguments.command == "rollback-ssh":
        _write_deployment_receipt(RollbackRelease(ssh_gateway).execute())
        return 0

    site_directory = Path(arguments.site_dir)
    release = FilesystemReleaseArtifactStore().read(site_directory)
    if arguments.command == "deploy-ssh":
        deployment_receipt = DeployRelease(ssh_gateway).execute(
            DeployReleaseRequest(release=release, source=site_directory)
        )
        _write_deployment_receipt(deployment_receipt)
        return 0
    if arguments.command == "preview-ssh":
        preview_receipt = PublishPreview(ssh_gateway).execute(
            PublishPreviewRequest(
                release=release,
                source=site_directory,
                branch=arguments.branch,
            )
        )
        _write_deployment_receipt(preview_receipt)
        return 0
    raise ValueError(f"Unknown SSH command: {arguments.command}")


def _build_ssh_settings(arguments: ParsedCliArguments) -> SshRsyncSettings:
    return SshRsyncSettings.create(
        host=arguments.host,
        user=arguments.user,
        port=arguments.port,
        private_key=Path(arguments.ssh_key),
        known_hosts=Path(arguments.known_hosts),
        deployment_root=arguments.deployment_root,
        public_path=arguments.public_path,
    )


def _write_deployment_receipt(receipt: DeploymentReceipt) -> None:
    write_cli_document(deployment_receipt_to_document(receipt))


def _measure_artifact(site_directory: Path) -> tuple[int, int]:
    try:
        files = tuple(path for path in site_directory.rglob("*") if path.is_file())
        return sum(path.stat().st_size for path in files), len(files)
    except OSError as error:
        raise InvalidArtifactError(f"Cannot measure release artifact: {site_directory}") from error
