import json
from pathlib import Path

import pytest

from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from scripts.deployment_targets import Target
from scripts.site_publication import (
    archive,
    build_versions,
    compose_pages,
    prepare,
    rollback_pages,
    run,
    select_latest,
    state_commit,
    version_key,
)
from scripts.verify_published_site import verify_local_site


@pytest.fixture
def source_repository(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.name", "Test builder")
    run(root, "git", "config", "user.email", "test@example.invalid")
    run(root, "git", "config", "core.autocrlf", "false")
    (root / "docs").mkdir()
    (root / "mkdocs.yml").write_text(
        "site_name: Test publication\nsite_url: !ENV [SITE_URL, 'http://localhost/']\n"
        "strict: true\ntheme:\n  name: material\n  font: false\n",
        encoding="utf-8",
    )
    template = Path(__file__).resolve().parents[2] / "mkdocs.versioned.yml"
    (root / "mkdocs.versioned.yml").write_text(template.read_text(encoding="utf-8"))
    index = root / "docs/index.md"
    index.write_text("# First release\n\npublication-site-control\n", encoding="utf-8")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "First snapshot")
    run(root, "git", "tag", "v1.0")
    index.write_text("# Second release\n\npublication-site-control\n", encoding="utf-8")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "Second snapshot")
    run(root, "git", "tag", "v1.1")
    return root


def test_versions_alias_selection_rollback_and_state_roundtrip(
    source_repository: Path,
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target: Target = {"id": "github-pages", "base_url": "https://example.test/lab/"}
    build_versions(source_repository, state, [target])
    production = state / "sites/github-pages/production"
    verify_local_site(production)
    assert "First release" in (production / "v1.0/index.html").read_text(encoding="utf-8")
    assert "Second release" in (production / "v1.1/index.html").read_text(encoding="utf-8")
    old_version = (production / "v1.0/index.html").read_bytes()
    assert "../v1.1/" in (production / "latest/index.html").read_text(encoding="utf-8")
    select_latest(source_repository, state, [target], "v1.0")
    assert "../v1.0/" in (production / "latest/index.html").read_text(encoding="utf-8")
    assert (production / "v1.0/index.html").read_bytes() == old_version
    rollback_pages(state)
    assert "../v1.1/" in (production / "latest/index.html").read_text(encoding="utf-8")
    preview = state / "sites/github-pages/previews/feature-example/index.html"
    preview.parent.mkdir(parents=True)
    preview.write_text("preserved preview")
    compose_pages(state / "sites/github-pages", tmp_path / "public")
    assert (
        tmp_path / "public/previews/feature-example/index.html"
    ).read_text() == "preserved preview"
    head = run(source_repository, "git", "rev-parse", "HEAD")
    commit = state_commit(source_repository, state, None)
    restored = tmp_path / "restored"
    archive(source_repository, commit, restored)
    verify_local_site(restored / "sites/github-pages/production")
    assert run(source_repository, "git", "rev-parse", "HEAD") == head
    assert run(source_repository, "git", "status", "--porcelain") == ""
    run(source_repository, "git", "tag", "-d", "v1.1")
    build_versions(source_repository, state, [target])
    assert "../v1.1/" in (production / "latest/index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("value", ["latest", "v1", "../v1.0", "v01.0", "v1.0-rc1"])
def test_rejects_invalid_stable_versions(value: str) -> None:
    with pytest.raises(ValueError):
        version_key(value)


def test_version_sorting_is_numeric() -> None:
    assert sorted(["v1.9", "v1.10", "v1.2"], key=version_key) == ["v1.2", "v1.9", "v1.10"]


def test_moved_published_tag_is_rejected(source_repository: Path, tmp_path: Path) -> None:
    state = tmp_path / "state"
    state.mkdir()
    target: Target = {"id": "github-pages", "base_url": "https://example.test/lab/"}
    build_versions(source_repository, state, [target])
    run(source_repository, "git", "tag", "-f", "v1.0", "HEAD")
    with pytest.raises(ValueError, match="was moved"):
        build_versions(source_repository, state, [target])
    versions = json.loads((state / "sites/github-pages/production/versions.json").read_text())
    assert {version["version"] for version in versions} == {"v1.0", "v1.1"}


def test_preview_cleanup_and_pages_recovery_preserve_other_targets(
    source_repository: Path, tmp_path: Path
) -> None:
    targets: list[Target] = [
        {"id": identity, "base_url": f"https://example.test/{identity}/"}
        for identity in ("github-pages", "helios-vasya", "helios-jenya")
    ]
    state = tmp_path / "state"
    state.mkdir()
    # This fixture exercises routing, rather than rebuilding the full version collection.
    from scripts.site_publication import build_plain

    for target in targets:
        build_plain(
            source_repository,
            state / "sites" / str(target["id"]) / "production",
            str(target["base_url"]),
        )
    original = (state / "sites/github-pages/production/index.html").read_bytes()
    output = tmp_path / "output"
    output.mkdir()
    prepare(source_repository, state, output, targets, "preview", "feature/a")
    first = BranchSlug.from_branch(BranchName("feature/a")).value
    prepare(source_repository, state, output, targets, "preview", "feature-a")
    second = BranchSlug.from_branch(BranchName("feature-a")).value
    assert first != second
    for target in targets:
        site = state / "sites" / str(target["id"])
        assert (site / "previews" / first / "release.json").is_file()
        assert (site / "previews" / second / "release.json").is_file()
    assert (state / "sites/github-pages/production/index.html").read_bytes() == original
    prepare(source_repository, state, output, targets[:1], "confirm-pages")
    prepare(source_repository, state, output, targets[:2], "cleanup-preview", "feature/a")
    assert not (state / "sites/github-pages/previews" / first).exists()
    assert (state / "sites/helios-jenya/previews" / first).is_dir()
    prepare(source_repository, state, output, targets[:1], "restore-pages")
    assert (state / "sites/github-pages/previews" / first).is_dir()
    assert (state / "sites/github-pages/previews" / second).is_dir()
    assert (state / "sites/github-pages/production/index.html").read_bytes() == original


def test_first_tag_publish_bootstraps_from_remote_main_on_detached_checkout(
    source_repository: Path, tmp_path: Path
) -> None:
    main_sha = run(source_repository, "git", "rev-parse", "main")
    run(source_repository, "git", "update-ref", "refs/remotes/origin/main", main_sha)
    run(source_repository, "git", "checkout", "--detach", "v1.0")
    run(source_repository, "git", "branch", "-D", "main")
    state = tmp_path / "state"
    state.mkdir()
    output = tmp_path / "output"
    output.mkdir()
    target: Target = {"id": "github-pages", "base_url": "https://example.test/lab/"}
    result = prepare(source_repository, state, output, [target], "version", version="v1.1")
    assert result["helios_action"] == "production"
    assert {directory.name for directory in (output / "pages").iterdir() if directory.is_dir()} == {
        "v1.0",
        "v1.1",
        "latest",
    }
    verify_local_site(output / "pages")
