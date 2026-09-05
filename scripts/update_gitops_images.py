#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_platform.release.gitops import update_image_manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Update GitOps image values from digest artifacts")
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    updated = update_image_manifest(args.artifacts_dir, args.manifest)
    print(json.dumps(updated, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
