"""Git adapter used to obtain reproducibility metadata."""

import subprocess
from pathlib import Path

from publication_pipeline.application.errors import SourceControlError
from publication_pipeline.application.models import SourceRevision
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha

_GIT_TIMEOUT_SECONDS = 15


class GitSourceControl:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def revision(self) -> SourceRevision:
        commit_sha = self._read_git_output("rev-parse", "--verify", "HEAD")
        branch = self._read_git_output("branch", "--show-current") or "detached"
        dirty = bool(self._read_git_output("status", "--porcelain"))
        try:
            return SourceRevision(
                commit_sha=CommitSha(commit_sha),
                branch=BranchName(branch),
                dirty=dirty,
            )
        except ValueError as error:
            raise SourceControlError("Git returned invalid revision metadata") from error

    def _read_git_output(self, *arguments: str) -> str:
        try:
            process = subprocess.run(
                ["git", *arguments],
                cwd=self._repository_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise SourceControlError(
                f"Git command exceeded {_GIT_TIMEOUT_SECONDS} seconds"
            ) from error
        except OSError as error:
            raise SourceControlError("Could not start Git command") from error
        if process.returncode != 0:
            detail = process.stderr.strip() or "no diagnostic output"
            raise SourceControlError(
                f"Git command failed with exit code {process.returncode}: {detail}"
            )
        return process.stdout.strip()
