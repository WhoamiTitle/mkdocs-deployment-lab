from pathlib import Path

import pytest

from publication_pipeline.application.errors import PublicationError
from publication_pipeline.infrastructure.ssh_rsync_gateway import SshRsyncSettings
from scripts.verify_helios_resilience import _validate_sandbox_targets


def _settings(
    tmp_path: Path,
    *,
    deployment_root: str = ".deployments/mkdocs-deployment-lab-sandbox",
    public_path: str = "public_html/mkdocs-deployment-lab-sandbox",
) -> SshRsyncSettings:
    private_key = tmp_path / "key"
    known_hosts = tmp_path / "known_hosts"
    private_key.touch()
    known_hosts.touch()
    return SshRsyncSettings.create(
        host="helios.example.edu",
        user="student",
        port=2222,
        private_key=private_key,
        known_hosts=known_hosts,
        deployment_root=deployment_root,
        public_path=public_path,
    )


def test_resilience_guard_accepts_only_dedicated_sandbox(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    _validate_sandbox_targets(
        settings,
        "https://example.test/~student/mkdocs-deployment-lab-sandbox/",
    )


@pytest.mark.parametrize(
    ("deployment_root", "public_path", "base_url"),
    [
        (
            ".deployments/mkdocs-deployment-lab",
            "public_html/mkdocs-deployment-lab-sandbox",
            "https://example.test/~student/mkdocs-deployment-lab-sandbox/",
        ),
        (
            ".deployments/mkdocs-deployment-lab-sandbox",
            "public_html/mkdocs-deployment-lab",
            "https://example.test/~student/mkdocs-deployment-lab-sandbox/",
        ),
        (
            ".deployments/mkdocs-deployment-lab-sandbox",
            "public_html/mkdocs-deployment-lab-sandbox",
            "https://example.test/~student/mkdocs-deployment-lab/",
        ),
    ],
)
def test_resilience_guard_rejects_production_targets(
    tmp_path: Path,
    deployment_root: str,
    public_path: str,
    base_url: str,
) -> None:
    settings = _settings(
        tmp_path,
        deployment_root=deployment_root,
        public_path=public_path,
    )

    with pytest.raises(PublicationError):
        _validate_sandbox_targets(settings, base_url)
