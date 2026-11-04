"""Sample coordinates from a metadata table, ready to plot on a map.

Reads ``latitude``/``longitude`` style columns (or a combined ``lat_lon`` string), drops
invalid or placeholder coordinates and merges samples that share a station.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

_LAT = ("latitude", "lat", "decimal_latitude", "geo_latitude")
_LON = ("longitude", "lon", "long", "lng", "decimal_longitude", "geo_longitude")
_ID = ("sample_id", "sample_accession", "sample", "run_accession", "id")
_GROUP_PREFERENCE = (
    "environment_feature", "environment_biome", "biome", "habitat", "isolation_source",
    "environment_material", "geo_loc_name", "country", "location",
)
_PAIR = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*([NSns])?[ ,;]+\s*(-?\d+(?:\.\d+)?)\s*([EWew])?\s*$")
_MAX_GROUPS = 12
_MAX_IDS = 6


def _num(value: str) -> float | None:
    try:
        return float(str(value).strip().replace(",", "."))
    except ValueError:
        return None


def _column(header: list[str], names: tuple[str, ...]) -> str | None:
    lowered = {h.lower().strip(): h for h in header}
    return next((lowered[n] for n in names if n in lowered), None)


def _split_lat_lon(text: str) -> tuple[float, float] | None:
    m = _PAIR.match(text or "")
    if not m:
        return None
    lat, ns, lon, ew = float(m[1]), m[2], float(m[3]), m[4]
    if ns and ns.upper() == "S":
        lat = -abs(lat)
    if ew and ew.upper() == "W":
        lon = -abs(lon)
    return lat, lon


def _pick_group(rows: list[dict[str, str]], header: list[str], skip: set[str]) -> str | None:
    def values(col: str) -> set[str]:
        return {r.get(col, "").strip() for r in rows if r.get(col, "").strip()}

    lowered = {h.lower(): h for h in header}
    for name in _GROUP_PREFERENCE:
        col = lowered.get(name)
        if col and col not in skip and 2 <= len(values(col)) <= _MAX_GROUPS:
            return col
    for col in header:
        if col not in skip and 2 <= len(values(col)) <= _MAX_GROUPS:
            return col
    return None


def read_points(path: str | Path, group_by: str | None = None, max_rows: int = 20000) -> dict[str, Any]:
    """Parse *path* (TSV/CSV) into map points. Never raises for a readable file without coordinates."""
    file = Path(path)
    if not file.is_file():
        return {"available": False, "reason": "not_downloaded", "points": [], "groups": [], "group_column": "", "total": 0, "mapped": 0, "skipped": 0}
    delimiter = "\t" if file.suffix.lower() in {".tsv", ".txt"} else ","
    with open(file, encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        header = [h for h in (reader.fieldnames or []) if h]
        rows = [r for _, r in zip(range(max_rows), reader, strict=False)]

    lat_col, lon_col = _column(header, _LAT), _column(header, _LON)
    pair_col = _column(header, ("lat_lon", "latlon", "coordinates"))
    id_col = _column(header, _ID) or (header[0] if header else "")
    if not (lat_col and lon_col) and not pair_col:
        return {"available": False, "reason": "no_coordinates", "points": [], "groups": [], "group_column": "", "total": len(rows), "mapped": 0, "skipped": 0}

    skip = {c for c in (lat_col, lon_col, pair_col, id_col) if c}
    group_col = group_by if group_by in header else _pick_group(rows, header, skip)

    merged: dict[tuple[float, float, str], dict[str, Any]] = {}
    spellings: dict[str, dict[str, int]] = {}
    skipped = 0
    for row in rows:
        if lat_col and lon_col:
            lat, lon = _num(row.get(lat_col, "")), _num(row.get(lon_col, ""))
        else:
            parsed = _split_lat_lon(row.get(pair_col or "", ""))
            lat, lon = parsed if parsed else (None, None)
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            skipped += 1
            continue
        raw_group = (row.get(group_col, "").strip() if group_col else "") or "—"
        # Public metadata often differs only in capitalisation ("river plume" / "River Plume"): one group.
        group = raw_group.casefold()
        seen = spellings.setdefault(group, {})
        seen[raw_group] = seen.get(raw_group, 0) + 1
        point = merged.setdefault((lat, lon, group), {"lat": lat, "lon": lon, "group": group, "n": 0, "ids": []})
        point["n"] += 1
        if len(point["ids"]) < _MAX_IDS:
            point["ids"].append(row.get(id_col, "") if id_col else "")

    points = list(merged.values())
    label = {key: max(names, key=names.get) for key, names in spellings.items()}
    for p in points:
        p["group"] = label[p["group"]]
    counts: dict[str, int] = {}
    for p in points:
        counts[p["group"]] = counts.get(p["group"], 0) + p["n"]
    if not points:
        return {"available": False, "reason": "no_valid_coordinates", "points": [], "groups": [], "group_column": group_col or "", "total": len(rows), "mapped": 0, "skipped": skipped}
    return {
        "available": True,
        "reason": "",
        "points": points,
        "groups": [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: -kv[1])],
        "group_column": group_col or "",
        "total": len(rows),
        "mapped": sum(p["n"] for p in points),
        "skipped": skipped,
    }
