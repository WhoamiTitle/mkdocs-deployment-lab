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
    for job_name in ("build-pages", "deploy-helios-production", "deploy-helios-preview"):
        assert "needs: quality" in _job(workflow, job_name)


def test_workflows_install_dependencies_from_uv_lock() -> None:
    for workflow_name in (
        "ci.yml",
        "cleanup-preview.yml",
        "helios-resilience.yml",
        "publish.yml",
        "rollback.yml",
    ):
        workflow = _workflow(workflow_name)
        assert "uv sync --locked" in workflow
        assert "requirements.txt" not in workflow


def test_production_deploy_and_rollback_share_concurrency_group() -> None:
    production = _job(_workflow("publish.yml"), "deploy-helios-production")
    rollback = _job(_workflow("rollback.yml"), "rollback")

    for job in (production, rollback):
        assert "group: helios-production" in job
        assert "cancel-in-progress: false" in job


def test_preview_deploy_and_cleanup_share_branch_concurrency_group() -> None:
    preview = _job(_workflow("publish.yml"), "deploy-helios-preview")
    cleanup = _job(_workflow("cleanup-preview.yml"), "cleanup-preview")

    assert "group: helios-preview-${{ github.ref_name }}" in preview
    assert (
        "helios-preview-${{ github.event_name == 'delete' && github.event.ref || inputs.branch }}"
        in cleanup
    )
    for job in (preview, cleanup):
        assert "cancel-in-progress: false" in job


def test_rollback_workflows_verify_restored_release_identifier() -> None:
    publish = _workflow("publish.yml")
    rollback = _workflow("rollback.yml")

    for workflow in (publish, rollback):
        assert 'tee "$RUNNER_TEMP/helios-rollback.json"' in workflow
        assert '--expected-text "deployment-marker:${release_id}:"' in workflow
