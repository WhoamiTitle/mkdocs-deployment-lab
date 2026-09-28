"""Git adapter used to obtain reproducibility metadata."""

from __future__ import annotations

import subprocess
from pathlib import Path

from publication_pipeline.application.models import SourceRevision


class GitGateway:
    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def revision(self) -> SourceRevision:
        commit_sha = self._read("rev-parse", "--verify", "HEAD") or "uncommitted"
        branch = self._read("branch", "--show-current") or "local"
        dirty = bool(self._read("status", "--porcelain"))
        return SourceRevision(commit_sha=commit_sha, branch=branch, dirty=dirty)

    def _read(self, *arguments: str) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=self._repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            return ""
        return process.stdout.strip()
