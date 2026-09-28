"""Validate that a built site has no externally hosted runtime assets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from publication_pipeline.application.errors import InvalidArtifactError

_EXTERNAL_PREFIXES = ("http://", "https://", "//")
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(?P<url>[^)'\"]+)\1\s*\)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ExternalAsset:
    source_file: Path
    element: str
    url: str


@dataclass(frozen=True, slots=True)
class OfflineAssetReport:
    scanned_html_files: int
    scanned_css_files: int
    external_assets: tuple[ExternalAsset, ...]


class VerifyOfflineAssets:
    def execute(self, site_directory: Path) -> OfflineAssetReport:
        if not site_directory.is_dir():
            raise InvalidArtifactError(f"Site directory does not exist: {site_directory}")

        external_assets: list[ExternalAsset] = []
        html_files = sorted(site_directory.rglob("*.html"))
        css_files = sorted(site_directory.rglob("*.css"))
        for html_file in html_files:
            parser = _RuntimeAssetParser(html_file)
            parser.feed(html_file.read_text(encoding="utf-8"))
            external_assets.extend(parser.external_assets)
        for css_file in css_files:
            css = css_file.read_text(encoding="utf-8", errors="replace")
            for match in _CSS_URL.finditer(css):
                url = match.group("url").strip()
                if _is_external(url):
                    external_assets.append(ExternalAsset(css_file, "css:url", url))

        report = OfflineAssetReport(
            scanned_html_files=len(html_files),
            scanned_css_files=len(css_files),
            external_assets=tuple(external_assets),
        )
        if report.external_assets:
            details = ", ".join(
                f"{asset.source_file}:{asset.element}={asset.url}"
                for asset in report.external_assets
            )
            raise InvalidArtifactError(f"External runtime assets found: {details}")
        return report


class _RuntimeAssetParser(HTMLParser):
    def __init__(self, source_file: Path) -> None:
        super().__init__(convert_charrefs=True)
        self._source_file = source_file
        self.external_assets: list[ExternalAsset] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value for name, value in attrs if value is not None}
        candidate_urls: list[tuple[str, str]] = []
        if tag == "script" and "src" in values:
            candidate_urls.append(("script:src", values["src"]))
        elif tag == "link" and "href" in values:
            relations = set(values.get("rel", "").lower().split())
            if relations.intersection(
                {"stylesheet", "icon", "preload", "modulepreload", "manifest"}
            ):
                candidate_urls.append(("link:href", values["href"]))
        elif tag in {"img", "source", "video", "audio", "iframe"} and "src" in values:
            candidate_urls.append((f"{tag}:src", values["src"]))

        for element, url in candidate_urls:
            if _is_external(url):
                self.external_assets.append(ExternalAsset(self._source_file, element, url))


def _is_external(url: str) -> bool:
    return url.strip().lower().startswith(_EXTERNAL_PREFIXES)
