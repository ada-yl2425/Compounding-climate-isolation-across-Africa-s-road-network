import csv
import hashlib

from hpc.verify_road_speed_transfer import verify


def test_transfer_verifier_rejects_missing_and_corrupt_input(tmp_path):
    roads = tmp_path / "roads"
    roads.mkdir()
    archive = roads / "Benin.rar"
    archive.write_bytes(b"official source")
    speed = tmp_path / "road_speed_cordex.zip"
    speed.write_bytes(b"speed reference")
    registry = tmp_path / "registry.csv"
    with registry.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=(
            "archive_filename", "archive_size_bytes", "archive_figshare_md5"
        ))
        writer.writeheader()
        writer.writerow({
            "archive_filename": archive.name,
            "archive_size_bytes": archive.stat().st_size,
            "archive_figshare_md5": hashlib.md5(archive.read_bytes()).hexdigest(),
        })
    expected_speed = hashlib.sha256(speed.read_bytes()).hexdigest()
    result = verify(registry, roads, speed, expected_speed)
    assert result["verified_road_archives"] == 1
    assert result["status"] == "FAIL"  # one country cannot masquerade as the 49-country set

    archive.write_bytes(b"corrupt source!")
    result = verify(registry, roads, speed, expected_speed)
    assert result["verified_road_archives"] == 0
    assert any("wrong official MD5" in message for message in result["failures"])


def test_transfer_verifier_detects_extra_archive_and_speed_mismatch(tmp_path):
    roads = tmp_path / "roads"
    roads.mkdir()
    (roads / "unexpected.rar").write_bytes(b"x")
    speed = tmp_path / "speed.zip"
    speed.write_bytes(b"different")
    registry = tmp_path / "registry.csv"
    registry.write_text("archive_filename,archive_size_bytes,archive_figshare_md5\n")
    result = verify(registry, roads, speed, "0" * 64)
    assert "unexpected road archive: unexpected.rar" in result["failures"]
    assert "legacy speed ZIP SHA-256 mismatch or missing" in result["failures"]


def test_transfer_verifier_passes_exact_49_country_set(tmp_path):
    roads = tmp_path / "roads"
    roads.mkdir()
    speed = tmp_path / "speed.zip"
    speed.write_bytes(b"speed")
    registry = tmp_path / "registry.csv"
    with registry.open("w", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=(
            "archive_filename", "archive_size_bytes", "archive_figshare_md5"
        ))
        writer.writeheader()
        for index in range(49):
            archive = roads / f"Country{index}.rar"
            payload = str(index).encode()
            archive.write_bytes(payload)
            writer.writerow({
                "archive_filename": archive.name,
                "archive_size_bytes": len(payload),
                "archive_figshare_md5": hashlib.md5(payload).hexdigest(),
            })
    result = verify(registry, roads, speed, hashlib.sha256(b"speed").hexdigest())
    assert result["status"] == "PASS"
    assert result["verified_road_archives"] == 49
