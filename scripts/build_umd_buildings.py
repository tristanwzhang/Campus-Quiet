#!/usr/bin/env python3
"""
Build data/umd/buildings.json: Maryland's own record of its buildings, in the
same shape build_osu_buildings.py produces for Columbus, so app.js can read
either.

Why this exists. The 3D buildings come from OpenStreetMap via Cesium and the map
matches them by NAME, which misses a lot: OSM does not name every building, and
where both name one the spellings differ. This file supplies the university's
own names, aliases and coordinates so a building OSM never named can still be
labelled, coloured and flown to — and so `offMap()` can tell a College Park
building from the rest of Prince George's County.

Two official sources, joined on the university's building number:

  data/umd/building_codes.json  — written by build_umd_class_estimates.py from
      Testudo's own building lookup: scheduling code -> official name -> number.
  MD iMAP, the state GIS, which publishes UMD's footprints keyed by that number:
      https://mdgeodata.md.gov/imap/rest/services/Structure/MD_CampusFacilities/FeatureServer/2

That join is the part Maryland gives away. Columbus needed GIS_ALIASES_OSU
written by hand because only 144 of its 534 register records carry a scheduling
code at all; here Testudo states the number outright, so nothing is matched by
name or guessed.

Every iMAP building is kept, not only the ones with classes. Buildings with
hours but no classes — Stamp Student Union, the rec centres — have to be
placeable too, and `offMap()` needs the register to know about a building before
it can decide the building is off the map.

Usage:  python3 scripts/build_umd_buildings.py
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "umd" / "buildings.json"
CODES_FILE = ROOT / "data" / "umd" / "building_codes.json"

LAYER = ("https://mdgeodata.md.gov/imap/rest/services/Structure/"
         "MD_CampusFacilities/FeatureServer/2")
SOURCE = "MD iMAP campus facilities — UMD Buildings"
# Generalise the outlines. Full fidelity is tens of thousands of points in a
# file every visitor downloads, and ~2 m is finer than a footprint reads at any
# zoom this map allows.
OFFSET = 0.00002


def query(geometry):
    params = {
        "where": "1=1", "outFields": "BUILDINGID,NAME", "f": "json",
        "resultRecordCount": 5000,
        "returnGeometry": "true" if geometry else "false",
    }
    if geometry:
        params["outSR"] = 4326           # WGS84, what Cesium wants
        params["maxAllowableOffset"] = OFFSET
    url = f"{LAYER}/query?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CampusQuiet build)"})
    data = json.loads(urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data.get("features", [])


def biggest_ring(geom):
    """The outer ring, as [[lon, lat], …]. iMAP gives rings smallest-last but
    does not promise an order, so this picks by |area| rather than by position —
    a courtyard ring taken for the footprint would draw the building inside out.
    """
    rings = (geom or {}).get("rings") or []
    if not rings:
        return None
    return max(rings, key=lambda r: abs(shoelace(r)))


def shoelace(ring):
    a = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        a += x1 * y2 - x2 * y1
    return a / 2


def centroid(ring):
    """Area centroid of a ring, which sits inside an L-shaped building where the
    average of the vertices does not — and a label outside its own building is
    worse than no label."""
    a = shoelace(ring)
    if not a:                                    # degenerate: fall back to the mean
        return (sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring))
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return (cx / (6 * a), cy / (6 * a))


def number_key(raw):
    """iMAP and Testudo both write the number as three characters ('048'), but
    normalise anyway: a join that works for 048 and silently fails for 48 would
    lose exactly one building and look like a missing footprint."""
    s = str(raw).strip()
    return s.zfill(3) if s.isdigit() else s


def main():
    if not CODES_FILE.exists():
        print(f"missing {CODES_FILE.relative_to(ROOT)} — run "
              f"build_umd_class_estimates.py first", file=sys.stderr)
        return 1
    codes = json.loads(CODES_FILE.read_text())["codes"]
    by_number = {}
    for code, v in codes.items():
        by_number.setdefault(number_key(v["number"]), []).append((code, v["name"]))

    features = query(geometry=True)
    print(f"{len(features)} footprints from MD iMAP, {len(codes)} codes from Testudo")

    buildings, no_geometry, ambiguous = {}, [], []
    for f in features:
        attrs = f.get("attributes") or {}
        num = number_key(attrs.get("BUILDINGID"))
        gis_name = (attrs.get("NAME") or "").strip()
        ring = biggest_ring(f.get("geometry"))
        if not ring or len(ring) < 3:
            no_geometry.append(f"{num} {gis_name}")
            continue
        lon, lat = centroid(ring)

        pairs = by_number.get(num) or []
        if len(pairs) > 1:
            # Two scheduling codes on one building number. Recorded rather than
            # resolved: picking one would quietly drop the other's classes.
            ambiguous.append(f"{num} {gis_name}: {', '.join(c for c, _ in pairs)}")
        code = pairs[0][0] if pairs else None
        # Testudo's name and the state's name disagree often enough to matter —
        # Testudo writes "Epply Recreation Center", iMAP writes "Eppley
        # Recreation Center" — and OSM may use either. Both go in, so the
        # tile-name match has every official spelling to try.
        aliases = []
        for _c, testudo_name in pairs:
            if testudo_name and testudo_name != gis_name:
                aliases.append(testudo_name)
        aliases.append(f"{gis_name} ({num})")

        buildings[num] = {
            "name": gis_name,
            "code": code,
            "aliases": aliases,
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "outline": [[round(x, 6), round(y, 6)] for x, y in ring],
        }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "Maryland — College Park",
        "source": SOURCE,
        "sourceUrl": LAYER,
        "codeSource": "University of Maryland Schedule of Classes building lookup",
        "buildings": buildings,
    }, indent=1) + "\n")

    placed = sum(1 for b in buildings.values() if b["code"])
    missing = sorted(set(by_number) - {n for n in buildings})
    print(f"\nbuildings written:  {len(buildings)}")
    print(f"carrying a code:    {placed} of {len(codes)} codes joined")
    if missing:
        # A code whose building number has no footprint in the state's data.
        # These cannot be drawn, and offMap() will drop them, which is the
        # right answer — but it should be visible, not silent.
        print(f"!! codes with no footprint: "
              f"{', '.join(f'{n} ({by_number[n][0][1]})' for n in missing)}", file=sys.stderr)
    if ambiguous:
        print(f"!! one number, several codes: {'; '.join(ambiguous)}", file=sys.stderr)
    if no_geometry:
        print(f"!! no usable outline: {', '.join(no_geometry)}", file=sys.stderr)
    size = OUT_FILE.stat().st_size
    print(f"-> {OUT_FILE.relative_to(ROOT)} ({size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
