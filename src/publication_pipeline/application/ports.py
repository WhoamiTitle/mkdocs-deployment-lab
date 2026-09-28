"""Ports required by publication use cases."""

from pathlib import Path
from typing import Protocol

from publication_pipeline.application.models import (
    DeploymentReceipt,
    HttpResponse,
    Release,
    SourceRevision,
)


class SourceControl(Protocol):
    def revision(self) -> SourceRevision:
        """Return the source revision represented by the working tree."""


class SiteBuilder(Protocol):
    def build(self, destination: Path) -> None:
        """Build the site into a clean destination directory."""


class ReleasePublisher(Protocol):
    def publish(self, release: Release, source: Path) -> DeploymentReceipt:
        """Atomically make a production release public."""

    def publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: str,
    ) -> DeploymentReceipt:
        """Atomically publish one branch preview."""

    def rollback(self) -> DeploymentReceipt:
        """Swap the current and previous production releases."""


class HttpClient(Protocol):
    def get(self, url: str) -> HttpResponse:
        """Fetch a text response without following application-specific rules."""
