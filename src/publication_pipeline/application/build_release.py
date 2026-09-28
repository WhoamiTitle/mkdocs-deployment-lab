"""Build a static site and attach reproducibility metadata."""

from __future__ import annotations

import html
import json
from pathlib import Path

from publication_pipeline.application.errors import InvalidArtifactError
from publication_pipeline.application.models import Release
from publication_pipeline.application.ports import SiteBuilder, SourceControl

_RELEASE_FILE = "release.json"


class BuildRelease:
    def __init__(self, site_builder: SiteBuilder, source_control: SourceControl) -> None:
        self._site_builder = site_builder
        self._source_control = source_control

    def execute(self, destination: Path) -> Release:
        release = Release.create(self._source_control.revision())
        self._site_builder.build(destination)
        index_path = destination / "index.html"
        if not index_path.is_file():
            raise InvalidArtifactError(f"Generated site has no root index: {index_path}")

        _inject_release_marker(index_path, release)
        (destination / _RELEASE_FILE).write_text(
            json.dumps(release.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return release


def load_release(artifact_directory: Path) -> Release:
    release_path = artifact_directory / _RELEASE_FILE
    if not release_path.is_file():
        raise InvalidArtifactError(f"Artifact has no {_RELEASE_FILE}: {artifact_directory}")
    try:
        raw_value = json.loads(release_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise InvalidArtifactError(f"Cannot read release metadata: {release_path}") from error
    if not isinstance(raw_value, dict):
        raise InvalidArtifactError(f"Release metadata must be an object: {release_path}")
    try:
        return Release.from_dict(raw_value)
    except (TypeError, ValueError) as error:
        raise InvalidArtifactError(f"Invalid release metadata: {release_path}") from error


def _inject_release_marker(index_path: Path, release: Release) -> None:
    document = index_path.read_text(encoding="utf-8")
    if "</head>" not in document:
        raise InvalidArtifactError(f"Root HTML document has no closing head tag: {index_path}")
    marker = html.escape(release.marker, quote=True)
    commit_sha = html.escape(release.commit_sha, quote=True)
    metadata = f'<meta name="deployment-commit" content="{commit_sha}">\n<!-- {marker} -->\n'
    index_path.write_text(document.replace("</head>", metadata + "</head>", 1), encoding="utf-8")
