#!/usr/bin/env python3
"""
Build data/utsg/buildings.json (the register app.js joins on) and rename the keys
of data/utsg/class_activity.json from U of T's building CODES to the university's
own building NAMES.

Sources, in the order they are trusted:

  names, building numbers, addresses, coordinates
      The University's own campus map, map.utoronto.ca (a Concept3D site). The
      timetable's `buildingUrl` for every meeting is `map.utoronto.ca/?id=1809#!m/<id>`,
      so each building code already names its map record; this script reads that
      record: `Name | CODE`, `CODE | Building #NNN`, address, lat/lng. Nothing is
      matched by name.

  footprints
      OpenStreetMap (ODbL). The map record is a POINT, so the footprint is the OSM
      building that contains it, or the nearest one within NEAR_M metres. A building
      with no footprint close to its point is left without an outline rather than
      given a neighbour's.

  FALLBACKS
      Nine codes (UC, WI, WE, WW, WO, RL, IN, SD, WS) point at map ids that now 404.
      Their records exist under other ids; the ones below are read from the same
      map's other records that carry the code. See each entry for what was used.
      A code with no source at all (ON, TL, BY, UP) is NOT placed.

Usage:  python3 scripts/build_utsg_buildings.py
"""

import json
import math
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "utsg"
CACHE = DATA / ".cache"
KEY = "0001085cc708b9cef47080f064612ca5"          # the map site's own public key
MAP_ID = 1809
NEAR_M = 30.0
BBOX = (43.650, -79.415, 43.675, -79.375)          # S, W, N, E

# Codes whose own map id 404s. Name: Wikipedia's list of U of T buildings AND the
# map's own records that carry the code (Registrar offices, libraries, dining).
# Point: that record's coordinates -- a point inside or at the building.
FALLBACKS = {
    "UC": ("University College", 43.662716, -79.395561, "map: 'Registrar | University College | UC'"),
    "WI": ("Wilson Hall", 43.661549, -79.400879, "map: 'Dining Commons | WI'; Wikipedia list"),
    "WE": ("Wetmore Hall", 43.662289, -79.40052, "map: 'Registrar | New College | WE'; Wikipedia list"),
    "WW": ("Woodsworth College", 43.666374, -79.399071, "map: 'Registrar | Woodsworth College | WW'"),
    "WO": ("Woodsworth College Residence", 43.667267, -79.399429, "map: 'Rotman Commerce | WO'; Wikipedia list"),
    "RL": ("Robarts Library", 43.664902, -79.399551, "map record 959690 'Robarts Library | RL'"),
    "IN": ("Innis College", 43.66555, -79.399529, "map: 'Registrar | Innis College | IN'"),
    "WS": ("Warren Stevens Building", 43.662861, -79.401039, "map record 959693 'Athletic Centre | WS | Warren Stevens Building'"),
}


def get(url, cache_name=None, data=None, headers=None):
    p = CACHE / cache_name if cache_name else None
    if p and p.exists():
        return p.read_bytes()
    req = urllib.request.Request(url, data=data, headers=headers or {"User-Agent": "CampusQuiet/1.0"})
    body = urllib.request.urlopen(req, timeout=120).read()
    if p:
        CACHE.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body)
    return body


def official(map_id):
    try:
        r = json.loads(get(f"https://api.concept3d.com/locations/{map_id}?map={MAP_ID}&key={KEY}",
                           f"loc_{map_id}.json"))
    except Exception:                                  # noqa: BLE001
        return None
    d = r if isinstance(r, dict) else r[0]
    desc = d.get("description") or ""
    num = re.search(r"Building #(\d+)", desc)
    addr = re.search(r"<h3>(.*?)</h3>", desc, re.S)
    name = d["name"].split(" | ")[0].strip()
    if "Correct rendering" in name:
        return None
    return {"name": name, "lat": d["lat"], "lon": d["lng"],
            "number": num.group(1) if num else None,
            "address": unescape(re.sub(r"<br>", ", ", addr.group(1))).strip() if addr else None}


# ── geometry (metres, local plane) ──
def to_m(lon, lat, lat0=43.664):
    return (lon * math.cos(math.radians(lat0)) * 111320, lat * 110574)


def inside(pt, ring):
    x, y = pt
    c = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            c = not c
    return c


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def distance(pt, ring):
    return 0.0 if inside(pt, ring) else min(seg_dist(pt, a, b) for a, b in zip(ring, ring[1:] + ring[:1]))


