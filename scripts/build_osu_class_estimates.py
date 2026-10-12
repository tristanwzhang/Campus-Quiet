#!/usr/bin/env python3
"""
Build Ohio State class activity into data/osu/class_activity.json, matching the
shape build_class_estimates.py produces for Illinois so app.js can read either.

Source: Ohio State's public class search API (no key).
  https://content.osu.edu/v2/classes/search?q=&term=<term>&p=<page>

Two things differ from Illinois and both are improvements:

  * Buildings are joined on the BUILDING CODE, not the name. A meeting's
    facilityId looks like "RS0206" — the letter prefix is the same code the
    registrar's hours page prints as "(RS)". Names cannot be joined: the hours
    page says "Ag. Engineering", the class API says "Agricultural Engineering
    Bldg", and the API truncates at 30 characters ("Engineering Research and
    Educa"). On a sample, codes matched 43 of 47 buildings; names matched 33.

  * Every meeting carries facilityCapacity, so alongside the Illinois-style
    meeting count this records seats scheduled. app.js reads `hours`; `seats`
    is there for a better occupancy model later.

Regional campuses (Newark, Marion, Lima, Wooster, ATI) are excluded on the
section's own `campus` field rather than guessed at from building names.

Usage:
  python3 scripts/build_osu_class_estimates.py --cache     # save raw pages
  python3 scripts/build_osu_class_estimates.py --offline   # rebuild from cache
"""

import argparse
import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "osu" / "class_activity.json"
HOURS_FILE = ROOT / "data" / "osu" / "building_hours.json"
CACHE_DIR = ROOT / "data" / "osu" / ".cache"

API = "https://content.osu.edu/v2/classes/search"
TERM = "1268"          # Autumn 2026
TERM_LABEL = "2026/autumn"
CAMPUS = "Columbus"    # regional campuses are a different map
PAGE_CAP = 50          # the API stops at 10,000 results = 50 pages of 200

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# A real room is a building code followed by a room number ("RS0206"). Requiring
# the digits is what keeps out ONLINE and OFFCAMPUS, which are facilityId values
# too — matching the letters alone made ONLINE the busiest building on campus.
CODE_RE = re.compile(r"^([A-Z]{2,5})\d")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", re.I)


def fetch(q, page, cache, offline):
    # Subject names carry slashes ("Bosnian/Croatian/Serbian"), which would be
    # read as directories in a cache filename.
    safe = re.sub(r"[^A-Za-z0-9]+", "_", q) or "_"
    tag = f"q{safe}-p{page}.json"
    path = CACHE_DIR / tag
    # Always reuse a cached page: ~500 requests over several minutes will hit a
    # timeout sooner or later, and re-running should resume, not start over.
    if path.exists():
        raw = path.read_text(encoding="utf-8")
    elif offline:
        return None
    else:
        url = f"{API}?q={urllib.parse.quote(q)}&term={TERM}&p={page}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UIUC Spaces build)"})
        raw = None
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
                break
            except Exception as err:
                if attempt == 3:
                    print(f"  giving up on q={q!r} p={page}: {type(err).__name__}", flush=True)
                    return None
                time.sleep(2 * (attempt + 1))
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        time.sleep(0.25)
    # Course descriptions contain raw newlines, which strict JSON rejects.
    return json.loads(raw, strict=False)["data"]


def to_decimal(text):
    """'11:10 am' -> 11.1666. None when it can't be read exactly."""
    m = TIME_RE.match((text or "").strip())
    if not m:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "pm":
        hour += 12
    return hour + int(m.group(2)) / 60


