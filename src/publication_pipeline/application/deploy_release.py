"""Production publication use case."""

from pathlib import Path

from publication_pipeline.application.errors import InvalidArtifactError
from publication_pipeline.application.models import DeploymentReceipt, Release
from publication_pipeline.application.ports import ReleasePublisher


class DeployRelease:
    def __init__(self, publisher: ReleasePublisher) -> None:
        self._publisher = publisher

    def execute(self, release: Release, source: Path) -> DeploymentReceipt:
        _validate_artifact(source)
        return self._publisher.publish(release, source)


def _validate_artifact(source: Path) -> None:
    required_files = (source / "index.html", source / "release.json")
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        missing_list = ", ".join(missing)
        raise InvalidArtifactError(f"Deployment artifact is incomplete: {missing_list}")
