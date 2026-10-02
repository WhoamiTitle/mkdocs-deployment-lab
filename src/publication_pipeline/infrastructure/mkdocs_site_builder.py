"""MkDocs site-builder adapter."""

import subprocess
import sys
from pathlib import Path

from publication_pipeline.application.errors import SiteBuildError

_BUILD_TIMEOUT_SECONDS = 300


class MkDocsSiteBuilder:
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
        try:
            process = subprocess.run(
                command,
                cwd=self._repository_root,
                check=False,
                capture_output=True,
                text=True,
                timeout=_BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise SiteBuildError(
                f"MkDocs build exceeded {_BUILD_TIMEOUT_SECONDS} seconds"
            ) from error
        except OSError as error:
            raise SiteBuildError("Could not start MkDocs build") from error
        if process.returncode != 0:
            detail = process.stderr.strip() or process.stdout.strip() or "no diagnostic output"
            raise SiteBuildError(
                f"MkDocs build failed with exit code {process.returncode}: {detail}"
            )
