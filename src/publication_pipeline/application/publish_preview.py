"""Branch-preview publication use case."""

from dataclasses import dataclass
from pathlib import Path

from publication_pipeline.application.artifact_validation import validate_deployment_artifact
from publication_pipeline.application.models import BranchSlug, DeploymentReceipt, Release
from publication_pipeline.application.ports import PreviewPublisher


@dataclass(frozen=True, slots=True, kw_only=True)
class PublishPreviewRequest:
    release: Release
    source: Path
    branch: str


class PublishPreview:
    def __init__(self, publisher: PreviewPublisher) -> None:
        self._publisher = publisher

    def execute(self, request: PublishPreviewRequest) -> DeploymentReceipt:
        validate_deployment_artifact(request.source)
        branch_slug = BranchSlug.from_branch(request.branch)
        return self._publisher.publish_preview(request.release, request.source, branch_slug)
