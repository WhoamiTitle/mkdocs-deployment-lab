import subprocess
from pathlib import Path

from publication_pipeline.infrastructure.git_source_control import GitSourceControl


def _run_git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def test_git_source_control_reads_revision_branch_and_dirty_state(tmp_path: Path) -> None:
    _run_git(tmp_path, "init", "--initial-branch", "main")
    (tmp_path / "tracked.txt").write_text("initial\n", encoding="utf-8")
    _run_git(tmp_path, "add", "tracked.txt")
    _run_git(
        tmp_path,
        "-c",
        "user.name=Test User",
        "-c",
        "user.email=test@example.test",
        "commit",
        "-m",
        "initial",
    )

    clean_revision = GitSourceControl(tmp_path).revision()
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    dirty_revision = GitSourceControl(tmp_path).revision()

    assert len(clean_revision.commit_sha) == 40
    assert clean_revision.branch == "main"
    assert clean_revision.dirty is False
    assert dirty_revision.commit_sha == clean_revision.commit_sha
    assert dirty_revision.dirty is True
