"""Verify version roots, aliases and previews against a prepared site artifact."""

import argparse
import json
from pathlib import Path
from urllib.parse import urljoin

from publication_pipeline.application.verify_release import VerifyRelease, VerifyReleaseRequest
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from publication_pipeline.infrastructure.urllib_http_client import UrllibHttpClient


def site_checks(site: Path) -> list[tuple[str, tuple[str, ...]]]:
    checks: list[tuple[str, tuple[str, ...]]] = []
    store = FilesystemReleaseArtifactStore()
    for metadata in sorted(site.rglob("release.json")):
        relative = metadata.parent.relative_to(site).as_posix()
        url = "./" if relative == "." else f"{relative}/"
        release = store.read(metadata.parent)
        checks.append((url, ("publication-site-control", release.marker)))
    versions_file = site / "versions.json"
    if versions_file.is_file():
        versions = json.loads(versions_file.read_text(encoding="utf-8"))
        latest = [entry["version"] for entry in versions if "latest" in entry["aliases"]]
        if len(latest) != 1:
            raise ValueError("Exactly one published version must own the latest alias")
        checks += [("./", ("latest/",)), ("latest/", (f"../{latest[0]}/",))]
        checks.append(("versions.json", tuple(entry["version"] for entry in versions)))
    if not checks:
        raise ValueError("Published site has no release metadata")
    return checks


def verify_local_site(site: Path) -> None:
    for url, texts in site_checks(site):
        file = site / (
            "index.html" if url == "./" else (f"{url}index.html" if url.endswith("/") else url)
        )
        html = file.read_text(encoding="utf-8")
        if any(text not in html for text in texts):
            raise ValueError(f"Missing version or release marker in {file}")
    for version in (
        json.loads((site / "versions.json").read_text(encoding="utf-8"))
        if (site / "versions.json").exists()
        else []
    ):
        if not (site / version["version"] / "search/search_index.json").is_file():
            raise ValueError("Each stable version must have a local search index")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--site-dir", required=True)
    args = parser.parse_args()
    site = Path(args.site_dir)
    verify_local_site(site)
    verifier = VerifyRelease(UrllibHttpClient())
    for relative, expected in site_checks(site):
        result = verifier.execute(
            VerifyReleaseRequest(
                url=urljoin(args.url, relative),
                expected_texts=expected,
                attempts=5,
                delay_seconds=5,
            )
        )
        print(json.dumps({"url": result.url, "status": result.status_code}))


if __name__ == "__main__":
    main()
