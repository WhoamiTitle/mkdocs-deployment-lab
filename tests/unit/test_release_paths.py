from datetime import UTC, datetime, timedelta, timezone
from pathlib import PurePosixPath

import pytest

from publication_pipeline.application.errors import UnsafePathError
from publication_pipeline.application.models import Release, validate_remote_relative_path


@pytest.mark.parametrize(
    "value",
    [
        ".deploy/research-site",
        "public_html/research-site",
        "sites/project_1/releases",
    ],
)
def test_accepts_relative_remote_path(value: str) -> None:
    assert validate_remote_relative_path(value) == PurePosixPath(value)


@pytest.mark.parametrize(
    "value",
    [
        "/var/www/site",
        "../public_html",
        "public_html/../../etc",
        "public html/site",
        "",
    ],
)
def test_rejects_remote_path_that_can_escape_scope(value: str) -> None:
    with pytest.raises(UnsafePathError):
        validate_remote_relative_path(value)


@pytest.mark.parametrize(
    "release_id",
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
def test_release_rejects_unsafe_identifier(release_id: str) -> None:
    with pytest.raises(ValueError, match="Unsafe release ID"):
        Release(
            release_id=release_id,
            commit_sha="a" * 40,
            branch="main",
            built_at=datetime(2026, 1, 1, tzinfo=UTC),
            dirty=False,
        )


@pytest.mark.parametrize(
    ("commit_sha", "branch"),
    [
        ("", "main"),
        ("a" * 40, "  "),
    ],
)
def test_release_rejects_blank_identity_fields(commit_sha: str, branch: str) -> None:
    with pytest.raises(ValueError, match="must be non-blank"):
        Release(
            release_id="valid-release",
            commit_sha=commit_sha,
            branch=branch,
            built_at=datetime(2026, 1, 1, tzinfo=UTC),
            dirty=False,
        )


def test_release_rejects_naive_build_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Release(
            release_id="valid-release",
            commit_sha="a" * 40,
            branch="main",
            built_at=datetime(2026, 1, 1),
            dirty=False,
        )


def test_release_normalizes_build_time_to_utc() -> None:
    release = Release(
        release_id="valid-release",
        commit_sha="a" * 40,
        branch="main",
        built_at=datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))),
        dirty=False,
    )

    assert release.built_at == datetime(2026, 1, 1, tzinfo=UTC)
