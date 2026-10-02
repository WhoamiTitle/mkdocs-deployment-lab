import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from publication_pipeline.infrastructure.urllib_http_client import UrllibHttpClient


class LocalRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthy":
            body = "publication-site-control"
            self.send_response(200)
        else:
            body = "missing"
            self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))


@contextmanager
def _http_server() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_urllib_http_client_fetches_success_and_http_error_responses() -> None:
    with _http_server() as base_url:
        client = UrllibHttpClient(timeout_seconds=2)

        healthy = client.fetch(f"{base_url}/healthy")
        missing = client.fetch(f"{base_url}/missing")

    assert healthy.status_code == 200
    assert healthy.body == "publication-site-control"
    assert missing.status_code == 404
    assert missing.body == "missing"
