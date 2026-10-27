"""Verify a staged input/output manifest before a PBS job consumes it.

The manifest contains paths relative to a declared staging root. This module
does not decide whether the scientific content is suitable for the manuscript;
it only checks file identity, size, and safe path resolution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CHUNK_SIZE = 4 * 1024 * 1024


class ManifestError(ValueError):
    """A manifest is malformed or does not match staged files."""


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_staged_file(root: Path, relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ManifestError(f"unsafe relative path: {relative_path!r}")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / relative).resolve(strict=False)
    if not resolved.is_relative_to(resolved_root):
        raise ManifestError(f"path escapes staging root: {relative_path!r}")
    if not resolved.is_file():
        raise ManifestError(f"missing staged file: {relative_path!r}")
    return resolved


def verify_manifest(manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    """Fail closed if a required file is missing, changed, duplicated, or unsafe."""
    if manifest.get("schema_version") != 1:
        raise ManifestError("schema_version must be 1")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ManifestError("files must be a non-empty list")
    seen: set[str] = set()
    total_bytes = 0
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ManifestError(f"files[{index}] must be an object")
        relpath = entry.get("path")
        expected_hash = entry.get("sha256")
        expected_bytes = entry.get("bytes")
        if not isinstance(relpath, str) or not relpath:
            raise ManifestError(f"files[{index}].path must be nonempty text")
        if relpath in seen:
            raise ManifestError(f"duplicate staged path: {relpath!r}")
        seen.add(relpath)
        if not isinstance(expected_hash, str) or not SHA256_PATTERN.fullmatch(expected_hash):
            raise ManifestError(f"invalid SHA-256 for {relpath!r}")
        if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int) or expected_bytes < 0:
            raise ManifestError(f"invalid byte count for {relpath!r}")
        staged = _safe_staged_file(root, relpath)
        actual_bytes = staged.stat().st_size
        if actual_bytes != expected_bytes:
            raise ManifestError(
                f"size mismatch for {relpath!r}: expected {expected_bytes}, got {actual_bytes}"
            )
        actual_hash = file_sha256(staged)
        if actual_hash != expected_hash:
            raise ManifestError(f"SHA-256 mismatch for {relpath!r}")
        total_bytes += actual_bytes
    return {"status": "PASS", "files": len(entries), "bytes": total_bytes}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ManifestError("manifest root must be an object")
        report = verify_manifest(manifest, args.root)
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
