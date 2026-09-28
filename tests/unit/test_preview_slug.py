from publication_pipeline.application.models import branch_to_slug


def test_branch_slug_is_readable_and_path_safe() -> None:
    slug = branch_to_slug("Feature/Отчёт 2026")

    assert slug.startswith("feature-2026-")
    assert "/" not in slug
    assert " " not in slug


def test_similar_branch_names_do_not_collide() -> None:
    assert branch_to_slug("feature/a") != branch_to_slug("feature-a")


def test_branch_slug_is_stable() -> None:
    assert branch_to_slug("feature/report") == branch_to_slug("feature/report")
