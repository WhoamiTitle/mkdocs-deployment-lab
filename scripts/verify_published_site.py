"""Verify version roots, aliases and previews against a prepared site artifact."""

import argparse
import json
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

from publication_pipeline.application.errors import HealthcheckError
from publication_pipeline.application.models import HealthcheckResult
from publication_pipeline.application.ports import HttpClient
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


def verify_remote_site(
    site: Path,
    base_url: str,
    http_client: HttpClient,
    *,
    wait_seconds: int = 0,
    poll_seconds: float = 10,
    clock: Callable[[], float] = time.monotonic,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    if wait_seconds < 0 or poll_seconds <= 0:
        raise ValueError("Healthcheck wait must be nonnegative and poll interval positive")
    verify_local_site(site)
    verifier = VerifyRelease(http_client)
    deadline = clock() + wait_seconds
    while True:
        results: list[HealthcheckResult] = []
        try:
            for relative, expected in site_checks(site):
                address = urljoin(base_url, relative)
                if wait_seconds:
                    parts = urlsplit(address)
                    query = f"{parts.query}&" if parts.query else ""
                    address = urlunsplit(
                        (
                            parts.scheme,
                            parts.netloc,
                            parts.path,
                            f"{query}publication_probe={uuid.uuid4().hex}",
                            parts.fragment,
                        )
                    )
                results.append(
                    verifier.execute(
                        VerifyReleaseRequest(
                            url=address,
                            expected_texts=expected,
                            attempts=1 if wait_seconds else 5,
                            delay_seconds=0 if wait_seconds else 5,
                        )
                    )
                )
        except HealthcheckError as error:
            remaining = deadline - clock()
            if wait_seconds == 0:
                raise
            if remaining <= 0:
                raise HealthcheckError(
                    f"Published site did not become ready within {wait_seconds}s: {error}"
                ) from error
            print(
                f"Waiting for published site ({remaining:.0f}s left): {error}",
                file=sys.stderr,
                flush=True,
            )
            pause(min(poll_seconds, remaining))
            continue
        for result in results:
            print(json.dumps({"url": result.url, "status": result.status_code}))
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--site-dir", required=True)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    verify_remote_site(
        Path(args.site_dir),
        args.url,
        UrllibHttpClient(),
        wait_seconds=args.wait_seconds,
    )


if __name__ == "__main__":
    main()
