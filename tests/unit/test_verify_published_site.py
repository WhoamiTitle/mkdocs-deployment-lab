import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from publication_pipeline.application.errors import HealthcheckError
from publication_pipeline.application.models import HttpResponse, Release
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from scripts.verify_published_site import verify_remote_site


class SequenceHttpClient:
    def __init__(self, responses: list[HttpResponse]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def fetch(self, url: str) -> HttpResponse:
        self.urls.append(url)
        index = min(len(self.urls) - 1, len(self.responses) - 1)
        return self.responses[index]


class FakeClock:
    def __init__(self) -> None:
        self.seconds = 0.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.seconds

    def pause(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.seconds += seconds


@pytest.fixture
def published_site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        "<html><head></head><body>publication-site-control</body></html>",
        encoding="utf-8",
    )
    release = Release(
        release_id=ReleaseId("release-1"),
        commit_sha=CommitSha("a" * 40),
        branch=BranchName("main"),
        built_at=UtcDatetime(datetime(2026, 10, 5, tzinfo=UTC)),
        dirty=False,
    )
    FilesystemReleaseArtifactStore().write(site, release)
    return site


def test_pages_healthcheck_waits_for_expected_release(
    published_site: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current_html = (published_site / "index.html").read_text(encoding="utf-8")
    client = SequenceHttpClient(
        [HttpResponse(200, "publication-site-control old release"), HttpResponse(200, current_html)]
    )
    clock = FakeClock()

    verify_remote_site(
        published_site,
        "https://example.test/lab/",
        client,
        wait_seconds=30,
        clock=clock.now,
        pause=clock.pause,
    )

    assert clock.sleeps == [10]
    assert len(client.urls) == 2
    probes = [parse_qs(urlsplit(url).query)["publication_probe"] for url in client.urls]
    assert probes[0] != probes[1]
    assert all(urlsplit(url).path == "/lab/" for url in client.urls)
    output = capsys.readouterr()
    assert json.loads(output.out)["status"] == 200
    assert "Waiting for published site" in output.err


def test_pages_healthcheck_uses_one_bounded_deadline(published_site: Path) -> None:
    client = SequenceHttpClient([HttpResponse(200, "old release")])
    clock = FakeClock()

    with pytest.raises(HealthcheckError, match="within 25s"):
        verify_remote_site(
            published_site,
            "https://example.test/lab/",
            client,
            wait_seconds=25,
            clock=clock.now,
            pause=clock.pause,
        )

    assert clock.sleeps == [10, 10, 5]
    assert len(client.urls) == 4


def test_pages_healthcheck_shares_deadline_across_all_urls(
    published_site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scripts.verify_published_site.verify_local_site", lambda _: None)
    monkeypatch.setattr(
        "scripts.verify_published_site.site_checks",
        lambda _: [("./", ("root-new",)), ("v1.1/", ("version-new",))],
    )
    client = SequenceHttpClient(
        [
            HttpResponse(200, "root-old"),
            HttpResponse(200, "root-new"),
            HttpResponse(200, "version-old"),
            HttpResponse(200, "root-new"),
            HttpResponse(200, "version-old"),
        ]
    )
    clock = FakeClock()

    with pytest.raises(HealthcheckError, match="within 15s"):
        verify_remote_site(
            published_site,
            "https://example.test/lab/",
            client,
            wait_seconds=15,
            clock=clock.now,
            pause=clock.pause,
        )

    assert clock.sleeps == [10, 5]
    assert [urlsplit(url).path for url in client.urls] == [
        "/lab/",
        "/lab/",
        "/lab/v1.1/",
        "/lab/",
        "/lab/v1.1/",
    ]


def test_default_healthcheck_keeps_original_url(published_site: Path) -> None:
    client = SequenceHttpClient(
        [HttpResponse(200, (published_site / "index.html").read_text(encoding="utf-8"))]
    )

    verify_remote_site(published_site, "https://example.test/lab/", client)

    assert client.urls == ["https://example.test/lab/"]
