"""HTTP healthcheck for a published release."""

from __future__ import annotations

import time

from publication_pipeline.application.errors import HealthcheckError
from publication_pipeline.application.models import HealthcheckResult
from publication_pipeline.application.ports import HttpClient


class VerifyRelease:
    def __init__(self, http_client: HttpClient) -> None:
        self._http_client = http_client

    def execute(
        self,
        url: str,
        expected_texts: tuple[str, ...],
        *,
        attempts: int = 1,
        delay_seconds: float = 0,
    ) -> HealthcheckResult:
        if attempts < 1:
            raise ValueError("Healthcheck attempts must be at least one")
        last_problem = "request was not attempted"
        for attempt in range(1, attempts + 1):
            try:
                response = self._http_client.get(url)
                missing = tuple(text for text in expected_texts if text not in response.body)
                if response.status_code == 200 and not missing:
                    return HealthcheckResult(
                        url=url,
                        status_code=response.status_code,
                        checked_texts=expected_texts,
                        attempts=attempt,
                    )
                if response.status_code != 200:
                    last_problem = f"HTTP status is {response.status_code}, expected 200"
                else:
                    last_problem = f"response does not contain: {', '.join(missing)}"
            except OSError as error:
                last_problem = str(error)

            if attempt < attempts and delay_seconds > 0:
                time.sleep(delay_seconds)

        raise HealthcheckError(f"Healthcheck failed for {url}: {last_problem}")
