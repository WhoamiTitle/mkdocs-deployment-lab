"""Ports required by publication use cases."""

from pathlib import Path
from typing import Protocol

from publication_pipeline.application.models import (
    DeploymentReceipt,
    HttpResponse,
    PreviewCleanupReceipt,
    Release,
    SourceRevision,
)
from publication_pipeline.application.value_objects.branch_slug import BranchSlug


class SourceControl(Protocol):
    def revision(self) -> SourceRevision:
        """Return the source revision represented by the working tree."""


class SiteBuilder(Protocol):
    def build(self, destination: Path) -> None:
        """Build the site into a clean destination directory."""


class ReleaseArtifactWriter(Protocol):
    def write(self, destination: Path, release: Release) -> None:
        """Attach release metadata to a generated site artifact."""


class ProductionReleasePublisher(Protocol):
    def publish(self, release: Release, source: Path) -> DeploymentReceipt:
        """Atomically make a production release public."""


class PreviewPublisher(Protocol):
    def publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: BranchSlug,
    ) -> DeploymentReceipt:
        """Atomically publish one branch preview."""


class ReleaseRollback(Protocol):
    def rollback(self) -> DeploymentReceipt:
        """Swap the current and previous production releases."""


class PreviewCleaner(Protocol):
    def cleanup_preview(self, branch_slug: BranchSlug) -> PreviewCleanupReceipt:
        """Remove the public link and immutable releases for one preview branch."""


class HttpClient(Protocol):
    def fetch(self, url: str) -> HttpResponse:
        """Fetch a text response without following application-specific rules."""
