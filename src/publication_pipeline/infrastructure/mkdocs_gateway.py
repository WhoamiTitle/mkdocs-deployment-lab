"""MkDocs site-builder adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from publication_pipeline.application.errors import PublicationError


class MkDocsGateway:
    def __init__(self, repository_root: Path, config_file: Path) -> None:
        self._repository_root = repository_root
        self._config_file = config_file

    def build(self, destination: Path) -> None:
        command = [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--clean",
            "--config-file",
            str(self._config_file),
            "--site-dir",
            str(destination),
        ]
        process = subprocess.run(command, cwd=self._repository_root, check=False)
        if process.returncode != 0:
            raise PublicationError(f"MkDocs build failed with exit code {process.returncode}")
