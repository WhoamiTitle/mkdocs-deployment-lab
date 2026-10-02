"""Collect raw build and publication timing observations for the T4/P4 report."""

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from publication_pipeline.application.models import Release
from publication_pipeline.application.release_document import JsonValue, release_from_document
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from publication_pipeline.infrastructure.git_source_control import GitSourceControl

_CONTROL_TEXT = "publication-site-control"
_COMMAND_TIMEOUT_SECONDS = 300
_BUILD_FIELDS = (
    "environment",
    "run",
    "started_at_utc",
    "finished_at_utc",
    "duration_seconds",
    "result",
    "commit_sha",
    "dirty",
    "artifact_size_bytes",
    "file_count",
    "cache_condition",
    "notes",
)
_PUBLICATION_FIELDS = (
    "platform",
    "method",
    "run",
    "started_at_utc",
    "healthcheck_at_utc",
    "duration_seconds",
    "result",
    "commit_sha",
    "release_id",
    "release_built_at_utc",
    "url",
    "measurement_scope",
    "artifact_size_bytes",
    "file_count",
    "notes",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class BuildMeasurement:
    environment: str
    run: int
    started_at_utc: datetime
    finished_at_utc: datetime
    duration_seconds: float
    result: str
    commit_sha: str
    dirty: bool
    artifact_size_bytes: int
    file_count: int
    cache_condition: str
    notes: str

    def as_csv_row(self) -> dict[str, str]:
        return {
            "environment": self.environment,
            "run": str(self.run),
            "started_at_utc": _format_datetime(self.started_at_utc),
            "finished_at_utc": _format_datetime(self.finished_at_utc),
            "duration_seconds": _format_duration(self.duration_seconds),
            "result": self.result,
            "commit_sha": self.commit_sha,
            "dirty": str(self.dirty).lower(),
            "artifact_size_bytes": str(self.artifact_size_bytes),
            "file_count": str(self.file_count),
            "cache_condition": self.cache_condition,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True, kw_only=True)
class PublicationMeasurement:
    platform: str
    method: str
    run: int
    started_at_utc: datetime
    healthcheck_at_utc: datetime
    duration_seconds: float
    result: str
    commit_sha: str
    release_id: str
    release_built_at_utc: datetime
    url: str
    measurement_scope: str
    artifact_size_bytes: int | None
    file_count: int | None
    notes: str

    def as_csv_row(self) -> dict[str, str]:
        return {
            "platform": self.platform,
            "method": self.method,
            "run": str(self.run),
            "started_at_utc": _format_datetime(self.started_at_utc),
            "healthcheck_at_utc": _format_datetime(self.healthcheck_at_utc),
            "duration_seconds": _format_duration(self.duration_seconds),
            "result": self.result,
            "commit_sha": self.commit_sha,
            "release_id": self.release_id,
            "release_built_at_utc": _format_datetime(self.release_built_at_utc),
            "url": self.url,
            "measurement_scope": self.measurement_scope,
            "artifact_size_bytes": _format_optional_int(self.artifact_size_bytes),
            "file_count": _format_optional_int(self.file_count),
            "notes": self.notes,
        }


class _QuietRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, message_format: str, *arguments: str) -> None:
        return


@dataclass(slots=True, init=False)
class ParsedMeasurementArguments:
    command: str
    repository_root: str
    runs: int
    run_start: int
    build_output: str
    publication_output: str
    platform: str
    method: str
    run: int
    url: str
    expected_commit: str
    started_at_utc: str
    measurement_scope: str
    output: str
    attempts: int
    delay_seconds: float


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _create_parser()
    parsed_arguments = ParsedMeasurementArguments()
    parser.parse_args(arguments, namespace=parsed_arguments)
    if parsed_arguments.command == "timestamp":
        print(_format_datetime(datetime.now(UTC)))
        return 0
    if parsed_arguments.command == "local":
        return _measure_local(parsed_arguments)
    if parsed_arguments.command == "observe":
        return _observe_publication(parsed_arguments)
    parser.error(f"Unknown command: {parsed_arguments.command}")


def _create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="measure-publication")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("timestamp", help="print an ISO 8601 UTC start timestamp")

    local = subparsers.add_parser(
        "local",
        help="measure strict builds and local atomic publications",
    )
    local.add_argument("--repository-root", default=".")
    local.add_argument("--runs", type=int, default=5)
    local.add_argument("--run-start", type=int, default=1)
    local.add_argument(
        "--build-output",
        default="evidence/measurements/build-times.csv",
    )
    local.add_argument(
        "--publication-output",
        default="evidence/measurements/deployment-times.csv",
    )

    observe = subparsers.add_parser(
        "observe",
        help="wait until a published site exposes the expected commit",
    )
    observe.add_argument("--platform", required=True)
    observe.add_argument("--method", required=True)
    observe.add_argument("--run", type=int, required=True)
    observe.add_argument("--url", required=True)
    observe.add_argument("--expected-commit", required=True)
    observe.add_argument("--started-at-utc", required=True)
    observe.add_argument(
        "--measurement-scope",
        choices=(
            "push-start-to-healthcheck",
            "workflow-dispatch-to-healthcheck",
        ),
        default="push-start-to-healthcheck",
    )
    observe.add_argument("--output", default="evidence/measurements/deployment-times.csv")
    observe.add_argument("--attempts", type=int, default=90)
    observe.add_argument("--delay-seconds", type=float, default=2.0)
    return parser


