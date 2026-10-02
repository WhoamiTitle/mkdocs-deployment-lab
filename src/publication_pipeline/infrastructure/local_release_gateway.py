"""Filesystem deployment adapter used for local verification."""

import os
import shutil
import uuid
from pathlib import Path

from publication_pipeline.application.errors import (
    LocalDeploymentError,
    PublicationError,
    RollbackUnavailableError,
    UnsafePathError,
)
from publication_pipeline.application.models import (
    BranchSlug,
    DeploymentReceipt,
    PreviewCleanupReceipt,
    Release,
)


class LocalReleaseGateway:
    """Mirror the remote release layout using local directories and symlinks."""

    def __init__(self, deployment_root: Path, public_path: Path) -> None:
        self._deployment_root = deployment_root.absolute()
        self._public_path = public_path.absolute()
        try:
            _validate_local_target(self._deployment_root, "deployment root")
            _validate_local_target(self._public_path, "public path")
            if self._public_path.exists() and not self._public_path.is_symlink():
                raise UnsafePathError(
                    f"Public path already exists and is not a symlink: {self._public_path}"
                )
        except OSError as error:
            raise LocalDeploymentError("Cannot initialize local deployment paths") from error

    def publish(self, release: Release, source: Path) -> DeploymentReceipt:
        try:
            return self._publish(release, source)
        except OSError as error:
            raise LocalDeploymentError(
                f"Cannot publish local release {release.release_id}"
            ) from error

    def _publish(self, release: Release, source: Path) -> DeploymentReceipt:
        self._prepare_layout()
        release_path = self._resolve_deployment_path("releases", release.release_id)
        self._stage_artifact(source, release_path, include_previews=True)

        current_link = self._deployment_root / "current"
        previous_link = self._deployment_root / "previous"
        old_target = _read_link(current_link)
        old_previous_target = _read_link(previous_link)
        old_public_target = _read_link(self._public_path)
        new_target = Path("releases") / release.release_id
        try:
            if old_target is not None:
                _atomic_symlink(previous_link, old_target)
            _atomic_symlink(self._public_path, current_link)
            _atomic_symlink(current_link, new_target)
        except BaseException as error:
            _restore_links(
                error,
                (current_link, old_target),
                (previous_link, old_previous_target),
                (self._public_path, old_public_target),
            )
            raise
        return DeploymentReceipt(
            release_id=release.release_id,
            location=str(self._public_path),
            previous_release_id=_target_release_id(old_target),
        )

    def publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: BranchSlug,
    ) -> DeploymentReceipt:
        try:
            return self._publish_preview(release, source, branch_slug)
        except OSError as error:
            raise LocalDeploymentError(
                f"Cannot publish local preview {branch_slug.value}"
            ) from error

    def _publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: BranchSlug,
    ) -> DeploymentReceipt:
        slug = branch_slug.value
        self._prepare_layout()
        release_path = self._resolve_deployment_path(
            "preview-releases",
            slug,
            release.release_id,
        )
        self._stage_artifact(source, release_path, include_previews=False)

        public_preview_link = self._resolve_deployment_path("shared-previews", slug)
        preview_target = Path("..") / "preview-releases" / slug / release.release_id
        old_target = _read_link(public_preview_link)
        _atomic_symlink(public_preview_link, preview_target)
        return DeploymentReceipt(
            release_id=release.release_id,
            location=str(self._public_path / "previews" / slug),
            previous_release_id=_target_release_id(old_target),
        )

    def rollback(self) -> DeploymentReceipt:
        try:
            return self._rollback()
        except OSError as error:
            raise LocalDeploymentError("Cannot roll back local release") from error

    def _rollback(self) -> DeploymentReceipt:
        current_link = self._deployment_root / "current"
        previous_link = self._deployment_root / "previous"
        current_target = _read_link(current_link)
        previous_target = _read_link(previous_link)
        if current_target is None or previous_target is None:
            raise RollbackUnavailableError("Both current and previous releases are required")

        old_public_target = _read_link(self._public_path)
        try:
            _atomic_symlink(previous_link, current_target)
            _atomic_symlink(self._public_path, current_link)
            _atomic_symlink(current_link, previous_target)
        except BaseException as error:
            _restore_links(
                error,
                (current_link, current_target),
                (previous_link, previous_target),
                (self._public_path, old_public_target),
            )
            raise
        release_id = _target_release_id(previous_target)
        if release_id is None:
            raise RollbackUnavailableError("Previous release link has no release identifier")
        return DeploymentReceipt(
            release_id=release_id,
            location=str(self._public_path),
            previous_release_id=_target_release_id(current_target),
        )

    def cleanup_preview(self, branch_slug: BranchSlug) -> PreviewCleanupReceipt:
        try:
            return self._cleanup_preview(branch_slug)
        except OSError as error:
            raise LocalDeploymentError(
                f"Cannot clean up local preview {branch_slug.value}"
            ) from error

    def _cleanup_preview(self, branch_slug: BranchSlug) -> PreviewCleanupReceipt:
        slug = branch_slug.value
        preview_link = self._resolve_deployment_path("shared-previews", slug)
        branch_root = self._resolve_deployment_path("preview-releases", slug)
        if preview_link.exists() and not preview_link.is_symlink():
            raise UnsafePathError(f"Preview path is not a symlink: {preview_link}")

        removed_release_count = 0
        if branch_root.is_dir():
            removed_release_count = sum(path.is_dir() for path in branch_root.iterdir())
        if preview_link.is_symlink():
            preview_link.unlink()
        if branch_root.exists():
            shutil.rmtree(branch_root)

        return PreviewCleanupReceipt(
            branch_slug=branch_slug,
            location=str(self._public_path / "previews" / slug),
            removed_release_count=removed_release_count,
        )

    def _prepare_layout(self) -> None:
        for relative_path in ("releases", "preview-releases", "shared-previews"):
            (self._deployment_root / relative_path).mkdir(parents=True, exist_ok=True)
            self._resolve_deployment_path(relative_path)
        self._public_path.parent.mkdir(parents=True, exist_ok=True)

    def _resolve_deployment_path(self, *parts: str) -> Path:
        resolved_root = self._deployment_root.resolve()
        deployment_path = self._deployment_root.joinpath(*parts)
        resolved_parent = deployment_path.parent.resolve()
        if not resolved_parent.is_relative_to(resolved_root):
            raise UnsafePathError(f"Local path escapes the deployment root: {deployment_path}")
        if deployment_path.is_symlink():
            resolved_target = deployment_path.resolve()
            if not resolved_target.is_relative_to(resolved_root):
                raise UnsafePathError(
                    f"Local symlink escapes the deployment root: {deployment_path}"
                )
        return deployment_path

    def _stage_artifact(self, source: Path, destination: Path, *, include_previews: bool) -> None:
        if destination.exists():
            raise PublicationError(f"Immutable release already exists: {destination}")
        staging_path = destination.with_name(f".staging-{destination.name}-{uuid.uuid4().hex}")
        try:
            shutil.copytree(source, staging_path, symlinks=True)
            if not (staging_path / "index.html").is_file():
                raise PublicationError(f"Staged release has no index.html: {staging_path}")
            if include_previews:
                (staging_path / "previews").symlink_to(
                    self._resolve_deployment_path("shared-previews"),
                    target_is_directory=True,
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging_path, destination)
        except BaseException:
            if staging_path.exists():
                shutil.rmtree(staging_path)
            raise


def _atomic_symlink(link_path: Path, target: Path) -> None:
    link_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_link = link_path.with_name(f".{link_path.name}.next-{uuid.uuid4().hex}")
    temporary_link.symlink_to(target, target_is_directory=True)
    try:
        os.replace(temporary_link, link_path)
    finally:
        if temporary_link.is_symlink():
            temporary_link.unlink()


def _read_link(path: Path) -> Path | None:
    if not path.is_symlink():
        return None
    return Path(os.readlink(path))


def _restore_links(
    original_error: BaseException,
    *snapshots: tuple[Path, Path | None],
) -> None:
    for link_path, target in snapshots:
        try:
            if target is None:
                if link_path.is_symlink():
                    link_path.unlink()
            else:
                _atomic_symlink(link_path, target)
        except Exception as restore_error:
            original_error.add_note(f"Could not restore symlink {link_path}: {restore_error}")


def _target_release_id(target: Path | None) -> str | None:
    return target.name if target is not None else None


def _validate_local_target(path: Path, label: str) -> None:
    forbidden = {Path("/"), Path.home().absolute()}
    if path in forbidden:
        raise UnsafePathError(f"Refusing to use broad {label}: {path}")
