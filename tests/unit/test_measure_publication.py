import csv
from datetime import UTC
from pathlib import Path

from scripts.measure_publication import (
    _BUILD_FIELDS,
    BuildMeasurement,
    _append_csv,
    _normalized_base_url,
    parse_utc_datetime,
)


def test_parse_utc_datetime_normalizes_offset() -> None:
    parsed = parse_utc_datetime("2026-10-02T09:00:00+09:00")

    assert parsed.tzinfo is UTC
    assert parsed.isoformat() == "2026-10-02T00:00:00+00:00"


def test_normalized_base_url_preserves_repository_subpath() -> None:
    result = _normalized_base_url("https://example.test/project")

    assert result == "https://example.test/project/"


def test_append_csv_writes_stable_schema(tmp_path: Path) -> None:
    output = tmp_path / "measurements.csv"
    timestamp = parse_utc_datetime("2026-10-02T00:00:00Z")
    measurement = BuildMeasurement(
        environment="test-python",
        run=1,
        started_at_utc=timestamp,
        finished_at_utc=timestamp,
        duration_seconds=1.25,
        result="success",
        commit_sha="a" * 40,
        dirty=False,
        artifact_size_bytes=100,
        file_count=2,
        cache_condition="dependencies-preinstalled",
        notes="test",
    )

    _append_csv(output, _BUILD_FIELDS, measurement.as_csv_row())

    with output.open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows[0]["duration_seconds"] == "1.250000"
    assert rows[0]["artifact_size_bytes"] == "100"
