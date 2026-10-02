"""Filesystem adapter for generated release metadata and HTML markers."""

import html
import json
from pathlib import Path

from publication_pipeline.application.errors import InvalidArtifactError
from publication_pipeline.application.models import Release
from publication_pipeline.application.release_document import (
    JsonValue,
    release_from_document,
    release_to_document,
)

_RELEASE_FILE_NAME = "release.json"


class FilesystemReleaseArtifactStore:
    """Persist and load the published metadata contract in a site directory."""

    def write(self, destination: Path, release: Release) -> None:
        index_path = destination / "index.html"
        if not index_path.is_file():
            raise InvalidArtifactError(f"Generated site has no root index: {index_path}")
        try:
            document = index_path.read_text(encoding="utf-8")
            if "</head>" not in document:
                raise InvalidArtifactError(
                    f"Root HTML document has no closing head tag: {index_path}"
                )
            marker = html.escape(release.marker, quote=True)
            commit_sha = html.escape(release.commit_sha.value, quote=True)
            metadata = (
                f'<meta name="deployment-commit" content="{commit_sha}">\n<!-- {marker} -->\n'
            )
            index_path.write_text(
                document.replace("</head>", metadata + "</head>", 1),
                encoding="utf-8",
            )
            (destination / _RELEASE_FILE_NAME).write_text(
                json.dumps(release_to_document(release), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except InvalidArtifactError:
            raise
        except OSError as error:
            raise InvalidArtifactError(f"Cannot prepare release artifact: {destination}") from error

    def read(self, artifact_directory: Path) -> Release:
        release_path = artifact_directory / _RELEASE_FILE_NAME
        if not release_path.is_file():
            raise InvalidArtifactError(
                f"Artifact has no {_RELEASE_FILE_NAME}: {artifact_directory}"
            )
        try:
            raw_value: JsonValue = json.loads(release_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InvalidArtifactError(f"Cannot read release metadata: {release_path}") from error
        try:
            return release_from_document(raw_value)
        except (TypeError, ValueError) as error:
            raise InvalidArtifactError(f"Invalid release metadata: {release_path}") from error