def simplify(ring, eps=0.00002):
    out = [ring[0]]
    for p in ring[1:]:
        if abs(p[0] - out[-1][0]) > eps or abs(p[1] - out[-1][1]) > eps:
            out.append(p)
    return out if len(out) >= 3 else ring


def footprints():
    q = f"[out:json][timeout:90];way[building]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});out geom;"
    body = get("https://overpass-api.de/api/interpreter", "osm_buildings.json",
               data=("data=" + urllib.parse.quote(q)).encode(),
               headers={"User-Agent": "CampusQuiet/1.0 (contact via campusquiet.com)",
                        "Content-Type": "application/x-www-form-urlencoded"})
    out = []
    for w in json.loads(body)["elements"]:
        g = w.get("geometry") or []
        if len(g) >= 4:
            ring = [(p["lon"], p["lat"]) for p in g[:-1]]
            out.append((ring, [to_m(*p) for p in ring]))
    return out


import urllib.parse  # noqa: E402  (used by footprints)


def main():
    activity = json.loads((DATA / "class_activity.json").read_text())
    meetings = json.loads((DATA / "meetings.json").read_text())["meetings"]
    ids = {}
    for m in meetings:
        mm = re.search(r"#!m/(\d+)", m["url"] or "")
        if m["code"] and mm:
            ids.setdefault(m["code"], set()).add(mm.group(1))

    # Buildings with published hours but no classes (Hart House) are not in the class
    # data, so the hours file is the second place a code can come from. Their map record
    # id is read from the map itself (Hart House: 494521, "Hart House | HH", category 48654).
    EXTRA_IDS = {"HH": "494521"}
    hours_file = DATA / "building_hours.json"
    extra = sorted({e["code"] for e in json.loads(hours_file.read_text())["buildings"].values()
                    if e.get("code") in EXTRA_IDS}) if hours_file.exists() else []
    for c in extra:
        ids.setdefault(c, set()).add(EXTRA_IDS[c])

    # Codes come from each record's own `code`, not its key: the keys are names once this
    # script has run, and it must be safe to run twice.
    codes = sorted({v.get("code", k) for k, v in activity["buildings"].items()} | set(extra))
    shapes = footprints()
    print(f"footprints: {len(shapes)}", file=sys.stderr)

    records, unplaced = {}, []
    for code in codes:
        rec = None
        if len(ids.get(code, ())) == 1:
            rec = official(next(iter(ids[code])))
        if rec:
            rec["source"] = "map.utoronto.ca"
        elif code in FALLBACKS:
            n, la, lo, why = FALLBACKS[code]
            rec = {"name": n, "lat": la, "lon": lo, "number": None, "address": None, "source": why}
        else:
            unplaced.append(code)
            continue
        pt = to_m(rec["lon"], rec["lat"])
        best = min(shapes, key=lambda s: distance(pt, s[1]))
        d = distance(pt, best[1])
        rec["outline"] = [list(p) for p in simplify(best[0])] if d <= NEAR_M else None
        rec["outlineDistM"] = round(d, 1)
        records[code] = rec

    # Several codes can land on one footprint (Bahen/VN, the Borden halves). Keep the
    # shared outline -- a building the register holds twice is still one building.
    reg = {}
    for code, r in records.items():
        entry = {"name": r["name"], "code": code, "aliases": [], "lat": r["lat"], "lon": r["lon"],
                 "outline": r["outline"], "number": r["number"], "address": r["address"],
                 "source": r["source"]}
        reg[code] = entry
    (DATA / "buildings.json").write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "University of Toronto — St. George",
        "source": "map.utoronto.ca (names, numbers, coordinates); OpenStreetMap (footprints)",
        "sourceUrl": "https://map.utoronto.ca/",
        "buildings": reg}, indent=1) + "\n")

    # Rename class_activity keys code -> official name.
    renamed, clash = {}, set()
    for key, v in activity["buildings"].items():
        code = v.get("code", key)
        name = records[code]["name"] if code in records else None
        if not name:
            continue
        if name in renamed:
            clash.add(name)
            continue
        renamed[name] = v
    activity["buildings"] = renamed
    (DATA / "class_activity.json").write_text(json.dumps(activity, indent=1) + "\n")

    (DATA / "building_codes.json").write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "map.utoronto.ca", "codes": {c: r["name"] for c, r in records.items()}}, indent=1) + "\n")

    print(f"placed {len(records)}/{len(codes)}; unplaced (no source): {unplaced}")
    print(f"no outline within {NEAR_M} m: {[c for c, r in records.items() if not r['outline']]}")
    print(f"name clashes dropped: {sorted(clash)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
