"""Validation shared by release-publication use cases."""

from pathlib import Path

from publication_pipeline.application.errors import InvalidArtifactError


def validate_deployment_artifact(source: Path) -> None:
    try:
        required_files = (source / "index.html", source / "release.json")
        missing = [str(path) for path in required_files if not path.is_file()]
    except OSError as error:
        raise InvalidArtifactError(f"Cannot inspect deployment artifact: {source}") from error
    if missing:
        missing_list = ", ".join(missing)
        raise InvalidArtifactError(f"Deployment artifact is incomplete: {missing_list}")
