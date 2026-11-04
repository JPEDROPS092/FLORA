"""Sample coordinates -> map points."""

from __future__ import annotations

from flora.io.geo import read_points


def _write(tmp_path, text, name="metadata.tsv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_points_merge_shared_stations_and_pick_group(tmp_path):
    p = _write(tmp_path, "sample_id\tlatitude\tlongitude\tenvironment_feature\n"
                         "S1\t-0.1569\t-50.6225\tAmazon River\n"
                         "S2\t-0.1569\t-50.6225\tAmazon River\n"
                         "S3\t7.29\t-53\tAmazon river plume\n"
                         "S4\t\t\tAmazon river plume\n"
                         "S5\t0\t0\tAmazon River\n"
                         "S6\t95\t10\tAmazon River\n")
    out = read_points(p)
    assert out["available"] and out["group_column"] == "environment_feature"
    assert out["mapped"] == 3 and out["skipped"] == 3 and out["total"] == 6
    station = next(pt for pt in out["points"] if pt["lat"] == -0.1569)
    assert station["n"] == 2 and station["ids"] == ["S1", "S2"]
    assert {g["name"]: g["count"] for g in out["groups"]} == {"Amazon River": 2, "Amazon river plume": 1}


def test_no_coordinates_and_missing_file(tmp_path):
    assert read_points(_write(tmp_path, "sample_id\tbiome\nS1\ta\n"))["reason"] == "no_coordinates"
    assert read_points(tmp_path / "nope.tsv")["reason"] == "not_downloaded"
    assert read_points(_write(tmp_path, "sample_id\tlatitude\tlongitude\nS1\t\t\n", "b.tsv"))["reason"] == "no_valid_coordinates"


def test_combined_lat_lon_column_and_hemispheres(tmp_path):
    out = read_points(_write(tmp_path, "sample_id\tlat_lon\nS1\t10.5 S 30.2 W\nS2\t1.5 -2.5\nS3\tbad\n"))
    pts = {(p["lat"], p["lon"]) for p in out["points"]}
    assert pts == {(-10.5, -30.2), (1.5, -2.5)} and out["skipped"] == 1


def test_explicit_group_by(tmp_path):
    p = _write(tmp_path, "sample_id\tlatitude\tlongitude\thost\nS1\t1\t1\ta\nS2\t2\t2\tb\n")
    assert read_points(p, "host")["group_column"] == "host"


def test_groups_ignore_capitalisation(tmp_path):
    p = _write(tmp_path, "sample_id\tlatitude\tlongitude\tenvironment_feature\n"
                         "S1\t1\t1\tAmazon river plume\nS2\t2\t2\tAmazon River Plume\nS3\t3\t3\tAmazon river plume\nS4\t4\t4\tAmazon River\n")
    out = read_points(p)
    assert {g["name"]: g["count"] for g in out["groups"]} == {"Amazon river plume": 3, "Amazon River": 1}
