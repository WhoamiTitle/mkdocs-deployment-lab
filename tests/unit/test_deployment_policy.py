from datetime import UTC, datetime
from pathlib import Path

import pytest

from publication_pipeline.application.cleanup_preview import CleanupPreview, CleanupPreviewRequest
from publication_pipeline.application.errors import (
    LocalDeploymentError,
    PublicationError,
    UnsafePathError,
)
from publication_pipeline.application.models import Release, SourceRevision
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime
from publication_pipeline.infrastructure import local_release_gateway as local_gateway_module
from publication_pipeline.infrastructure.local_release_gateway import LocalReleaseGateway


def _artifact(path: Path, release: Release, text: str) -> Path:
    path.mkdir()
    (path / "index.html").write_text(text, encoding="utf-8")
    (path / "release.json").write_text("{}", encoding="utf-8")
    return path


def _release(commit: str, second: int) -> Release:
    return Release.create(
        SourceRevision(
            commit_sha=CommitSha(commit),
            branch=BranchName("main"),
            dirty=False,
        ),
        built_at=UtcDatetime(datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)),
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
    assert (tmp_path / "state" / "releases" / second.release_id.value).is_dir()
    assert (tmp_path / "public").readlink() == tmp_path / "state" / "current"


def test_failed_link_preparation_keeps_active_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployment_root = tmp_path / "state"
    public_path = tmp_path / "public"
    gateway = LocalReleaseGateway(deployment_root, public_path)
    first = _release("a" * 40, 1)
    second = _release("b" * 40, 2)
    gateway.publish(first, _artifact(tmp_path / "first", first, "first"))
    original_atomic_symlink = local_gateway_module._atomic_symlink
    failure_injected = False

    def fail_once_before_public_link(link_path: Path, target: Path) -> None:
        nonlocal failure_injected
        if link_path == public_path and not failure_injected:
            failure_injected = True
            raise OSError("injected public-link failure")
        original_atomic_symlink(link_path, target)

    monkeypatch.setattr(local_gateway_module, "_atomic_symlink", fail_once_before_public_link)

    with pytest.raises(LocalDeploymentError, match="Cannot publish local release") as captured:
        gateway.publish(second, _artifact(tmp_path / "second", second, "second"))

    assert isinstance(captured.value.__cause__, OSError)

    assert (public_path / "index.html").read_text(encoding="utf-8") == "first"
    assert (deployment_root / "current").readlink().name == first.release_id.value
    assert not (deployment_root / "previous").exists()


def test_release_directory_must_resolve_inside_deployment_root(tmp_path: Path) -> None:
    deployment_root = tmp_path / "state"
    outside_root = tmp_path / "outside"
    deployment_root.mkdir()
    outside_root.mkdir()
    (deployment_root / "releases").symlink_to(outside_root, target_is_directory=True)
    gateway = LocalReleaseGateway(deployment_root, tmp_path / "public")
    release = _release("a" * 40, 1)

    with pytest.raises(UnsafePathError, match="escapes the deployment root"):
        gateway.publish(release, _artifact(tmp_path / "artifact", release, "release"))

    assert not (outside_root / release.release_id.value).exists()


def test_preview_is_published_under_shared_preview_path(tmp_path: Path) -> None:
    gateway = LocalReleaseGateway(tmp_path / "state", tmp_path / "public")
    production = _release("a" * 40, 1)
    preview = _release("b" * 40, 2)
    production_artifact = _artifact(tmp_path / "production", production, "production")
    preview_artifact = _artifact(tmp_path / "preview", preview, "preview")

    gateway.publish(production, production_artifact)
    branch_slug = BranchSlug("feature-report-abcd1234")
    receipt = gateway.publish_preview(preview, preview_artifact, branch_slug)

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
    branch_slug = BranchSlug.from_branch(BranchName(branch))
    gateway.publish_preview(preview, preview_artifact, branch_slug)

    with pytest.raises(PublicationError, match="exact branch confirmation"):
        CleanupPreview(gateway).execute(
            CleanupPreviewRequest(branch=branch, confirmed_branch="feature/other")
        )

    receipt = CleanupPreview(gateway).execute(
        CleanupPreviewRequest(branch=branch, confirmed_branch=branch)
    )

    assert receipt.branch_slug == branch_slug
    assert receipt.removed_release_count == 1
    assert not (tmp_path / "state" / "shared-previews" / branch_slug.value).exists()
    assert not (tmp_path / "state" / "preview-releases" / branch_slug.value).exists()


def test_preview_cleanup_rejects_branch_directory_outside_deployment_root(
    tmp_path: Path,
) -> None:
    deployment_root = tmp_path / "state"
    outside_root = tmp_path / "outside"
    branch_slug = BranchSlug("feature-report-abcd1234")
    branch_parent = deployment_root / "preview-releases"
    branch_parent.mkdir(parents=True)
    outside_root.mkdir()
    (outside_root / "keep.txt").write_text("keep", encoding="utf-8")
    (branch_parent / branch_slug.value).symlink_to(outside_root, target_is_directory=True)
    gateway = LocalReleaseGateway(deployment_root, tmp_path / "public")

    with pytest.raises(UnsafePathError, match="symlink escapes"):
        gateway.cleanup_preview(branch_slug)

    assert (outside_root / "keep.txt").read_text(encoding="utf-8") == "keep"
