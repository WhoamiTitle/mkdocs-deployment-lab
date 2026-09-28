"""Branch-preview publication use case."""

from pathlib import Path

from publication_pipeline.application.deploy_release import _validate_artifact
from publication_pipeline.application.models import DeploymentReceipt, Release, branch_to_slug
from publication_pipeline.application.ports import ReleasePublisher


class PublishPreview:
    def __init__(self, publisher: ReleasePublisher) -> None:
        self._publisher = publisher

    def execute(self, release: Release, source: Path, branch: str) -> DeploymentReceipt:
        _validate_artifact(source)
        branch_slug = branch_to_slug(branch)
        return self._publisher.publish_preview(release, source, branch_slug)
