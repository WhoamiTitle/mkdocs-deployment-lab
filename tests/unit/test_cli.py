import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from publication_pipeline.application.models import Release
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from publication_pipeline.main import main
from publication_pipeline.presentation.cli import parse_cli_arguments


@pytest.mark.parametrize("root_option", ("--deployment-root", "--state-root"))
def test_local_deployment_root_accepts_new_and_legacy_flags(root_option: str) -> None:
    arguments = parse_cli_arguments(
        [
            "deploy-local",
            "--site-dir",
            "site",
            root_option,
            ".local-deploy/state",
            "--public-path",
            ".local-deploy/public",
        ]
    )

    assert arguments.deployment_root == ".local-deploy/state"


def test_cli_dispatches_branch_slug(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main(["branch-slug", "--branch", "Feature/Отчёт 2026"])

    assert exit_code == 0
    assert capsys.readouterr().out.startswith("feature-2026-")


def test_cli_dispatches_offline_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "index.html").write_text(
        '<script src="assets/application.js"></script>',
        encoding="utf-8",
    )

    exit_code = main(["offline-check", "--site-dir", str(tmp_path)])

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["scanned_html_files"] == 1
    assert document["external_assets"] == 0


def test_cli_maps_domain_validation_error_to_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["branch-slug", "--branch", "  "])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Branch name must be non-blank" in captured.err


def test_cli_dispatches_local_deployment(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    site_directory = tmp_path / "site"
    site_directory.mkdir()
    (site_directory / "index.html").write_text(
        "<html><head></head><body>ready</body></html>",
        encoding="utf-8",
    )
    release = Release(
        release_id="abcdef123456-20261002T010203Z",
        commit_sha="abcdef1234567890",
        branch="main",
        built_at=datetime(2026, 10, 2, 1, 2, 3, tzinfo=UTC),
        dirty=False,
    )
    FilesystemReleaseArtifactStore().write(site_directory, release)
    deployment_root = tmp_path / "deployments"
    public_path = tmp_path / "public"

    exit_code = main(
        [
            "deploy-local",
            "--site-dir",
            str(site_directory),
            "--deployment-root",
            str(deployment_root),
            "--public-path",
            str(public_path),
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["release_id"] == release.release_id
    assert (public_path / "index.html").is_file()
