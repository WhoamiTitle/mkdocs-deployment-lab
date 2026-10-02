from datetime import UTC, datetime
from pathlib import Path

import pytest

from publication_pipeline.application.errors import InvalidArtifactError
from publication_pipeline.application.models import Release
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)


def _release() -> Release:
    return Release(
        release_id=ReleaseId("abcdef123456-20261002T010203Z"),
        commit_sha=CommitSha("a" * 40),
        branch=BranchName("main"),
        built_at=UtcDatetime(datetime(2026, 10, 2, 1, 2, 3, tzinfo=UTC)),
        dirty=False,
    )


def test_store_writes_marker_and_round_trips_release(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html><head></head></html>", encoding="utf-8")
    store = FilesystemReleaseArtifactStore()
    release = _release()

    store.write(tmp_path, release)

    document = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert release.marker in document
    assert 'name="deployment-commit"' in document
    assert store.read(tmp_path) == release


def test_store_rejects_root_document_without_head(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")

    with pytest.raises(InvalidArtifactError, match="closing head tag"):
        FilesystemReleaseArtifactStore().write(tmp_path, _release())


def test_store_rejects_invalid_release_document(tmp_path: Path) -> None:
    (tmp_path / "release.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(InvalidArtifactError, match="Cannot read release metadata"):
        FilesystemReleaseArtifactStore().read(tmp_path)
