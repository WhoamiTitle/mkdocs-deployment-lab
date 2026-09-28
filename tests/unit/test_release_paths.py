from pathlib import PurePosixPath

import pytest

from publication_pipeline.application.errors import UnsafePathError
from publication_pipeline.application.models import validate_remote_relative_path


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
