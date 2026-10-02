#!/bin/sh
set -eu

audit_directory=$(mktemp -d)
trap 'rm -rf "$audit_directory"' EXIT

.venv/bin/uv --quiet export --locked --format pylock.toml \
  --output-file "$audit_directory/pylock.toml"
.venv/bin/pip-audit --locked "$audit_directory"
