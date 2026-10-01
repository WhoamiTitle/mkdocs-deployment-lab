"""Filesystem deployment adapter used for local verification."""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from publication_pipeline.application.errors import (
    PublicationError,
    RollbackUnavailableError,
    UnsafePathError,
)
from publication_pipeline.application.models import (
    DeploymentReceipt,
    PreviewCleanupReceipt,
    Release,
)


class LocalReleaseGateway:
    """Mirror the remote release layout using local directories and symlinks."""

    def __init__(self, state_root: Path, public_path: Path) -> None:
        self._state_root = state_root.absolute()
        self._public_path = public_path.absolute()
        _validate_local_target(self._state_root, "state root")
        _validate_local_target(self._public_path, "public path")
        if self._public_path.exists() and not self._public_path.is_symlink():
            raise UnsafePathError(
                f"Public path already exists and is not a symlink: {self._public_path}"
            )

    def publish(self, release: Release, source: Path) -> DeploymentReceipt:
        self._prepare_layout()
        release_path = self._state_root / "releases" / release.release_id
        self._stage_artifact(source, release_path, include_previews=True)

        current_link = self._state_root / "current"
        previous_link = self._state_root / "previous"
        old_target = _read_link(current_link)
        if old_target is not None:
            _atomic_symlink(previous_link, old_target)

        new_target = Path("releases") / release.release_id
        _atomic_symlink(current_link, new_target)
        _atomic_symlink(self._public_path, release_path)
        return DeploymentReceipt(
            release_id=release.release_id,
            location=str(self._public_path),
            previous_release_id=_target_release_id(old_target),
        )

    def publish_preview(
        self,
        release: Release,
        source: Path,
        branch_slug: str,
    ) -> DeploymentReceipt:
        self._prepare_layout()
        branch_root = self._state_root / "preview-releases" / branch_slug
        release_path = branch_root / release.release_id
        self._stage_artifact(source, release_path, include_previews=False)

        public_preview_link = self._state_root / "shared-previews" / branch_slug
        preview_target = Path("..") / "preview-releases" / branch_slug / release.release_id
        old_target = _read_link(public_preview_link)
        _atomic_symlink(public_preview_link, preview_target)
        return DeploymentReceipt(
            release_id=release.release_id,
            location=str(self._public_path / "previews" / branch_slug),
            previous_release_id=_target_release_id(old_target),
        )

    def rollback(self) -> DeploymentReceipt:
        current_link = self._state_root / "current"
        previous_link = self._state_root / "previous"
        current_target = _read_link(current_link)
        previous_target = _read_link(previous_link)
        if current_target is None or previous_target is None:
            raise RollbackUnavailableError("Both current and previous releases are required")

        _atomic_symlink(current_link, previous_target)
        _atomic_symlink(previous_link, current_target)
        activated_path = self._state_root / previous_target
        _atomic_symlink(self._public_path, activated_path)
        release_id = _target_release_id(previous_target)
        if release_id is None:
            raise RollbackUnavailableError("Previous release link has no release identifier")
        return DeploymentReceipt(
            release_id=release_id,
            location=str(self._public_path),
            previous_release_id=_target_release_id(current_target),
        )

    def cleanup_preview(self, branch_slug: str) -> PreviewCleanupReceipt:
        preview_link = self._state_root / "shared-previews" / branch_slug
        branch_root = self._state_root / "preview-releases" / branch_slug
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
            location=str(self._public_path / "previews" / branch_slug),
            removed_release_count=removed_release_count,
        )

    def _prepare_layout(self) -> None:
        for relative_path in ("releases", "preview-releases", "shared-previews"):
            (self._state_root / relative_path).mkdir(parents=True, exist_ok=True)
        self._public_path.parent.mkdir(parents=True, exist_ok=True)

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
                    self._state_root / "shared-previews",
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


def _target_release_id(target: Path | None) -> str | None:
    return target.name if target is not None else None


def _validate_local_target(path: Path, label: str) -> None:
    forbidden = {Path("/"), Path.home().absolute()}
    if path in forbidden:
        raise UnsafePathError(f"Refusing to use broad {label}: {path}")
