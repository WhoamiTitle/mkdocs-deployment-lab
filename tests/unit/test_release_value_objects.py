from datetime import UTC, datetime, timedelta, timezone

import pytest

from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime


@pytest.mark.parametrize(
    "value",
    [
        "../../escaped-release",
        "/absolute-release",
        "nested/release",
        ".",
        "..",
        "release with spaces",
        "x" * 129,
    ],
)
def test_release_id_rejects_unsafe_path_segment(value: str) -> None:
    with pytest.raises(ValueError, match="Unsafe release ID"):
        ReleaseId(value)


@pytest.mark.parametrize("value", ["", "a" * 39, "A" * 40, "g" * 40])
def test_commit_sha_rejects_invalid_git_identifier(value: str) -> None:
    with pytest.raises(ValueError, match="Invalid commit SHA"):
        CommitSha(value)


@pytest.mark.parametrize("value", ["a" * 40, "b" * 64])
def test_commit_sha_accepts_supported_git_object_formats(value: str) -> None:
    assert CommitSha(value).value == value


def test_branch_name_rejects_blank_value() -> None:
    with pytest.raises(ValueError, match="non-blank"):
        BranchName("  ")


def test_utc_datetime_rejects_naive_value() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        UtcDatetime(datetime(2026, 1, 1))


def test_utc_datetime_normalizes_value() -> None:
    built_at = UtcDatetime(datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))))

    assert built_at.value == datetime(2026, 1, 1, tzinfo=UTC)


def test_release_id_is_derived_from_commit_and_utc_time() -> None:
    release_id = ReleaseId.create(
        CommitSha("a" * 40),
        UtcDatetime(datetime(2026, 1, 1, 1, 2, 3, tzinfo=UTC)),
    )

    assert release_id.value == "aaaaaaaaaaaa-20260101T010203Z"
