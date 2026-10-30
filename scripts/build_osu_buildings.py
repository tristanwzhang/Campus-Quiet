#!/usr/bin/env python3
"""
Build data/osu/buildings.json: Ohio State's own record of its buildings, from
the university's public ArcGIS server.

  https://gissvc.osu.edu/arcgis/rest/services/

Why this exists. The 3D buildings come from OpenStreetMap via Cesium, and the
map matches them by NAME. That fails in two ways on this campus:

  * OSM doesn't name every building. Thompson Library — the main library — has
    no name in OSM at all, so it could never be labelled, coloured or flown to.
  * Where both name a building, the spellings differ: OSM writes "Recreation &
    Physical Activity Center", Ohio State writes "and".

On a 22-building sample only 10 matched by exact name. This file supplies the
university's own names, aliases and coordinates so the map can place a building
OSM never named, and tell a campus building apart from the rest of Columbus.

Two layers are merged on building number:
  Apps/Campusmap_Buildings_POI/1  — names, aliases, scheduling code, lat/long
  Connectors/Tableau_Connector/2  — gross area, institutional type, campus

Usage:  python3 scripts/build_osu_buildings.py
"""

import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "osu" / "buildings.json"
BASE = "https://gissvc.osu.edu/arcgis/rest/services"
SOURCE_URL = f"{BASE}/Apps/Campusmap_Buildings_POI/MapServer/1"

POI_FIELDS = ("BLDG_NUM,BLDG_NAME,ComName,FormalName,AlsoKnownAs,"
              "SchedulingAbbreviation,Address,City,Latitude,Longitude,Status,PhotoLink")
TAB_FIELDS = "BLDG_NUM,GrossArea,InstType,Campus"


def query(layer, fields, where="1=1", geometry=False):
    params = {
        "where": where, "outFields": fields, "f": "json", "resultRecordCount": 5000,
        "returnGeometry": "true" if geometry else "false",
    }
    if geometry:
        params["outSR"] = 4326          # WGS84, what Cesium wants
        # Generalise the outline. Full fidelity is tens of thousands of points
        # for a file every visitor downloads; ~2 m is finer than the building
        # footprints read at any zoom this map allows.
        params["maxAllowableOffset"] = 0.00002
    url = f"{BASE}/{layer}/query?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (CampusQuiet build)"})
    data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace"))
    if "error" in data:
        raise RuntimeError(f"{layer}: {data['error']}")
    feats = data.get("features", [])
    # With geometry the caller needs the whole feature, not just its attributes.
    return feats if geometry else [f["attributes"] for f in feats]


def clean(v):
    v = (v or "").strip() if isinstance(v, str) else v
    return v or None


def ring_area_sqft(ring):
    """Rough planar area of a lon/lat ring, in square feet."""
    if len(ring) < 3:
        return 0.0
    lat0 = sum(p[1] for p in ring) / len(ring)
    mx = 364_000 * math.cos(math.radians(lat0))   # feet per degree of longitude
    my = 364_000                                   # feet per degree of latitude
    total = 0.0
    for i in range(len(ring)):
        x1, y1 = ring[i][0] * mx, ring[i][1] * my
        x2, y2 = ring[(i + 1) % len(ring)][0] * mx, ring[(i + 1) % len(ring)][1] * my
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def main():
    poi = query("Apps/Campusmap_Buildings_POI/MapServer/1", POI_FIELDS, "City='Columbus'")
    tab = {a["BLDG_NUM"]: a for a in query("Connectors/Tableau_Connector/MapServer/2",
                                           TAB_FIELDS, "City='Columbus'")}
    print(f"POI rows: {len(poi)} | Tableau rows: {len(tab)}")

    out, skipped = {}, 0
    for a in poi:
        num = clean(a.get("BLDG_NUM"))
        extra = tab.get(num, {})
        try:
            lat, lon = float(a.get("Latitude")), float(a.get("Longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        name = clean(a.get("BLDG_NAME"))
        if not name:
            skipped += 1
            continue
        # Every spelling Ohio State knows this building by. The map tries each
        # against the OSM name before giving up and drawing it from lat/long.
        aliases = []
        for f in ("ComName", "FormalName", "AlsoKnownAs"):
            v = clean(a.get(f))
            if v and v != name and v not in aliases:
                aliases.append(v)
        entry = {"name": name, "code": clean(a.get("SchedulingAbbreviation"))}
        if aliases: entry["aliases"] = aliases
        if lat is not None: entry["lat"], entry["lon"] = round(lat, 6), round(lon, 6)
        for key, src in (("area", extra.get("GrossArea")), ("use", clean(extra.get("InstType"))),
                         ("campus", clean(extra.get("Campus"))), ("status", clean(a.get("Status"))),
                         ("photo", clean(a.get("PhotoLink"))), ("address", clean(a.get("Address")))):
            if src: entry[key] = src
        out[num or name] = entry

    # Footprints, for buildings OpenStreetMap doesn't carry. Only the ones with
    # a scheduling code: those are the buildings the rest of the pipeline can
    # join to, and fetching all 534 would bloat a file every visitor downloads.
    shapes = query("Apps/Campusmap_Buildings_POI/MapServer/1",
                   "BLDG_NUM", "City='Columbus' AND SchedulingAbbreviation IS NOT NULL",
                   geometry=True)
    drawn = 0
    for f in shapes:
        num = clean(f["attributes"].get("BLDG_NUM"))
        entry = out.get(num)
        rings = (f.get("geometry") or {}).get("rings") or []
        if not entry or not rings:
            continue
        ring = max(rings, key=len)                      # outer ring
        ring = [[round(x, 6), round(y, 6)] for x, y in ring]
        entry["outline"] = ring
        # No height is published — BLDGHEIGHT and NUMSTORIES are empty on every
        # row — so estimate storeys from gross floor area over footprint area.
        # Marked as an estimate because that is what it is.
        foot = ring_area_sqft(ring)
        gross = entry.get("area")
        if foot > 500 and isinstance(gross, (int, float)) and gross > 0:
            storeys = max(1, min(round(gross / foot), 30))
            entry["heightM"] = round(storeys * 4.0, 1)
            entry["heightFrom"] = "estimated from gross area / footprint"
        drawn += 1
    print(f"  with footprint:       {drawn}")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "Ohio State — Columbus",
        "source": "Ohio State University GIS (gissvc.osu.edu)",
        "sourceUrl": SOURCE_URL,
        "buildings": out,
    }, indent=1) + "\n")

    withcode = sum(1 for e in out.values() if e.get("code"))
    withll = sum(1 for e in out.values() if "lat" in e)
    main_campus = sum(1 for e in out.values() if e.get("campus") == "Columbus")
    print(f"written: {len(out)}  (skipped {skipped} unnamed)")
    print(f"  with scheduling code: {withcode}")
    print(f"  with coordinates:     {withll}")
    print(f"  main Columbus campus: {main_campus}  (rest is Medical Center / off campus)")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
