#!/usr/bin/env python3
"""
Build data/utsg/class_activity.json (and rooms-free summaries) for U of T St. George
from the Timetable Builder API the university itself runs:

    POST https://api.easi.utoronto.ca/ttb/getPageableCourses

Why this campus is different from the other three:
  * ONE api covers every division (ARTSC, APSC, FIS, FPEH, MUSIC, ARCLA) with a
    campus filter, so nothing is scraped page by page.
  * Each section carries currentEnrolment AND maxEnrolment -- people, not room size.
  * NO ROOM NUMBER is published. buildingRoomNumber is empty on every one of the
    ~6,400 meetings read on 2026-10-20, so U of T is building-level only. There is
    no rooms.json and "find a free room" cannot exist here.
  * The building is a short code (BA, SS, ...) whose buildingUrl is a Concept3D
    location id on map.utoronto.ca -- the join to the official map is free.
    build_utsg_buildings.py resolves the codes.

`hours` is weighted and counted exactly as the other campuses do it: a meeting
counts its type's weight in every clock hour it touches. `seats` is students
ENROLLED in the distinct sections meeting then.

Fall only (session 20269). Winter is 20271 -- sweep it before January.

Usage:  python3 scripts/build_utsg_class_estimates.py [--session 20269]
"""

import argparse
import collections
import json
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "utsg"
OUT_FILE = DATA / "class_activity.json"
RAW_FILE = DATA / "meetings.json"          # the sweep, kept so rebuilding is offline

URL = "https://api.easi.utoronto.ca/ttb/getPageableCourses"
DIVISIONS = ["APSC", "ARTSC", "FIS", "FPEH", "MUSIC", "ARCLA"]   # the St. George ones
SESSIONS = {"20269": "Fall 2026", "20271": "Winter 2027"}

# Same weights the other campuses use, onto the TTB's teachMethod codes.
TYPE_WEIGHTS = {"LEC": 3.0, "TUT": 1.0, "PRA": 1.5, "SEM": 1.0}
DEFAULT_WEIGHT = 1.0
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def post(body, tries=5):
    req = urllib.request.Request(
        URL, data=json.dumps(body).encode(),
        headers={"Origin": "https://ttb.utoronto.ca", "Content-Type": "application/json"})
    for i in range(tries):
        try:
            return ET.fromstring(urllib.request.urlopen(req, timeout=90).read())
        except Exception as e:                     # noqa: BLE001
            if i == tries - 1:
                raise
            print(f"  retry {i + 1}: {e}", file=sys.stderr)
            time.sleep(2 * (i + 1))


def sweep(session):
    rows, courses_seen = [], 0
    for div in DIVISIONS:
        page, got = 1, 0
        while True:
            body = {"courseCodeAndTitleProps": {"courseCode": "", "courseTitle": "",
                                                "courseSectionCode": "", "searchCourseDescription": True},
                    "departmentProps": [], "campuses": ["St. George"], "sessions": [session],
                    "requirementProps": [], "instructor": "", "courseLevels": [], "deliveryModes": [],
                    "dayPreferences": [], "timePreferences": [], "divisions": [div],
                    "creditWeights": [], "availableSpace": False, "waitListable": False,
                    "page": page, "pageSize": 20, "direction": "asc"}
            root = post(body)
            courses = root.findall("./payload/pageableCourse/courses/courses")
            total = int(root.findtext("./payload/pageableCourse/total") or 0)
            if not courses:
                break
            for c in courses:
                for s in c.findall("./sections/sections"):
                    if s.findtext("cancelInd") == "Y":
                        continue
                    for m in s.findall("./meetingTimes/meetingTimes"):
                        b = m.find("building")
                        rows.append({
                            "div": div, "course": c.findtext("code"), "section": s.findtext("name"),
                            "method": s.findtext("teachMethod"),
                            "mode": s.findtext("./deliveryModes/deliveryModes/mode"),
                            "day": int(m.findtext("./start/day")),
                            "start": int(m.findtext("./start/millisofday")) / 3.6e6,
                            "end": int(m.findtext("./end/millisofday")) / 3.6e6,
                            "code": b.findtext("buildingCode") or "",
                            "url": b.findtext("buildingUrl") or "",
                            "repeat": m.findtext("repetitionTime"),
                            "enrolled": int(s.findtext("currentEnrolment") or 0),
                            "cap": int(s.findtext("maxEnrolment") or 0),
                        })
            got += len(courses)
            courses_seen += len(courses)
            print(f"{div} page {page}: {got}/{total}", file=sys.stderr)
            if got >= total:
                break
            page += 1
    return rows, courses_seen


def hours_touched(start, end):
    """Same convention as every other builder: a part-hour counts whole, a class
    ending exactly on the hour does not reach into it."""
    return range(int(start), min(int(end - 1 / 60) + 1, 24))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", default="20269")
    ap.add_argument("--offline", action="store_true")
    args = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)

    if args.offline and RAW_FILE.exists():
        raw = json.loads(RAW_FILE.read_text())
        rows = raw["meetings"]
    else:
        rows, n = sweep(args.session)
        RAW_FILE.write_text(json.dumps({
            "session": args.session, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "courses": n, "meetings": rows}) + "\n")

    stats = collections.Counter()
    slots = {}                 # (code, day, start, end, section-key) -> weight, enrolled
    for r in rows:
        if not r["code"]:
            stats["no_building"] += 1
            continue
        if r["mode"] == "SYNC":
            stats["online_sync"] += 1
            continue
        day = DAYS[r["day"] - 1]
        weight = TYPE_WEIGHTS.get(r["method"], DEFAULT_WEIGHT)
        if r["method"] not in TYPE_WEIGHTS:
            stats[f"unweighted:{r['method']}"] += 1
        key = (r["code"], day, round(r["start"], 3), round(r["end"], 3))
        # Two sections of one course in one building at one time are different
        # classes; a cross-listed course is one class under several codes. Keep a
        # per-section record and drop only exact duplicates.
        sec = (r["course"], r["section"])
        slots.setdefault(key, {})[sec] = (weight, r["enrolled"])
        stats["meetings_used"] += 1

    counts = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    seats = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    for (code, day, start, end), secs in slots.items():
        weight = sum(w for w, _ in secs.values())
        people = sum(p for _, p in secs.values())
        for h in hours_touched(start, end):
            counts[code][day][h] += weight
            seats[code][day][h] += people

    buildings = {}
    for code, days in counts.items():
        used = {d: [round(v, 2) for v in vals] for d, vals in days.items() if any(vals)}
        if not used:
            continue
        s_used = {d: [round(v, 1) for v in vals] for d, vals in seats[code].items() if any(vals)}
        buildings[code] = {
            "peak": round(max(max(v) for v in used.values()), 2), "hours": used, "code": code,
            "seats": s_used, "seatsPeak": round(max(max(v) for v in s_used.values()), 1),
        }

    OUT_FILE.write_text(json.dumps({
        "term": SESSIONS.get(args.session, args.session),
        "campus": "University of Toronto — St. George",
        "source": "University of Toronto Timetable Builder",
        "sourceUrl": "https://ttb.utoronto.ca/",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Weighted count of class meetings in progress. Not people. Weights and hour "
                "counting match the other campuses. `seats` is students ENROLLED in the "
                "sections meeting then, summed over distinct sections. Keyed by building CODE "
                "until build_utsg_buildings.py renames it to the official name. Meetings that "
                "repeat every second week are counted as weekly.",
        "buildings": buildings,
    }, indent=1) + "\n")
    print(dict(stats), f"buildings: {len(buildings)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
