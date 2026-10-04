"""Persist versioned sites and branch previews in the isolated site-builds branch."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import uuid
from pathlib import Path

from publication_pipeline.application.models import Release, SourceRevision
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug
from publication_pipeline.application.value_objects.release_id import ReleaseId
from publication_pipeline.infrastructure.filesystem_release_artifact_store import (
    FilesystemReleaseArtifactStore,
)
from publication_pipeline.infrastructure.git_source_control import GitSourceControl
from scripts.deployment_targets import Target, resolve_targets

STATE_BRANCH = "site-builds"
VERSION = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:\.(0|[1-9][0-9]*))?$")


def version_key(version: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(version)
    if match is None:
        raise ValueError("Stable versions must be vMAJOR.MINOR or vMAJOR.MINOR.PATCH")
    return int(match[1]), int(match[2]), int(match[3] or 0)


def run(cwd: Path, *args: str, env: dict[str, str] | None = None) -> str:
    environment = dict(os.environ) if env is None else dict(env)
    environment["PYTHONUTF8"] = "1"
    environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    result = subprocess.run(
        args,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
    )
    if result.returncode:
        raise RuntimeError(f"{args[0]} failed: {result.stderr or result.stdout}")
    return result.stdout.strip()


def copy_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    if source.exists():
        shutil.copytree(source, destination)


def archive(root: Path, ref: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="site-archive-") as temporary:
        archive_file = Path(temporary) / "site.tar"
        run(root, "git", "archive", "--format=tar", "-o", str(archive_file), ref)
        with tarfile.open(archive_file) as bundle:
            bundle.extractall(destination, filter="data")


def state_commit(root: Path, state: Path, parent: str | None) -> str:
    """Use a separate index; source files, HEAD and the user's index are untouched."""
    with tempfile.TemporaryDirectory(prefix="site-index-") as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / "index"))
        run(root, "git", "read-tree", "--empty", env=env)
        run(
            root,
            "git",
            "-c",
            "core.autocrlf=false",
            "--work-tree",
            str(state),
            "add",
            "--all",
            env=env,
        )
        tree = run(root, "git", "write-tree", env=env)
        arguments = [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit-tree",
            tree,
        ]
        if parent:
            arguments += ["-p", parent]
        return run(root, *arguments, "-m", "Update published site snapshots", env=env)


def load_remote_state(root: Path, state: Path) -> str | None:
    refs = run(root, "git", "ls-remote", "--heads", "origin", f"refs/heads/{STATE_BRANCH}")
    if not refs:
        state.mkdir(parents=True, exist_ok=True)
        return None
    run(root, "git", "fetch", "origin", f"refs/heads/{STATE_BRANCH}")
    parent = run(root, "git", "rev-parse", "FETCH_HEAD")
    archive(root, parent, state)
    return parent


def stamp(site: Path, root: Path, tag: str = "") -> Release:
    revision = GitSourceControl(root).revision()
    if tag:
        revision = SourceRevision(
            commit_sha=revision.commit_sha, branch=BranchName(tag), dirty=False
        )
    release = Release.create(revision)
    # Repeated operations on one commit in the same second must remain distinct.
    release = Release(
        release_id=ReleaseId(f"{release.release_id.value}-{uuid.uuid4().hex[:8]}"),
        commit_sha=release.commit_sha,
        branch=release.branch,
        built_at=release.built_at,
        dirty=release.dirty,
    )
    index = site / "index.html"
    html = index.read_text(encoding="utf-8")
    html = re.sub(r"<!-- deployment-marker:[^>]*-->\s*", "", html)
    html = re.sub(r'<meta name="deployment-commit"[^>]*>\s*', "", html)
    if "publication-site-control" not in html:
        html = html.replace("</body>", "<span hidden>publication-site-control</span></body>")
    index.write_text(html, encoding="utf-8")
    FilesystemReleaseArtifactStore().write(site, release)
    return release


