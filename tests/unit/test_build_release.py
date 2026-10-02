from pathlib import Path

from publication_pipeline.application.build_release import BuildRelease, BuildReleaseRequest
from publication_pipeline.application.models import Release, SourceRevision
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha


class StubSiteBuilder:
    def __init__(self) -> None:
        self.destination: Path | None = None

    def build(self, destination: Path) -> None:
        self.destination = destination


class StubSourceControl:
    def revision(self) -> SourceRevision:
        return SourceRevision(
            commit_sha=CommitSha("a" * 40),
            branch=BranchName("main"),
            dirty=False,
        )


class RecordingArtifactWriter:
    def __init__(self) -> None:
        self.destination: Path | None = None
        self.release: Release | None = None

    def write(self, destination: Path, release: Release) -> None:
        self.destination = destination
        self.release = release


def test_build_release_coordinates_ports_without_filesystem_logic(tmp_path: Path) -> None:
    site_builder = StubSiteBuilder()
    artifact_writer = RecordingArtifactWriter()

    release = BuildRelease(
        site_builder,
        StubSourceControl(),
        artifact_writer,
    ).execute(BuildReleaseRequest(destination=tmp_path))

    assert site_builder.destination == tmp_path
    assert artifact_writer.destination == tmp_path
    assert artifact_writer.release == release
    assert release.commit_sha == CommitSha("a" * 40)
