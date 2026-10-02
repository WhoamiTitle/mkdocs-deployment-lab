from datetime import UTC, datetime

import pytest

from publication_pipeline.application.models import Release
from publication_pipeline.application.release_document import (
    JsonValue,
    release_from_document,
    release_to_document,
)
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime


def test_release_document_round_trip() -> None:
    release = Release(
        release_id=ReleaseId("abcdef123456-20261002T010203Z"),
        commit_sha=CommitSha("a" * 40),
        branch=BranchName("main"),
        built_at=UtcDatetime(datetime(2026, 10, 2, 1, 2, 3, tzinfo=UTC)),
        dirty=False,
    )

    assert release_from_document(release_to_document(release)) == release


@pytest.mark.parametrize(
    "value",
    [
        {},
        {
            "release_id": "abcdef123456-20261002T010203Z",
            "commit_sha": "a" * 40,
            "branch": "main",
            "built_at": "2026-10-02T01:02:03+00:00",
            "dirty": "false",
        },
        {
            "release_id": "",
            "commit_sha": "a" * 40,
            "branch": "main",
            "built_at": "2026-10-02T01:02:03+00:00",
            "dirty": False,
        },
        {
            "release_id": "abcdef123456-20261002T010203Z",
            "commit_sha": "not-a-git-sha",
            "branch": "main",
            "built_at": "2026-10-02T01:02:03+00:00",
            "dirty": False,
        },
    ],
)
def test_release_document_rejects_invalid_structure(value: JsonValue) -> None:
    with pytest.raises(ValueError, match="Invalid release document"):
        release_from_document(value)
