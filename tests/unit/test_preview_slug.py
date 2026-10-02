import pytest

from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug


def test_branch_slug_is_readable_and_path_safe() -> None:
    slug = BranchSlug.from_branch(BranchName("Feature/Отчёт 2026")).value

    assert slug.startswith("feature-2026-")
    assert "/" not in slug
    assert " " not in slug


def test_similar_branch_names_do_not_collide() -> None:
    assert BranchSlug.from_branch(BranchName("feature/a")) != BranchSlug.from_branch(
        BranchName("feature-a")
    )


def test_branch_slug_is_stable() -> None:
    branch = BranchName("feature/report")
    assert BranchSlug.from_branch(branch) == BranchSlug.from_branch(branch)


@pytest.mark.parametrize("value", ("../outside", "nested/path", ".", "..", ""))
def test_branch_slug_rejects_unsafe_path_segments(value: str) -> None:
    with pytest.raises(ValueError, match="Unsafe branch slug"):
        BranchSlug(value)
