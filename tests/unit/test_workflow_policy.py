import re
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (_REPOSITORY_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _job(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        workflow,
    )
    assert match is not None, f"Workflow has no {name!r} job"
    return match.group(0)


def test_publish_jobs_require_embedded_quality_gate() -> None:
    workflow = _workflow("publish.yml")

    assert "run: make check" in _job(workflow, "quality")
    assert "needs: quality" in _job(workflow, "publish")
    assert "uses: ./.github/workflows/site-operation.yml" in _job(workflow, "publish")
    workflow = _workflow("site-operation.yml")
    for job_name in ("deploy-helios-production", "deploy-helios-preview"):
        deployment = _job(workflow, job_name)
        assert "needs: prepare" in deployment
        assert "fail-fast: false" in deployment
        assert "publication_pipeline build" not in deployment
        assert "actions/download-artifact@" in deployment


def test_workflows_install_dependencies_from_uv_lock() -> None:
    for workflow_name in (
        "ci.yml",
        "site-operation.yml",
        "helios-resilience.yml",
        "publish.yml",
        "rollback.yml",
    ):
        workflow = _workflow(workflow_name)
        assert "uv sync --locked" in workflow
        assert "requirements.txt" not in workflow


def test_production_deploy_and_rollback_share_concurrency_group() -> None:
    production = _job(_workflow("site-operation.yml"), "deploy-helios-production")
    rollback = _job(_workflow("rollback.yml"), "rollback")

    for job in (production, rollback):
        assert "group: helios-production-${{ matrix.target.id }}" in job
        assert "cancel-in-progress: false" in job


def test_preview_deploy_and_cleanup_share_branch_concurrency_group() -> None:
    preview = _job(_workflow("site-operation.yml"), "deploy-helios-preview")
    cleanup = _job(_workflow("site-operation.yml"), "cleanup-preview")

    assert "group: helios-preview-${{ matrix.target.id }}-${{ inputs.name }}" in preview
    assert "helios-preview-${{ matrix.target.id }}-${{ inputs.name }}" in cleanup
    for job in (preview, cleanup):
        assert "cancel-in-progress: false" in job


def test_rollback_workflows_verify_restored_release_identifier() -> None:
    publish = _workflow("site-operation.yml")
    rollback = _workflow("rollback.yml")

    for workflow in (publish, rollback):
        assert 'tee "$RUNNER_TEMP/helios-rollback.json"' in workflow
        assert '--expected-text "deployment-marker:${release_id}:"' in workflow


def test_pages_state_mutations_are_serialized_and_delivery_has_no_git_write() -> None:
    for name in ("publish.yml", "set-latest.yml", "rollback-pages.yml", "cleanup-preview.yml"):
        workflow = _workflow(name)
        assert "group: site-publication" in workflow
        assert "cancel-in-progress: false" in workflow
    workflow = _workflow("site-operation.yml")
    assert "contents: write" in _job(workflow, "prepare")
    assert "contents: write" in _job(workflow, "recover-pages-state")
    assert "contents: write" in _job(workflow, "confirm-pages-state")
    pages = _job(workflow, "deploy-pages")
    assert "contents: read" in pages
    assert "contents: write" not in pages
    assert "scripts.verify_published_site" in pages
    assert "timeout-minutes: 50" in pages
    assert pages.count("--wait-seconds 720") == 2
    assert "artifacts/previous-pages/" in pages
    assert "actions/deploy-pages@" in pages


def test_service_branch_cannot_trigger_source_builds() -> None:
    for name in ("publish.yml", "ci.yml"):
        assert '"!site-builds"' in _workflow(name)
