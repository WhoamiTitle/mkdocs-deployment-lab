"""Build a static site and attach reproducibility metadata."""

from dataclasses import dataclass
from pathlib import Path

from publication_pipeline.application.models import Release
from publication_pipeline.application.ports import (
    ReleaseArtifactWriter,
    SiteBuilder,
    SourceControl,
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildReleaseRequest:
    destination: Path


class BuildRelease:
    def __init__(
        self,
        site_builder: SiteBuilder,
        source_control: SourceControl,
        artifact_writer: ReleaseArtifactWriter,
    ) -> None:
        self._site_builder = site_builder
        self._source_control = source_control
        self._artifact_writer = artifact_writer

    def execute(self, request: BuildReleaseRequest) -> Release:
        release = Release.create(self._source_control.revision())
        self._site_builder.build(request.destination)
        self._artifact_writer.write(request.destination, release)
        return release