def build_plain(root: Path, destination: Path, url: str) -> None:
    run(
        root,
        sys.executable,
        "-m",
        "publication_pipeline",
        "build",
        "--repository-root",
        str(root),
        "--site-dir",
        str(destination),
        env=dict(os.environ, SITE_URL=url),
    )


def compose_pages(target: Path, destination: Path) -> None:
    copy_directory(target / "production", destination)
    if (target / "previews").exists():
        copy_directory(target / "previews", destination / "previews")


def stable_snapshot(state: Path, target_id: str) -> None:
    source = state / "sites" / target_id / "production"
    if target_id == "github-pages" and (state / "delivered/github-pages/production").is_dir():
        source = state / "delivered/github-pages/production"
    copy_directory(source, state / "history" / target_id / "previous")


def version_config(builder: Path, template: str) -> None:
    """Apply current version navigation/search adapters to historical document sources."""
    project = Path(__file__).resolve().parents[1]
    copy_directory(project / "overrides", builder / "overrides")
    worker = Path("docs/assets/javascripts/workers/russian-search.js")
    (builder / worker).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(project / worker, builder / worker)
    (builder / ".versioned-mkdocs.yml").write_text(template, encoding="utf-8")


def build_versions(root: Path, state: Path, targets: list[Target], selected: str = "") -> None:
    tags = sorted(
        (tag for tag in run(root, "git", "tag", "--list").splitlines() if VERSION.fullmatch(tag)),
        key=version_key,
    )
    if not tags and not selected:
        raise ValueError("No stable tags exist; create v1.0 and push it before publishing versions")
    if selected:
        version_key(selected)
    published = set(tags)
    for target in targets:
        manifest = state / "sites" / str(target["id"]) / "production/versions.json"
        if manifest.is_file():
            published.update(
                entry["version"] for entry in json.loads(manifest.read_text(encoding="utf-8"))
            )
    latest = selected or max(published, key=version_key)
    for target in targets:
        identity = str(target["id"])
        production = state / "sites" / identity / "production"
        stable_snapshot(state, identity)
        if production.exists() and not (production / "versions.json").exists():
            if not production.resolve().is_relative_to(state.resolve()):
                raise ValueError("Production snapshot must stay inside the state directory")
            shutil.rmtree(production)
    with tempfile.TemporaryDirectory(prefix="site-mike-") as temporary:
        builder = Path(temporary) / "source"
        run(root, "git", "clone", "--no-hardlinks", "--no-checkout", str(root), str(builder))
        run(builder, "git", "config", "user.name", "Documentation builder")
        run(builder, "git", "config", "user.email", "builder@example.invalid")
        run(builder, "git", "config", "core.autocrlf", "false")
        initial = state_commit(builder, state, None)
        run(builder, "git", "branch", "-f", STATE_BRANCH, initial)
        template = (root / "mkdocs.versioned.yml").read_text(encoding="utf-8")
        for target in targets:
            identity = str(target["id"])
            production = state / "sites" / identity / "production"
            prefix = f"sites/{identity}/production"
            for tag in [] if selected else tags:
                sha = run(root, "git", "rev-parse", f"refs/tags/{tag}^{{commit}}")
                existing = production / tag / "release.json"
                if existing.exists():
                    release = FilesystemReleaseArtifactStore().read(existing.parent)
                    if release.commit_sha.value != sha:
                        raise ValueError(
                            f"Published tag {tag} was moved; create a new version instead"
                        )
                    continue
                run(builder, "git", "checkout", "--force", "--detach", sha)
                version_config(builder, template)
                mike(builder, prefix, str(target["base_url"]), "deploy", tag)
            # Alias commands only need a readable config; use the newest tagged source.
            run(
                builder,
                "git",
                "checkout",
                "--force",
                "--detach",
                "HEAD" if selected else f"refs/tags/{tags[-1]}",
            )
            version_config(builder, template)
            mike(
                builder,
                prefix,
                str(target["base_url"]),
                "alias",
                latest,
                "latest",
                "--update-aliases",
                "--alias-type",
                "redirect",
            )
            mike(builder, prefix, str(target["base_url"]), "set-default", "latest")
        exported = Path(temporary) / "exported"
        archive(builder, STATE_BRANCH, exported)
        for target in targets:
            identity = str(target["id"])
            production = state / "sites" / identity / "production"
            copy_directory(exported / "sites" / identity / "production", production)
            for tag in tags:
                if not (production / tag / "release.json").exists():
                    if selected:
                        continue
                    run(builder, "git", "checkout", "--force", "--detach", f"refs/tags/{tag}")
                    (builder / ".versioned-mkdocs.yml").unlink(missing_ok=True)
                    stamp(production / tag, builder, tag)
            stamp(production, root)


