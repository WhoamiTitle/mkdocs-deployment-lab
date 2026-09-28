"""Typed contracts shared by application use cases and adapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

from publication_pipeline.application.errors import UnsafePathError

_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_UNSAFE_SLUG_CHARS = re.compile(r"[^a-z0-9._-]+")
_MULTIPLE_DASHES = re.compile(r"-{2,}")


@dataclass(frozen=True, slots=True)
class SourceRevision:
    """Version-control state used to identify a generated artifact."""

    commit_sha: str
    branch: str
    dirty: bool


@dataclass(frozen=True, slots=True)
class Release:
    """Immutable metadata embedded into one generated site artifact."""

    release_id: str
    commit_sha: str
    branch: str
    built_at: datetime
    dirty: bool

    @classmethod
    def create(cls, revision: SourceRevision, *, built_at: datetime | None = None) -> Release:
        timestamp = built_at or datetime.now(UTC)
        normalized_timestamp = timestamp.astimezone(UTC)
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

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "release_id": self.release_id,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "built_at": self.built_at.isoformat(),
            "dirty": self.dirty,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> Release:
        return cls(
            release_id=_required_string(value, "release_id"),
            commit_sha=_required_string(value, "commit_sha"),
            branch=_required_string(value, "branch"),
            built_at=datetime.fromisoformat(_required_string(value, "built_at")),
            dirty=_required_bool(value, "dirty"),
        )


@dataclass(frozen=True, slots=True)
class DeploymentReceipt:
    """Observable result of changing a deployment target."""

    release_id: str
    location: str
    previous_release_id: str | None = None


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: str


@dataclass(frozen=True, slots=True)
class HealthcheckResult:
    url: str
    status_code: int
    checked_texts: tuple[str, ...]
    attempts: int


def branch_to_slug(branch: str) -> str:
    """Return a readable, collision-resistant and path-safe branch identifier."""

    normalized = _UNSAFE_SLUG_CHARS.sub("-", branch.strip().lower())
    normalized = _MULTIPLE_DASHES.sub("-", normalized).strip(".-")
    base = (normalized or "branch")[:48].rstrip(".-")
    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:8]
    return f"{base}-{digest}"


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


def _required_string(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Release metadata field {key!r} must be a non-empty string")
    return item


def _required_bool(value: dict[str, object], key: str) -> bool:
    item = value.get(key)
    if not isinstance(item, bool):
        raise ValueError(f"Release metadata field {key!r} must be a boolean")
    return item
