import pytest

from publication_pipeline.application.errors import HealthcheckError
from publication_pipeline.application.models import HttpResponse
from publication_pipeline.application.verify_release import VerifyRelease, VerifyReleaseRequest


class StubHttpClient:
    def __init__(self, response: HttpResponse) -> None:
        self._response = response

    def fetch(self, url: str) -> HttpResponse:
        return self._response


def test_healthcheck_requires_status_and_all_markers() -> None:
    verifier = VerifyRelease(
        StubHttpClient(HttpResponse(status_code=200, body="control commit-123"))
    )

    result = verifier.execute(
        VerifyReleaseRequest(
            url="https://example.test/",
            expected_texts=("control", "commit-123"),
        )
    )

    assert result.status_code == 200
    assert result.attempts == 1


def test_healthcheck_fails_when_release_marker_is_missing() -> None:
    verifier = VerifyRelease(StubHttpClient(HttpResponse(status_code=200, body="old release")))

    with pytest.raises(HealthcheckError, match="expected-release"):
        verifier.execute(
            VerifyReleaseRequest(
                url="https://example.test/",
                expected_texts=("expected-release",),
            )
        )
