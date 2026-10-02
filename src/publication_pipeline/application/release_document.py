"""Typed serialization contract for the published release document."""

from datetime import datetime
from typing import TypedDict

from publication_pipeline.application.models import Release

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class ReleaseDocument(TypedDict):
    release_id: str
    commit_sha: str
    branch: str
    built_at: str
    dirty: bool


def release_to_document(release: Release) -> ReleaseDocument:
    return ReleaseDocument(
        release_id=release.release_id,
        commit_sha=release.commit_sha,
        branch=release.branch,
        built_at=release.built_at.isoformat(),
        dirty=release.dirty,
    )


def release_from_document(value: JsonValue | ReleaseDocument) -> Release:
    match value:
        case {
            "release_id": str(release_id),
            "commit_sha": str(commit_sha),
            "branch": str(branch),
            "built_at": str(built_at),
            "dirty": bool(dirty),
        } if release_id and commit_sha and branch and built_at:
            return Release(
                release_id=release_id,
                commit_sha=commit_sha,
                branch=branch,
                built_at=datetime.fromisoformat(built_at),
                dirty=dirty,
            )
        case _:
            raise ValueError("Invalid release document")
