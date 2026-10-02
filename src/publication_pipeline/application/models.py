"""Typed contracts shared by application use cases and adapters."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Self

from publication_pipeline.application.errors import UnsafePathError
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRevision:
    """Version-control state used to identify a generated artifact."""

    commit_sha: CommitSha
    branch: BranchName
    dirty: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class Release:
    """Immutable metadata embedded into one generated site artifact."""

    release_id: ReleaseId
    commit_sha: CommitSha
    branch: BranchName
    built_at: UtcDatetime
    dirty: bool

    @classmethod
    def create(cls, revision: SourceRevision, *, built_at: UtcDatetime | None = None) -> Self:
        timestamp = built_at or UtcDatetime(datetime.now(UTC))
        return cls(
            release_id=ReleaseId.create(revision.commit_sha, timestamp),
            commit_sha=revision.commit_sha,
            branch=revision.branch,
            built_at=timestamp,
            dirty=revision.dirty,
        )

    @property
    def marker(self) -> str:
        """Unique text expected in the deployed root HTML document."""

        return f"deployment-marker:{self.release_id.value}:{self.commit_sha.value}"


@dataclass(frozen=True, slots=True, kw_only=True)
class RsyncTransferMetrics:
    """Machine-readable transfer statistics reported by rsync."""

    duration_seconds: float
    file_count: int
    transferred_file_count: int
    total_file_size_bytes: int
    transferred_file_size_bytes: int
    sent_bytes: int
    received_bytes: int


@dataclass(frozen=True, slots=True, kw_only=True)
class DeploymentReceipt:
    """Observable result of changing a deployment target."""

    release_id: ReleaseId
    location: str
    previous_release_id: ReleaseId | None = None
    transfer: RsyncTransferMetrics | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class PreviewCleanupReceipt:
    """Observable result of removing one branch preview."""

    branch_slug: BranchSlug
    location: str
    removed_release_count: int


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str


@dataclass(frozen=True, slots=True, kw_only=True)
class HealthcheckResult:
    url: str
    status_code: int
    checked_texts: tuple[str, ...]
    attempts: int


def validate_remote_relative_path(raw_path: str) -> PurePosixPath:
    """Validate a path that will be resolved below a remote home directory."""

    path = PurePosixPath(raw_path)
    if not raw_path or path.is_absolute() or ".." in path.parts:
        raise UnsafePathError(f"Remote path must stay below the home directory: {raw_path!r}")
    if any(part in {"", "."} or not _SAFE_SEGMENT.fullmatch(part) for part in path.parts):
        raise UnsafePathError(f"Remote path contains an unsafe segment: {raw_path!r}")
    return path
