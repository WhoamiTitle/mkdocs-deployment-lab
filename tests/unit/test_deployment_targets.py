import json
from pathlib import Path

import pytest

from scripts.deployment_targets import main, resolve_targets

_CONFIG = Path(__file__).resolve().parents[2] / "config" / "deploy-targets.example.json"


def test_example_targets_use_separate_keys_and_shared_host_identity() -> None:
    targets = resolve_targets(_CONFIG.read_text(encoding="utf-8"))
    assert {target["user"] for target in targets} == {"s507353", "s505999"}
    assert len({target["key_secret"] for target in targets}) == 2
    assert {target["known_hosts_secret"] for target in targets} == {"HELIOS_KNOWN_HOSTS"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "../other"),
        ("user", "user; touch /tmp/file"),
        ("host", "-oProxyCommand=command"),
        ("port", True),
        ("port", "2222"),
        ("port", 0),
        ("public_path", "public_html"),
        ("public_path", "public_html/../lab1"),
        ("public_path", "/public_html/site"),
        ("public_path", "public_html//site"),
        ("public_path", "other/site"),
        ("deployment_root", "public_html/mkdocs-deployment-lab/releases"),
        ("base_url", "https://user:password@example.com/site/"),
        ("base_url", "https://example.com/site/?query=1"),
        ("base_url", "https://example.com/site"),
        ("key_secret", "private key contents"),
    ],
)
def test_rejects_unsafe_configuration(field: str, value: str | int | bool) -> None:
    targets = json.loads(_CONFIG.read_text(encoding="utf-8"))
    targets[0][field] = value
    with pytest.raises(ValueError):
        resolve_targets(json.dumps(targets))


def test_rejects_duplicate_destinations_with_different_ids() -> None:
    target = json.loads(_CONFIG.read_text(encoding="utf-8"))[0]
    with pytest.raises(ValueError, match="share"):
        resolve_targets(json.dumps([target, dict(target, id="duplicate")]))


def test_variable_defines_targets_and_target_selection_is_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = json.loads(_CONFIG.read_text(encoding="utf-8"))[1]
    output = tmp_path / "output"
    monkeypatch.setenv("DEPLOY_TARGETS", json.dumps([target]))
    monkeypatch.setenv("TARGET_ID", "helios-jenya")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    main()
    assert json.loads(output.read_text(encoding="utf-8").removeprefix("targets=")) == [target]
    monkeypatch.setenv("TARGET_ID", "missing")
    with pytest.raises(ValueError, match="does not exist"):
        main()


def test_missing_variable_does_not_fall_back_to_repository_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEPLOY_TARGETS", raising=False)
    with pytest.raises(ValueError, match="DEPLOY_TARGETS GitHub variable"):
        main()
