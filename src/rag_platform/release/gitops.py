from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

IMAGE_KEYS = {
    "frontend": "frontend",
    "api": "api",
    "ingestion-worker": "ingestionWorker",
    "drive-sync": "driveSync",
    "ollama-runtime": "ollamaRuntime",
}
IMAGE_REFERENCE = re.compile(r"^(?P<repository>[^@\s]+)@(?P<digest>sha256:[0-9a-f]{64})$")


def update_image_manifest(artifacts_dir: Path, manifest_path: Path) -> dict[str, str]:
    """Update a Helm values overlay from verified image-release digest artifacts."""
    references: dict[str, str] = {}
    for artifact in artifacts_dir.glob("**/*.digest.txt"):
        release_name = artifact.name.removesuffix(".digest.txt")
        if release_name in references:
            raise ValueError(f"Duplicate digest artifact for {release_name}")
        references[release_name] = artifact.read_text(encoding="utf-8").strip()

    missing = sorted(set(IMAGE_KEYS) - set(references))
    unexpected = sorted(set(references) - set(IMAGE_KEYS))
    if missing or unexpected:
        raise ValueError(f"Digest artifacts mismatch: missing={missing}, unexpected={unexpected}")

    document: dict[str, Any] = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    images = document.setdefault("images", {})
    updated: dict[str, str] = {}
    for release_name, values_key in IMAGE_KEYS.items():
        reference = references[release_name]
        match = IMAGE_REFERENCE.fullmatch(reference)
        if not match:
            raise ValueError(f"Invalid immutable image reference for {release_name}")
        image = images.setdefault(values_key, {})
        image["repository"] = match.group("repository")
        image["digest"] = match.group("digest")
        updated[values_key] = reference

    manifest_path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False), encoding="utf-8"
    )
    return updated
