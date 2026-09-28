from pathlib import Path

import pytest

from publication_pipeline.application.errors import InvalidArtifactError
from publication_pipeline.application.verify_offline_assets import VerifyOfflineAssets


def test_accepts_local_runtime_assets_and_external_anchors(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        """
        <link rel="stylesheet" href="assets/site.css">
        <script src="assets/site.js"></script>
        <a href="https://example.test/documentation">documentation</a>
        """,
        encoding="utf-8",
    )
    (tmp_path / "site.css").write_text(
        "@font-face { src: url('./font.woff2'); }",
        encoding="utf-8",
    )

    report = VerifyOfflineAssets().execute(tmp_path)

    assert report.external_assets == ()


def test_rejects_external_script_and_css_font(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        '<script src="https://cdn.example.test/app.js"></script>',
        encoding="utf-8",
    )
    (tmp_path / "site.css").write_text(
        "@font-face { src: url(//cdn.example.test/font.woff2); }",
        encoding="utf-8",
    )

    with pytest.raises(InvalidArtifactError) as captured:
        VerifyOfflineAssets().execute(tmp_path)

    message = str(captured.value)
    assert "app.js" in message
    assert "font.woff2" in message
