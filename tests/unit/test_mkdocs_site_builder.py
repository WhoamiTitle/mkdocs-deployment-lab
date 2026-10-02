import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from publication_pipeline.application.errors import SiteBuildError
from publication_pipeline.infrastructure.mkdocs_site_builder import MkDocsSiteBuilder


def test_mkdocs_builder_runs_strict_clean_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess[str](args=[], returncode=0, stdout="", stderr="")
    run = Mock(return_value=completed)
    monkeypatch.setattr(subprocess, "run", run)
    config_file = tmp_path / "mkdocs.yml"
    destination = tmp_path / "site"

    MkDocsSiteBuilder(tmp_path, config_file).build(destination)

    command = run.call_args.args[0]
    assert command[1:4] == ["-m", "mkdocs", "build"]
    assert "--strict" in command
    assert "--clean" in command
    assert command[-2:] == ["--site-dir", str(destination)]
    assert run.call_args.kwargs["cwd"] == tmp_path
    assert run.call_args.kwargs["timeout"] == 300


def test_mkdocs_builder_translates_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = subprocess.CompletedProcess[str](
        args=[],
        returncode=1,
        stdout="",
        stderr="broken configuration",
    )
    monkeypatch.setattr(subprocess, "run", Mock(return_value=completed))

    with pytest.raises(SiteBuildError, match="broken configuration"):
        MkDocsSiteBuilder(tmp_path, tmp_path / "mkdocs.yml").build(tmp_path / "site")