def add_meeting(bucket, start, end):
    """Spread one meeting across the hours it covers, by fraction of each hour."""
    for h in range(24):
        overlap = min(end, h + 1) - max(start, h)
        if overlap > 0:
            bucket[h] += round(overlap, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="save raw pages for reuse")
    ap.add_argument("--offline", action="store_true", help="rebuild from cache only")
    args = ap.parse_args()

    hours = json.loads(HOURS_FILE.read_text())["buildings"]
    name_by_code = {v["code"]: k for k, v in hours.items()}

    seen_sections = set()
    counts = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    seats = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    code_names = {}
    stats = collections.Counter()

    def ingest(data):
        for course in data.get("courses", []):
            for sec in course.get("sections") or []:
                if sec.get("campus") != CAMPUS:
                    stats["skipped_other_campus"] += 1
                    continue
                key = sec.get("classNumber")
                if key in seen_sections:
                    continue
                seen_sections.add(key)
                for m in sec.get("meetings") or []:
                    fid = m.get("facilityId") or ""
                    code_match = CODE_RE.match(fid)
                    start = to_decimal(m.get("startTime"))
                    end = to_decimal(m.get("endTime"))
                    if not code_match or start is None or end is None:
                        stats["skipped_no_place_or_time"] += 1
                        continue
                    if end <= start:
                        stats["skipped_bad_range"] += 1
                        continue
                    code = code_match.group(1)
                    code_names.setdefault(code, m.get("facilityDescription") or code)
                    cap = m.get("facilityCapacity") or 0
                    for d in DAYS:
                        if m.get(d):
                            add_meeting(counts[code][d], start, end)
                            if cap:
                                tmp = [0.0] * 24
                                add_meeting(tmp, start, end)
                                for h in range(24):
                                    seats[code][d][h] += tmp[h] * cap
                    stats["meetings_used"] += 1

    # Page the unfiltered query first, then each subject it reveals, because the API
    # caps any single query at 10,000 results and Columbus alone exceeds that.
    subjects = set()
    for p in range(1, PAGE_CAP + 1):
        data = fetch("", p, args.cache, args.offline)
        if not data:
            break
        ingest(data)
        for c in data.get("courses", []):
            for s in c.get("sections") or []:
                if s.get("subject"):
                    subjects.add(s["subject"])
        if not data.get("nextPageLink"):
            break
    print(f"base sweep: {len(seen_sections)} sections, {len(subjects)} subjects")

    for i, subj in enumerate(sorted(subjects), 1):
        for p in range(1, PAGE_CAP + 1):
            data = fetch(subj, p, args.cache, args.offline)
            if not data:
                break
            ingest(data)
            if not data.get("nextPageLink"):
                break
        if i % 25 == 0 or i == len(subjects):
            print(f"  ...{i}/{len(subjects)} subjects, {len(seen_sections)} sections")

    buildings = {}
    for code, days in counts.items():
        name = name_by_code.get(code) or code_names.get(code, code)
        used = {d: [round(v, 2) for v in vals] for d, vals in days.items() if any(vals)}
        if not used:
            continue
        peak = max(max(v) for v in used.values())
        entry = {"peak": round(peak, 2), "hours": used, "code": code}
        s_used = {d: [round(v, 1) for v in vals] for d, vals in seats[code].items() if any(vals)}
        if s_used:
            entry["seats"] = s_used
            entry["seatsPeak"] = round(max(max(v) for v in s_used.values()), 1)
        entry["hasHours"] = code in name_by_code
        buildings[name] = entry

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "term": TERM_LABEL,
        "campus": "Ohio State — Columbus",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Weighted count of class meetings in progress. Not people. "
                "`seats` is the same weighting times each room's capacity.",
        "buildings": buildings,
    }, indent=1) + "\n")

    joined = sum(1 for e in buildings.values() if e["hasHours"])
    print(f"\nsections kept:     {len(seen_sections)}")
    print(f"meetings used:     {stats['meetings_used']}")
    print(f"skipped (campus):  {stats['skipped_other_campus']}")
    print(f"skipped (no place/time): {stats['skipped_no_place_or_time']}")
    print(f"buildings:         {len(buildings)}  ({joined} joined to hours, "
          f"{len(buildings) - joined} without)")
    print(f"hours buildings with no classes: "
          f"{sorted(set(name_by_code.values()) - set(buildings))}")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
