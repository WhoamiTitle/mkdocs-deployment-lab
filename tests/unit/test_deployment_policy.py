from datetime import UTC, datetime
from pathlib import Path

import pytest

from publication_pipeline.application.cleanup_preview import CleanupPreview
from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import Release, SourceRevision, branch_to_slug
from publication_pipeline.infrastructure.local_release_gateway import LocalReleaseGateway


def _artifact(path: Path, release: Release, text: str) -> Path:
    path.mkdir()
    (path / "index.html").write_text(text, encoding="utf-8")
    (path / "release.json").write_text("{}", encoding="utf-8")
    return path


def _release(commit: str, second: int) -> Release:
    return Release.create(
        SourceRevision(commit_sha=commit, branch="main", dirty=False),
        built_at=datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC),
    )


def test_publish_then_rollback_swaps_immutable_releases(tmp_path: Path) -> None:
    gateway = LocalReleaseGateway(tmp_path / "state", tmp_path / "public")
    first = _release("a" * 40, 1)
    second = _release("b" * 40, 2)
    first_artifact = _artifact(tmp_path / "first", first, "first")
    second_artifact = _artifact(tmp_path / "second", second, "second")

    gateway.publish(first, first_artifact)
    gateway.publish(second, second_artifact)
    assert (tmp_path / "public" / "index.html").read_text(encoding="utf-8") == "second"

    receipt = gateway.rollback()

    assert receipt.release_id == first.release_id
    assert (tmp_path / "public" / "index.html").read_text(encoding="utf-8") == "first"
    assert (tmp_path / "state" / "releases" / second.release_id).is_dir()


def test_preview_is_published_under_shared_preview_path(tmp_path: Path) -> None:
    gateway = LocalReleaseGateway(tmp_path / "state", tmp_path / "public")
    production = _release("a" * 40, 1)
    preview = _release("b" * 40, 2)
    production_artifact = _artifact(tmp_path / "production", production, "production")
    preview_artifact = _artifact(tmp_path / "preview", preview, "preview")

    gateway.publish(production, production_artifact)
    receipt = gateway.publish_preview(preview, preview_artifact, "feature-report-abcd1234")

    preview_index = tmp_path / "public" / "previews" / "feature-report-abcd1234" / "index.html"
    assert preview_index.read_text(encoding="utf-8") == "preview"
    assert receipt.location.endswith("previews/feature-report-abcd1234")


def test_preview_cleanup_requires_confirmation_and_removes_branch(tmp_path: Path) -> None:
    gateway = LocalReleaseGateway(tmp_path / "state", tmp_path / "public")
    production = _release("a" * 40, 1)
    preview = _release("b" * 40, 2)
    production_artifact = _artifact(tmp_path / "production", production, "production")
    preview_artifact = _artifact(tmp_path / "preview", preview, "preview")
    gateway.publish(production, production_artifact)
    branch = "feature/report"
    branch_slug = branch_to_slug(branch)
    gateway.publish_preview(preview, preview_artifact, branch_slug)

    with pytest.raises(PublicationError, match="exact branch confirmation"):
        CleanupPreview(gateway).execute(branch, "feature/other")

    receipt = CleanupPreview(gateway).execute(branch, branch)

    assert receipt.branch_slug == branch_slug
    assert receipt.removed_release_count == 1
    assert not (tmp_path / "state" / "shared-previews" / branch_slug).exists()
    assert not (tmp_path / "state" / "preview-releases" / branch_slug).exists()
