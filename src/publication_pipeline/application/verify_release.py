"""HTTP healthcheck for a published release."""

import time
from dataclasses import dataclass

from publication_pipeline.application.errors import HealthcheckError, HttpClientError
from publication_pipeline.application.models import HealthcheckResult
from publication_pipeline.application.ports import HttpClient


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyReleaseRequest:
    url: str
    expected_texts: tuple[str, ...]
    attempts: int = 1
    delay_seconds: float = 0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("Healthcheck attempts must be at least one")


class VerifyRelease:
    def __init__(self, http_client: HttpClient) -> None:
        self._http_client = http_client

    def execute(self, request: VerifyReleaseRequest) -> HealthcheckResult:
        last_problem = "request was not attempted"
        for attempt in range(1, request.attempts + 1):
            try:
                response = self._http_client.fetch(request.url)
                missing = tuple(
                    text for text in request.expected_texts if text not in response.body
                )
                if response.status_code == 200 and not missing:
                    return HealthcheckResult(
                        url=request.url,
                        status_code=response.status_code,
                        checked_texts=request.expected_texts,
                        attempts=attempt,
                    )
                if response.status_code != 200:
                    last_problem = f"HTTP status is {response.status_code}, expected 200"
                else:
                    last_problem = f"response does not contain: {', '.join(missing)}"
            except HttpClientError as error:
                last_problem = str(error)

            if attempt < request.attempts and request.delay_seconds > 0:
                time.sleep(request.delay_seconds)

        raise HealthcheckError(f"Healthcheck failed for {request.url}: {last_problem}")
