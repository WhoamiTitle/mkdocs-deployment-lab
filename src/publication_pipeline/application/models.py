"""Typed contracts shared by application use cases and adapters."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Self

from publication_pipeline.application.errors import UnsafePathError

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_UNSAFE_SLUG_CHARS = re.compile(r"[^a-z0-9._-]+")
_MULTIPLE_DASHES = re.compile(r"-{2,}")
_MAX_RELEASE_ID_LENGTH = 128
_MAX_BRANCH_SLUG_LENGTH = 57


@dataclass(frozen=True, slots=True, kw_only=True)
class SourceRevision:
    """Version-control state used to identify a generated artifact."""

    commit_sha: str
    branch: str
    dirty: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class Release:
    """Immutable metadata embedded into one generated site artifact."""

    release_id: str
    commit_sha: str
    branch: str
    built_at: datetime
    dirty: bool

    def __post_init__(self) -> None:
        _validate_release_id(self.release_id)
        _validate_non_blank(self.commit_sha, "commit SHA")
        _validate_non_blank(self.branch, "branch")
        object.__setattr__(self, "built_at", _normalize_utc(self.built_at))

    @classmethod
    def create(cls, revision: SourceRevision, *, built_at: datetime | None = None) -> Self:
        timestamp = built_at or datetime.now(UTC)
        normalized_timestamp = _normalize_utc(timestamp)
        commit_part = _safe_identifier(revision.commit_sha)[:12] or "uncommitted"
        release_id = f"{commit_part}-{normalized_timestamp:%Y%m%dT%H%M%SZ}"
        return cls(
            release_id=release_id,
            commit_sha=revision.commit_sha,
            branch=revision.branch,
            built_at=normalized_timestamp,
            dirty=revision.dirty,
        )

    @property
    def marker(self) -> str:
        """Unique text expected in the deployed root HTML document."""

        return f"deployment-marker:{self.release_id}:{self.commit_sha}"


@dataclass(frozen=True, slots=True)
class BranchSlug:
    """Validated path segment used to identify one branch preview."""

    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) > _MAX_BRANCH_SLUG_LENGTH
            or self.value in {".", ".."}
            or _SAFE_SEGMENT.fullmatch(self.value) is None
        ):
            raise ValueError(f"Unsafe branch slug: {self.value!r}")

    @classmethod
    def from_branch(cls, branch: str) -> Self:
        if not branch.strip():
            raise ValueError("Branch name must be non-blank")
        normalized = _UNSAFE_SLUG_CHARS.sub("-", branch.strip().lower())
        normalized = _MULTIPLE_DASHES.sub("-", normalized).strip(".-")
        base = (normalized or "branch")[:48].rstrip(".-")
        digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:8]
        return cls(f"{base}-{digest}")


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

    release_id: str
    location: str
    previous_release_id: str | None = None
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


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")


def _validate_release_id(value: str) -> None:
    if (
        len(value) > _MAX_RELEASE_ID_LENGTH
        or value in {".", ".."}
        or _SAFE_SEGMENT.fullmatch(value) is None
    ):
        raise ValueError(f"Unsafe release ID: {value!r}")


def _validate_non_blank(value: str, label: str) -> None:
    if not value.strip():
        raise ValueError(f"Release {label} must be non-blank")


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Release build time must be timezone-aware")
    return value.astimezone(UTC)
