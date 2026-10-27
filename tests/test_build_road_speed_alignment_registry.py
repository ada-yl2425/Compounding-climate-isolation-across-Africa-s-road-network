import csv
import zipfile

import pytest

from hpc.build_road_speed_alignment_registry import build_registry


def test_registry_requires_complete_49_country_set(tmp_path):
    official = tmp_path / "official.csv"
    with official.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "filename", "size_bytes", "figshare_md5", "local_and_icloud_md5_match"
        ))
        writer.writeheader()
        writer.writerow({"filename": "Kenya.rar", "size_bytes": 1, "figshare_md5": "abc", "local_and_icloud_md5_match": "true"})
    (tmp_path / "Kenya.rar").write_bytes(b"x")
    speed = tmp_path / "speed.zip"
    with zipfile.ZipFile(speed, "w") as archive:
        archive.writestr("road_speed_cordex/Kenya_road_speed.csv", "road_id\n")
    with pytest.raises(ValueError, match="expected 49"):
        build_registry(official, speed, tmp_path)


def test_missing_speed_member_fails_before_transfer(tmp_path):
    official = tmp_path / "official.csv"
    with official.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=(
            "filename", "size_bytes", "figshare_md5", "local_and_icloud_md5_match"
        ))
        writer.writeheader()
        writer.writerow({"filename": "CentralAfrian.rar", "size_bytes": 1, "figshare_md5": "abc", "local_and_icloud_md5_match": "true"})
    (tmp_path / "CentralAfrian.rar").write_bytes(b"x")
    speed = tmp_path / "speed.zip"
    with zipfile.ZipFile(speed, "w") as archive:
        archive.writestr("road_speed_cordex/CentralAfrian_road_speed.csv", "road_id\n")
    with pytest.raises(ValueError, match="CentralAfrican_road_speed"):
        build_registry(official, speed, tmp_path)
