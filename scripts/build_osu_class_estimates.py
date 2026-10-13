#!/usr/bin/env python3
"""
Build Ohio State class activity into data/osu/class_activity.json, matching the
shape build_class_estimates.py produces for Illinois so app.js can read either.

Source: Ohio State's public class search API (no key).
  https://content.osu.edu/v2/classes/search?q=&term=<term>&p=<page>&campus=col&component=<slug>

The API publishes real facet filters, so the sweep asks for what it wants
instead of searching for subject names as free text: `campus=col` drops the
regional campuses at the source, and `subject=<code>` takes one subject at a
time.

One subject at a time is not just tidier, it is the only shape that comes back
complete. Paging is not stable across a long sweep: asking for all 7,233
lectures (37 pages) returned 117 fewer Computer Science sections than asking for
Computer Science alone (6 pages), and splitting by catalog number lost about as
many. Every subject is a handful of pages, so each one is checked against the
`totalItems` the API reports for it, and any shortfall is printed rather than
quietly accepted.

Two things differ from Illinois and both are improvements:

  * Buildings are joined on the BUILDING CODE, not the name. A meeting's
    facilityId looks like "RS0206" — the letter prefix is the same code the
    registrar's hours page prints as "(RS)". Names cannot be joined: the hours
    page says "Ag. Engineering", the class API says "Agricultural Engineering
    Bldg", and the API truncates at 30 characters ("Engineering Research and
    Educa"). On a sample, codes matched 43 of 47 buildings; names matched 33.

  * Every meeting carries facilityCapacity, so alongside the meeting count this
    records seats scheduled. A full lecture hall and a seminar room are not the
    same amount of building in use, and capacity says so where a count can't.
    app.js prefers `seats` and falls back to `hours`.

`hours` is weighted and counted exactly as build_class_estimates.py does it for
Illinois — a meeting counts its component's weight in every clock hour it
touches — so the two campuses' files mean the same thing and can be compared.

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
CAMPUS_FILTER = "col"  # the API's own slug for it
PAGE_CAP = 50          # the API stops at 10,000 results = 50 pages of 200

RESULT_CAP = 10000     # the API truncates any query past this

# The same weights build_class_estimates.py gives Illinois, mapped onto Ohio
# State's component names: a lecture fills a building in a way a recitation
# doesn't. Anything unlisted counts as one.
COMPONENT_WEIGHTS = {
    "Lecture": 3.0,
    "Laboratory": 1.5,
    "Recitation": 1.0,      # Illinois calls this a discussion
    "Seminar": 1.0,
    "Workshop": 1.0,
    "Clinical": 0.5,
    "Field Experience": 0.5,
    "Independent Study": 0.2,
}
DEFAULT_WEIGHT = 1.0

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# A real room is a building code followed by a room number ("RS0206"). Requiring
# the digits is what keeps out ONLINE and OFFCAMPUS, which are facilityId values
# too — matching the letters alone made ONLINE the busiest building on campus.
CODE_RE = re.compile(r"^([A-Z]{2,5})\d")
TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*(am|pm)$", re.I)


def fetch(subject, page, cache, offline, bucket=None):
    tag = f"{subject or bucket or 'all'}-p{page}.json"
    path = CACHE_DIR / tag
    # Always reuse a cached page: ~500 requests over several minutes will hit a
    # timeout sooner or later, and re-running should resume, not start over.
    if path.exists():
        raw = path.read_text(encoding="utf-8")
    elif offline:
        return None
    else:
        url = f"{API}?q=&term={TERM}&p={page}&campus={CAMPUS_FILTER}"
        if subject:
            url += f"&subject={urllib.parse.quote(subject)}"
        if bucket:
            url += f"&catalog-number={urllib.parse.quote(bucket)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UIUC Spaces build)"})
        raw = None
        for attempt in range(4):
            try:
                raw = urllib.request.urlopen(req, timeout=45).read().decode("utf-8", "replace")
                break
            except Exception as err:
                if attempt == 3:
                    print(f"  giving up on {tag}: {type(err).__name__}", flush=True)
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


def hours_touched(start, end):
    """The clock hours a meeting occupies. A part-hour counts as a whole one, and
    a class ending exactly on the hour does not reach into it — the convention
    build_class_estimates.py uses for Illinois, kept so the two files compare."""
    return range(int(start), min(int(end - 1 / 60) + 1, 24))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", action="store_true", help="save raw pages for reuse")
    ap.add_argument("--offline", action="store_true", help="rebuild from cache only")
    args = ap.parse_args()

    hours = json.loads(HOURS_FILE.read_text())["buildings"]
    name_by_code = {v["code"]: k for k, v in hours.items()}

    seen_sections = set()
    slots = {}             # (room, day, start, end) -> (weight, capacity, code)
    counts = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    seats = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    code_names = {}
    stats = collections.Counter()
    by_component = collections.Counter()

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
                    weight = COMPONENT_WEIGHTS.get(sec.get("component"), DEFAULT_WEIGHT)
                    if not weight:
                        stats["skipped_zero_weight"] += 1
                        continue
                    code = code_match.group(1)
                    code_names.setdefault(code, m.get("facilityDescription") or code)
                    cap = m.get("facilityCapacity") or 0
                    # A room holds one thing at a time, so two sections in the
                    # same room at the same hour are one event listed twice —
                    # the marching band is MUSIC 2205.01 and 7205.01, the same
                    # rehearsal under an undergraduate and a graduate number.
                    # Counting the slot once, at the heavier of the two weights,
                    # is the only reading of it that can be true.
                    for d in DAYS:
                        if m.get(d):
                            slot = (fid, d, start, end)
                            if weight > slots.get(slot, (0,))[0]:
                                slots[slot] = (weight, cap, code)
                            else:
                                stats["duplicate_room_hour"] += 1
                    stats["meetings_used"] += 1
                    by_component[sec.get("component")] += 1

    # Subject codes come from the courses themselves ("CSE"), which is the filter
    # slug lowercased. The first pass is capped at 10,000 results like any other,
    # so anything a later sweep reveals is swept in turn until nothing is new.
    def subject_codes(data):
        return {c["course"]["subject"] for c in data.get("courses", [])
                if (c.get("course") or {}).get("subject")}

    def page_through(subject=None, bucket=None):
        """-> (sections this query reported, pages fetched, codes seen)"""
        reported, pages, codes = None, 0, set()
        for p in range(1, PAGE_CAP + 1):
            data = fetch(subject, p, args.cache, args.offline, bucket)
            if not data:
                break
            if p == 1:
                reported = data.get("totalItems")
            pages += 1
            codes |= subject_codes(data)
            ingest(data)
            if not data.get("nextPageLink"):
                break
        return reported, pages, codes

    def facet(data, slug):
        for f in data.get("filters") or []:
            if f.get("slug") == slug:
                return {i["term"]: i["count"] for i in f.get("items") or []}
        return {}

    # Discovery has to see every class at least once or a whole subject could go
    # missing, and an unfiltered sweep stops at the cap. Catalog number is the one
    # facet whose published buckets add up to the campus total, so walking those
    # eight reaches everything. Sections dropped along the way don't matter here —
    # only the subject codes do, and the per-subject sweep that follows is what
    # actually has to be complete.
    boot = fetch(None, 1, args.cache, args.offline)
    if not boot:
        print("could not reach the class API", file=sys.stderr)
        return 1
    buckets = facet(boot, "catalog-number")
    print(f"campus has {sum(buckets.values())} classes in {len(buckets)} catalog-number buckets")

    subjects, pages = set(), 0
    for b in sorted(buckets):
        _, got, codes = page_through(bucket=b)
        subjects |= codes
        pages += got
    print(f"discovery: {pages} pages, {len(seen_sections)} sections, {len(subjects)} subjects")

    short, done, total_pages = [], set(), pages
    while subjects - done:
        for code in sorted(subjects - done):
            done.add(code)
            before = len(seen_sections)
            reported, pages, found = page_through(code.lower())
            subjects |= found
            total_pages += pages
            if reported and reported >= RESULT_CAP:
                short.append(f"{code} at the {RESULT_CAP} cap")
            elif reported and len(seen_sections) - before and pages == 0:
                short.append(f"{code} unreachable")
            if len(done) % 50 == 0:
                print(f"  ...{len(done)}/{len(subjects)} subjects, "
                      f"{len(seen_sections)} sections", flush=True)
    print(f"swept {len(done)} subjects in {total_pages} pages, {len(seen_sections)} sections")
    if short:
        print(f"!! incomplete: {short}", file=sys.stderr)

    # Every surviving slot, once.
    for (fid, day, start, end), (weight, cap, code) in slots.items():
        for h in hours_touched(start, end):
            counts[code][day][h] += weight
            seats[code][day][h] += weight * cap

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
                "Weights and hour counting match data/class_activity.json. "
                "`seats` is the same weighting times each room's capacity.",
        "buildings": buildings,
    }, indent=1) + "\n")

    joined = sum(1 for e in buildings.values() if e["hasHours"])
    print(f"\nsections kept:     {len(seen_sections)}")
    print(f"meetings used:     {stats['meetings_used']}  "
          f"({', '.join(f'{k}={v}' for k, v in by_component.most_common())})")
    print(f"skipped (campus):  {stats['skipped_other_campus']}")
    print(f"skipped (no place/time): {stats['skipped_no_place_or_time']}")
    print(f"room-hours kept:   {len(slots)}  "
          f"(dropped {stats['duplicate_room_hour']} already taken by another section)")
    print(f"buildings:         {len(buildings)}  ({joined} joined to hours, "
          f"{len(buildings) - joined} without)")
    print(f"hours buildings with no classes: "
          f"{sorted(set(name_by_code.values()) - set(buildings))}")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
