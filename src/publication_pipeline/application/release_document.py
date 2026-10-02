"""Typed serialization contract for the published release document."""

from datetime import datetime
from typing import TypedDict

from publication_pipeline.application.models import Release
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None


class ReleaseDocument(TypedDict):
    release_id: str
    commit_sha: str
    branch: str
    built_at: str
    dirty: bool


def release_to_document(release: Release) -> ReleaseDocument:
    return ReleaseDocument(
        release_id=release.release_id.value,
        commit_sha=release.commit_sha.value,
        branch=release.branch.value,
        built_at=release.built_at.value.isoformat(),
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
        }:
            try:
                return Release(
                    release_id=ReleaseId(release_id),
                    commit_sha=CommitSha(commit_sha),
                    branch=BranchName(branch),
                    built_at=UtcDatetime(datetime.fromisoformat(built_at)),
                    dirty=dirty,
                )
            except ValueError as error:
                raise ValueError("Invalid release document") from error
        case _:
            raise ValueError("Invalid release document")
