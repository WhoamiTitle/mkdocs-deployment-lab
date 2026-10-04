"""Resolve public deployment configuration without accessing credentials."""

import json
import os
import re
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlsplit

_FIELDS = {
    "id",
    "host",
    "port",
    "user",
    "base_url",
    "deployment_root",
    "public_path",
    "key_secret",
    "known_hosts_secret",
}
_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
_ID = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_SECRET = re.compile(r"^[A-Z_][A-Z0-9_]*$")

Target = dict[str, str | int]


def resolve_targets(raw: str) -> list[Target]:
    """Reject ambiguous destinations, unsafe paths and malformed matrix entries."""
    data = json.loads(raw)
    if not isinstance(data, list) or not 1 <= len(data) <= 256:
        raise ValueError("Deployment targets must be a nonempty array of at most 256 entries")
    identifiers: set[str] = set()
    destinations: set[tuple[str, int, str, str]] = set()
    roots: set[tuple[str, int, str, str]] = set()
    targets: list[Target] = []
    for item in data:
        if not isinstance(item, dict) or set(item) != _FIELDS:
            raise ValueError("Each deployment target must contain exactly the documented fields")
        target = cast(Target, item)
        for field in _FIELDS - {"port"}:
            if not isinstance(target[field], str) or not target[field]:
                raise ValueError(f"Target field {field} must be a nonempty string")
        identity = str(target["id"])
        if not _ID.fullmatch(identity) or identity in identifiers:
            raise ValueError("Deployment target IDs must be unique lowercase identifiers")
        identifiers.add(identity)
        for field in ("host", "user"):
            if not _NAME.fullmatch(str(target[field])):
                raise ValueError(f"Unsafe deployment target {field}")
        port = target["port"]
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("Deployment target port must be an integer between 1 and 65535")
        for field in ("key_secret", "known_hosts_secret"):
            if not _SECRET.fullmatch(str(target[field])):
                raise ValueError(f"Invalid secret name in {field}")
        for field in ("deployment_root", "public_path"):
            raw_path = str(target[field])
            remote_path = PurePosixPath(raw_path)
            if (
                remote_path.is_absolute()
                or any(
                    part in {"", ".", ".."} or not _NAME.fullmatch(part)
                    for part in raw_path.split("/")
                )
                or len(remote_path.parts) < 2
            ):
                raise ValueError(f"Unsafe deployment target {field}")
        public_path = PurePosixPath(str(target["public_path"]))
        deployment_root = PurePosixPath(str(target["deployment_root"]))
        if public_path.parts[0] != "public_html":
            raise ValueError("Public path must be a subdirectory of public_html")
        if public_path.is_relative_to(deployment_root) or deployment_root.is_relative_to(
            public_path
        ):
            raise ValueError("Public path and deployment root must not overlap")
        url = urlsplit(str(target["base_url"]))
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or not url.path.endswith("/")
        ):
            raise ValueError("Base URL must be an HTTPS directory URL without credentials or query")
        account = (str(target["host"]).lower(), port, str(target["user"]))
        destination = (*account, str(public_path))
        root = (*account, str(deployment_root))
        if destination in destinations or root in roots:
            raise ValueError("Deployment targets must not share a public path or deployment root")
        destinations.add(destination)
        roots.add(root)
        targets.append(target)
    return targets


def main() -> None:
    raw = os.environ.get("DEPLOY_TARGETS", "").strip()
    if not raw:
        raise ValueError("Set the DEPLOY_TARGETS GitHub variable before deploying")
    targets = resolve_targets(raw)
    requested = os.environ.get("TARGET_ID", "").strip()
    if requested:
        targets = [target for target in targets if target["id"] == requested]
        if not targets:
            raise ValueError("Requested deployment target does not exist")
    matrix = json.dumps(targets, separators=(",", ":"))
    output_file = os.environ.get("GITHUB_OUTPUT")
    if output_file:
        with Path(output_file).open("a", encoding="utf-8") as output:
            output.write(f"targets={matrix}\n")
    print(matrix)


if __name__ == "__main__":
    main()