def _measure_local(arguments: ParsedMeasurementArguments) -> int:
    repository_root = Path(arguments.repository_root).resolve()
    runs = arguments.runs
    run_start = arguments.run_start
    if runs < 1:
        raise ValueError("runs must be at least one")
    if run_start < 1:
        raise ValueError("run-start must be at least one")

    build_output = _resolve_output(repository_root, arguments.build_output)
    publication_output = _resolve_output(repository_root, arguments.publication_output)
    revision = GitSourceControl(repository_root).revision()
    environment = _environment_name()
    build_measurements: list[BuildMeasurement] = []
    publication_measurements: list[PublicationMeasurement] = []

    for offset in range(runs):
        run = run_start + offset
        with tempfile.TemporaryDirectory(prefix="mkdocs-publication-experiment-") as temporary:
            temporary_root = Path(temporary)
            site_directory = temporary_root / "site"
            deployment_root = temporary_root / "deployment"
            public_path = temporary_root / "public-site"
            with _serve_directory(public_path) as base_url:
                build_started = datetime.now(UTC)
                build_timer = time.perf_counter_ns()
                _run_command(
                    (
                        sys.executable,
                        "-m",
                        "publication_pipeline",
                        "build",
                        "--repository-root",
                        str(repository_root),
                        "--site-dir",
                        str(site_directory),
                    ),
                    cwd=repository_root,
                    environment={"SITE_URL": base_url},
                )
                build_duration = _elapsed_seconds(build_timer)
                build_finished = datetime.now(UTC)
                release = FilesystemReleaseArtifactStore().read(site_directory)
                artifact_size, file_count = _measure_artifact(site_directory)
                build_measurement = BuildMeasurement(
                    environment=environment,
                    run=run,
                    started_at_utc=build_started,
                    finished_at_utc=build_finished,
                    duration_seconds=build_duration,
                    result="success",
                    commit_sha=release.commit_sha,
                    dirty=release.dirty,
                    artifact_size_bytes=artifact_size,
                    file_count=file_count,
                    cache_condition=(
                        "dependencies-preinstalled; clean-site; filesystem-cache-uncontrolled"
                    ),
                    notes="mkdocs --strict --clean through publication_pipeline",
                )
                build_measurements.append(build_measurement)

                publication_started = datetime.now(UTC)
                publication_timer = time.perf_counter_ns()
                _run_command(
                    (
                        sys.executable,
                        "-m",
                        "publication_pipeline",
                        "deploy-local",
                        "--site-dir",
                        str(site_directory),
                        "--deployment-root",
                        str(deployment_root),
                        "--public-path",
                        str(public_path),
                    ),
                    cwd=repository_root,
                )
                _run_command(
                    (
                        sys.executable,
                        "-m",
                        "publication_pipeline",
                        "healthcheck",
                        "--url",
                        base_url,
                        "--release-file",
                        str(site_directory / "release.json"),
                        "--attempts",
                        "1",
                    ),
                    cwd=repository_root,
                )
                publication_duration = _elapsed_seconds(publication_timer)
                healthcheck_at = datetime.now(UTC)
                publication_measurement = PublicationMeasurement(
                    platform="local",
                    method="atomic-filesystem-symlink",
                    run=run,
                    started_at_utc=publication_started,
                    healthcheck_at_utc=healthcheck_at,
                    duration_seconds=publication_duration,
                    result="success",
                    commit_sha=release.commit_sha,
                    release_id=release.release_id,
                    release_built_at_utc=release.built_at,
                    url=base_url,
                    measurement_scope="deploy-command-to-healthcheck",
                    artifact_size_bytes=artifact_size,
                    file_count=file_count,
                    notes="control baseline; not a substitute for Helios",
                )
                publication_measurements.append(publication_measurement)
                print(
                    json.dumps(
                        {
                            "run": run,
                            "build_seconds": round(build_duration, 6),
                            "publication_seconds": round(publication_duration, 6),
                            "commit_sha": release.commit_sha,
                            "dirty": release.dirty,
                        },
                        ensure_ascii=False,
                    )
                )

    if revision.commit_sha != release.commit_sha:
        raise RuntimeError("source revision changed during the experiment")
    for build_result in build_measurements:
        _append_csv(build_output, _BUILD_FIELDS, build_result.as_csv_row())
    for publication_result in publication_measurements:
        _append_csv(
            publication_output,
            _PUBLICATION_FIELDS,
            publication_result.as_csv_row(),
        )
    return 0