def mike(root: Path, prefix: str, url: str, command: str, *arguments: str) -> None:
    run(
        root,
        sys.executable,
        "-c",
        "from mike.driver import main; main()",
        command,
        *arguments,
        "--config-file",
        ".versioned-mkdocs.yml",
        "--branch",
        STATE_BRANCH,
        "--deploy-prefix",
        prefix,
        "--ignore-remote-status",
        env=dict(os.environ, SITE_URL=url),
    )


def select_latest(root: Path, state: Path, targets: list[Target], version: str) -> None:
    version_key(version)
    for target in targets:
        versions = state / "sites" / str(target["id"]) / "production" / "versions.json"
        if not versions.is_file() or version not in {
            entry["version"] for entry in json.loads(versions.read_text(encoding="utf-8"))
        }:
            raise ValueError(f"Version {version} has not been published for {target['id']}")
    # build_versions preserves existing files; only the alias and root metadata change.
    build_versions(root, state, targets, selected=version)


def rollback_pages(state: Path) -> None:
    current = state / "sites" / "github-pages" / "production"
    previous = state / "history" / "github-pages" / "previous"
    if not previous.is_dir():
        raise ValueError("GitHub Pages has no previous stable publication to restore")
    with tempfile.TemporaryDirectory(prefix="site-rollback-") as temporary:
        saved = Path(temporary) / "current"
        copy_directory(current, saved)
        copy_directory(previous, current)
        copy_directory(saved, previous)


