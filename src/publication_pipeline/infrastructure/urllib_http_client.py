"""Small standard-library HTTP adapter for deployment checks."""

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from publication_pipeline.application.errors import HttpClientError
from publication_pipeline.application.models import HttpResponse


class UrllibHttpClient:
    def __init__(self, *, timeout_seconds: float = 10) -> None:
        self._timeout_seconds = timeout_seconds

    def fetch(self, url: str) -> HttpResponse:
        request = Request(url, headers={"User-Agent": "publication-pipeline-healthcheck/0.1"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8", errors="replace")
                return HttpResponse(status_code=response.status, body=body)
        except HTTPError as error:
            try:
                body = error.read().decode("utf-8", errors="replace")
            except OSError as body_error:
                raise HttpClientError(
                    f"Cannot read HTTP error response for {url}: {body_error}"
                ) from body_error
            return HttpResponse(status_code=error.code, body=body)
        except OSError as error:
            raise HttpClientError(f"HTTP request failed for {url}: {error}") from error