def _observe_publication(arguments: ParsedMeasurementArguments) -> int:
    attempts = arguments.attempts
    delay_seconds = arguments.delay_seconds
    run = arguments.run
    if attempts < 1:
        raise ValueError("attempts must be at least one")
    if delay_seconds < 0:
        raise ValueError("delay-seconds cannot be negative")
    if run < 1:
        raise ValueError("run must be at least one")

    started_at = parse_utc_datetime(arguments.started_at_utc)
    expected_commit = arguments.expected_commit
    base_url = _normalized_base_url(arguments.url)
    last_problem = "publication was not checked"

    for attempt in range(1, attempts + 1):
        try:
            release = _fetch_release(base_url)
            if release.commit_sha != expected_commit:
                last_problem = f"published commit is still {release.commit_sha}"
            elif release.built_at < started_at:
                last_problem = f"published release {release.release_id} predates observation start"
            else:
                _verify_root_page(base_url, expected_commit)
                healthcheck_at = datetime.now(UTC)
                measurement = PublicationMeasurement(
                    platform=arguments.platform,
                    method=arguments.method,
                    run=run,
                    started_at_utc=started_at,
                    healthcheck_at_utc=healthcheck_at,
                    duration_seconds=(healthcheck_at - started_at).total_seconds(),
                    result="success",
                    commit_sha=expected_commit,
                    release_id=release.release_id,
                    release_built_at_utc=release.built_at,
                    url=base_url,
                    measurement_scope=arguments.measurement_scope,
                    artifact_size_bytes=None,
                    file_count=None,
                    notes=f"release.json and root marker matched; attempts={attempt}",
                )
                output = Path(arguments.output).resolve()
                _append_csv(output, _PUBLICATION_FIELDS, measurement.as_csv_row())
                print(json.dumps(measurement.as_csv_row(), ensure_ascii=False, indent=2))
                return 0
        except (OSError, ValueError, json.JSONDecodeError) as error:
            last_problem = str(error)
        if attempt < attempts and delay_seconds > 0:
            time.sleep(delay_seconds)

    raise RuntimeError(
        f"publication did not expose commit {expected_commit} after {attempts} attempts: "
        f"{last_problem}"
    )


def parse_utc_datetime(raw_value: str) -> datetime:
    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a UTC offset")
    return parsed.astimezone(UTC)


def _fetch_release(base_url: str) -> Release:
    release_url = urljoin(base_url, "release.json")
    request = Request(
        _cache_busted_url(release_url),
        headers={"Cache-Control": "no-cache", "User-Agent": "publication-experiment/0.1"},
    )
    with urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise OSError(f"release metadata returned HTTP {response.status}")
        raw_value: JsonValue = json.loads(response.read().decode("utf-8"))
    return release_from_document(raw_value)


def _verify_root_page(base_url: str, expected_commit: str) -> None:
    request = Request(
        _cache_busted_url(base_url),
        headers={"Cache-Control": "no-cache", "User-Agent": "publication-experiment/0.1"},
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8", errors="replace")
        if response.status != 200:
            raise OSError(f"root page returned HTTP {response.status}")
    missing = [text for text in (_CONTROL_TEXT, expected_commit) if text not in body]
    if missing:
        raise ValueError(f"root page does not contain: {', '.join(missing)}")


def _normalized_base_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("url must be an absolute HTTP(S) URL")
    return raw_url.rstrip("/") + "/"


def _cache_busted_url(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.append(("publication_probe", str(time.time_ns())))
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


@contextmanager
def _serve_directory(directory: Path) -> Iterator[str]:
    handler = cast(
        type[BaseHTTPRequestHandler],
        partial(_QuietRequestHandler, directory=str(directory)),
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    host, port = cast(tuple[str, int], server.server_address)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> None:
    process_environment = os.environ.copy()
    if environment is not None:
        process_environment.update(environment)
    try:
        process = subprocess.run(
            command,
            cwd=cwd,
            env=process_environment,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=_COMMAND_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"command exceeded {_COMMAND_TIMEOUT_SECONDS} seconds: {' '.join(command)}"
        ) from error
    except OSError as error:
        raise RuntimeError(f"could not start command: {' '.join(command)}") from error
    if process.returncode != 0:
        raise RuntimeError(
            f"command failed with exit code {process.returncode}: {' '.join(command)}\n"
            f"{process.stdout[-4000:]}"
        )


def _measure_artifact(site_directory: Path) -> tuple[int, int]:
    files = tuple(path for path in site_directory.rglob("*") if path.is_file())
    return sum(path.stat().st_size for path in files), len(files)


def _append_csv(path: Path, fieldnames: tuple[str, ...], row: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    if not write_header:
        with path.open(encoding="utf-8", newline="") as source:
            existing_header = next(csv.reader(source), None)
        if existing_header != list(fieldnames):
            raise ValueError(f"unexpected CSV header in {path}")
    with path.open("a", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=fieldnames, lineterminator="\n")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _resolve_output(repository_root: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    return path.resolve() if path.is_absolute() else (repository_root / path).resolve()


def _environment_name() -> str:
    python_version = platform.python_version()
    return f"{platform.system().lower()}-{platform.machine().lower()}-python-{python_version}"


def _elapsed_seconds(started_at_ns: int) -> float:
    return (time.perf_counter_ns() - started_at_ns) / 1_000_000_000


def _format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _format_duration(value: float) -> str:
    return f"{value:.6f}"


def _format_optional_int(value: int | None) -> str:
    return "" if value is None else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