def prepare(
    root: Path,
    state: Path,
    output: Path,
    targets: list[Target],
    operation: str,
    name: str = "",
    version: str = "",
) -> dict[str, str]:
    """Build artifacts; callers may persist the resulting state only after validation."""
    pages_target = state / "sites" / "github-pages"
    delivered = state / "delivered/github-pages"
    previous_target = delivered if delivered.exists() else pages_target
    had_pages = (previous_target / "production" / "index.html").is_file()
    previous_pages = output / "previous-pages"
    if had_pages:
        compose_pages(previous_target, previous_pages)
    if operation not in {"restore-pages", "confirm-pages"} and had_pages:
        copy_directory(previous_target, state / "history" / "pages-delivery")
        copy_directory(
            state / "history/github-pages/previous",
            state / "history/pages-previous-before-delivery",
        )
    if operation == "confirm-pages":
        copy_directory(pages_target, delivered)
    elif operation == "restore-pages":
        old = state / "history" / "pages-delivery"
        if not old.is_dir():
            raise ValueError("There is no previous Pages delivery")
        copy_directory(old, pages_target)
        copy_directory(
            state / "history/pages-previous-before-delivery",
            state / "history/github-pages/previous",
        )
    else:
        # Bootstrap a readable root before the first tag, without changing it on branch pushes.
        for target in targets:
            production = state / "sites" / str(target["id"]) / "production"
            if not (production / "index.html").exists():
                try:
                    main_sha = run(root, "git", "rev-parse", "--verify", "refs/remotes/origin/main")
                except RuntimeError:
                    main_sha = run(root, "git", "rev-parse", "--verify", "refs/heads/main")
                with tempfile.TemporaryDirectory(prefix="site-bootstrap-") as temporary:
                    source = Path(temporary) / "source"
                    run(root, "git", "clone", "--no-hardlinks", str(root), str(source))
                    run(source, "git", "checkout", "--detach", main_sha)
                    build_plain(source, production, str(target["base_url"]))
        if operation == "version":
            version_key(version)
            run(root, "git", "rev-parse", "--verify", f"refs/tags/{version}^{{commit}}")
            build_versions(root, state, targets)
        elif operation == "set-latest":
            select_latest(root, state, targets, version)
        elif operation == "rollback-pages":
            rollback_pages(state)
        elif operation in {"preview", "cleanup-preview"}:
            slug = BranchSlug.from_branch(BranchName(name)).value
            for target in targets:
                preview = state / "sites" / str(target["id"]) / "previews" / slug
                if operation == "preview":
                    build_plain(root, preview, f"{target['base_url']}previews/{slug}/")
                elif preview.exists():
                    shutil.rmtree(preview)
        else:
            raise ValueError("Unknown site publication operation")
    compose_pages(pages_target, output / "pages")
    action = {
        "version": "production",
        "set-latest": "production",
        "preview": "preview",
        "cleanup-preview": "cleanup",
    }.get(operation, "none")
    for target in targets:
        if target["id"] == "github-pages" or action in {"none", "cleanup"}:
            continue
        source = state / "sites" / str(target["id"])
        if action == "preview":
            source /= f"previews/{BranchSlug.from_branch(BranchName(name)).value}"
        else:
            source /= "production"
        copy_directory(source, output / "targets" / str(target["id"]))
    for directory in (output / "pages", output / "targets"):
        if directory.is_dir():
            run(
                root,
                sys.executable,
                "-m",
                "publication_pipeline",
                "offline-check",
                "--site-dir",
                str(directory),
            )
    # Check that all HTML version links and metadata are internally consistent.
    from scripts.verify_published_site import verify_local_site

    verify_local_site(output / "pages")
    result = {"helios_action": action, "has_previous_pages": str(had_pages).lower()}
    (output / "operation.json").write_text(json.dumps(result), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--operation",
        choices=(
            "preview",
            "version",
            "set-latest",
            "rollback-pages",
            "cleanup-preview",
            "restore-pages",
            "confirm-pages",
        ),
        required=True,
    )
    parser.add_argument("--name", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--save-state", action="store_true")
    args = parser.parse_args()
    root = Path.cwd().resolve()
    output = root / "site/publication"
    output.mkdir(parents=True, exist_ok=True)
    helios = (
        resolve_targets(os.environ["DEPLOY_TARGETS"])
        if (os.environ.get("HELIOS_ENABLED") == "true")
        else []
    )
    requested = os.environ.get("TARGET_ID", "").strip()
    if requested:
        if args.operation != "cleanup-preview":
            raise ValueError("Target selection is supported only for preview cleanup")
        helios = [target for target in helios if target["id"] == requested]
        if not helios:
            raise ValueError("Requested deployment target does not exist")
    if any(target["id"] == "github-pages" for target in helios):
        raise ValueError("The target ID github-pages is reserved")
    pages: Target = {"id": "github-pages", "base_url": os.environ["PAGES_BASE_URL"]}
    with tempfile.TemporaryDirectory(prefix="site-state-") as temporary:
        state = Path(temporary) / "state"
        parent = load_remote_state(root, state)
        result = prepare(
            root, state, output, [pages, *helios], args.operation, args.name, args.version
        )
        if os.environ.get("CHECK_BROWSER") == "true":
            run(
                root,
                "node",
                "tools/browser-check/check.cjs",
                str(output / "pages"),
                str(output / "browser-check.json"),
            )
        if args.save_state:
            commit = state_commit(root, state, parent)
            run(root, "git", "push", "origin", f"{commit}:refs/heads/{STATE_BRANCH}")
    result["targets"] = json.dumps(helios, separators=(",", ":"))
    if github_output := os.environ.get("GITHUB_OUTPUT"):
        with Path(github_output).open("a", encoding="utf-8") as destination:
            for key, value in result.items():
                destination.write(f"{key}={value}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
