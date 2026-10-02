"""Production publication use case."""

from dataclasses import dataclass
from pathlib import Path

from publication_pipeline.application.artifact_validation import validate_deployment_artifact
from publication_pipeline.application.models import DeploymentReceipt, Release
from publication_pipeline.application.ports import ProductionReleasePublisher


@dataclass(frozen=True, slots=True, kw_only=True)
class DeployReleaseRequest:
    release: Release
    source: Path


class DeployRelease:
    def __init__(self, publisher: ProductionReleasePublisher) -> None:
        self._publisher = publisher

    def execute(self, request: DeployReleaseRequest) -> DeploymentReceipt:
        validate_deployment_artifact(request.source)
        return self._publisher.publish(request.release, request.source)
