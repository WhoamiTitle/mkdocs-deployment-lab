"""Typed JSON documents emitted by the command-line adapter."""

import json
from typing import TypedDict

from publication_pipeline.application.deployment_document import DeploymentReceiptDocument
from publication_pipeline.application.models import (
    HealthcheckResult,
    PreviewCleanupReceipt,
    Release,
)
from publication_pipeline.application.release_document import ReleaseDocument
from publication_pipeline.application.verify_offline_assets import OfflineAssetReport


class BuildReleaseDocument(ReleaseDocument):
    duration_seconds: float
    artifact_size_bytes: int
    file_count: int


class HealthcheckDocument(TypedDict):
    url: str
    status_code: int
    attempts: int
    checked_texts: list[str]
    duration_seconds: float


class OfflineCheckDocument(TypedDict):
    scanned_html_files: int
    scanned_css_files: int
    external_assets: int


class PreviewCleanupDocument(TypedDict):
    branch_slug: str
    location: str
    removed_release_count: int


type CliDocument = (
    BuildReleaseDocument
    | DeploymentReceiptDocument
    | HealthcheckDocument
    | OfflineCheckDocument
    | PreviewCleanupDocument
)


def build_release_to_document(
    release: Release,
    *,
    duration_seconds: float,
    artifact_size_bytes: int,
    file_count: int,
) -> BuildReleaseDocument:
    return BuildReleaseDocument(
        release_id=release.release_id,
        commit_sha=release.commit_sha,
        branch=release.branch,
        built_at=release.built_at.isoformat(),
        dirty=release.dirty,
        duration_seconds=duration_seconds,
        artifact_size_bytes=artifact_size_bytes,
        file_count=file_count,
    )


def healthcheck_to_document(
    result: HealthcheckResult,
    *,
    duration_seconds: float,
) -> HealthcheckDocument:
    return HealthcheckDocument(
        url=result.url,
        status_code=result.status_code,
        attempts=result.attempts,
        checked_texts=list(result.checked_texts),
        duration_seconds=duration_seconds,
    )


def offline_check_to_document(report: OfflineAssetReport) -> OfflineCheckDocument:
    return OfflineCheckDocument(
        scanned_html_files=report.scanned_html_files,
        scanned_css_files=report.scanned_css_files,
        external_assets=len(report.external_assets),
    )


def preview_cleanup_to_document(receipt: PreviewCleanupReceipt) -> PreviewCleanupDocument:
    return PreviewCleanupDocument(
        branch_slug=receipt.branch_slug.value,
        location=receipt.location,
        removed_release_count=receipt.removed_release_count,
    )


def write_cli_document(document: CliDocument) -> None:
    print(json.dumps(document, ensure_ascii=False, indent=2))
