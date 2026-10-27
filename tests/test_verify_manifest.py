import hashlib

import pytest

from hpc.verify_manifest import ManifestError, verify_manifest


def manifest_for(relative_path, content):
    return {
        "schema_version": 1,
        "files": [
            {
                "path": relative_path,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }


def test_valid_manifest_passes(tmp_path):
    payload = b"climate-input\n"
    (tmp_path / "climate.nc").write_bytes(payload)
    assert verify_manifest(manifest_for("climate.nc", payload), tmp_path) == {
        "status": "PASS",
        "files": 1,
        "bytes": len(payload),
    }


@pytest.mark.parametrize("replacement", [b"changed\n", b"more bytes\n"])
def test_changed_file_fails(tmp_path, replacement):
    original = b"original\n"
    (tmp_path / "climate.nc").write_bytes(replacement)
    with pytest.raises(ManifestError, match="mismatch"):
        verify_manifest(manifest_for("climate.nc", original), tmp_path)


def test_duplicate_path_fails(tmp_path):
    payload = b"x"
    (tmp_path / "roads.rar").write_bytes(payload)
    manifest = manifest_for("roads.rar", payload)
    manifest["files"].append(manifest["files"][0].copy())
    with pytest.raises(ManifestError, match="duplicate"):
        verify_manifest(manifest, tmp_path)


@pytest.mark.parametrize("outside", ["../outside.nc", "/tmp/outside.nc"])
def test_path_traversal_fails(tmp_path, outside):
    with pytest.raises(ManifestError, match="unsafe"):
        verify_manifest(manifest_for(outside, b"x"), tmp_path)


def test_symlink_escape_fails(tmp_path):
    outside = tmp_path.parent / "outside.nc"
    outside.write_bytes(b"x")
    (tmp_path / "escape.nc").symlink_to(outside)
    with pytest.raises(ManifestError, match="escapes"):
        verify_manifest(manifest_for("escape.nc", b"x"), tmp_path)
