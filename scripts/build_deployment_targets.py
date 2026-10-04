"""Build all target-specific artifacts before any SSH deployment starts."""

import os
import subprocess
import sys
from pathlib import Path

from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from scripts.deployment_targets import resolve_targets


def main() -> None:
    targets = resolve_targets(os.environ["DEPLOY_TARGETS"])
    branch = os.environ["GITHUB_REF_NAME"]
    is_production = os.environ["GITHUB_REF"] == "refs/heads/main"
    for target in targets:
        url = str(target["base_url"])
        if not is_production:
            url = f"{url}previews/{BranchSlug.from_branch(BranchName(branch)).value}/"
        destination = Path("site/targets") / str(target["id"])
        destination.mkdir(parents=True, exist_ok=True)
        environment = dict(os.environ, SITE_URL=url)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "publication_pipeline",
                    "build",
                    "--site-dir",
                    str(destination),
                ],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except subprocess.CalledProcessError as error:
            print(error.stderr, file=sys.stderr)
            raise
        print(result.stdout, end="")
        (destination / "build-receipt.json").write_text(result.stdout, encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-m",
                "publication_pipeline",
                "offline-check",
                "--site-dir",
                str(destination),
            ],
            check=True,
            timeout=60,
        )


if __name__ == "__main__":
    main()
