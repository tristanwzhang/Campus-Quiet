#!/usr/bin/env python3
"""
Build Ohio State building hours into data/osu/building_hours.json, in the same
shape build_hours.py produces for Illinois, so app.js can read either campus.

Source: the Registrar's "Classroom Pool Building Schedule", which publishes
per-day open/close times per building. Unlike Illinois — where hours are spread
across a Facilities spreadsheet plus library, dining and rec feeds — Ohio State
puts them on one page, so this is the only hours fetcher the campus needs.

  https://registrar.osu.edu/staff-resources/class-catalog-and-space/
      classroom-pool-building-schedule/autumn-2026-classroom-pool-building-schedule/

Usage:
  python3 scripts/build_osu_hours.py                 # fetch and write
  python3 scripts/build_osu_hours.py --print-skipped  # also list what was dropped

Nothing is guessed. 10 of ~399 published day-entries are malformed ('7am-10'
with no am/pm, '8am-' with no closing time) and are SKIPPED rather than
interpreted: '10' after a 7am open is probably 10pm, but probably is not good
enough for a building someone walks to. Skipped days are reported, and a
building with no parsable day at all is left out of the file entirely so the
map shows "no data" instead of a wrong answer.
"""

import argparse
import html
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "osu" / "building_hours.json"

SOURCE_NAME = "Ohio State registrar classroom pool building schedule"
SOURCE_URL = (
    "https://registrar.osu.edu/staff-resources/class-catalog-and-space/"
    "classroom-pool-building-schedule/autumn-2026-classroom-pool-building-schedule/"
)
# Autumn 2026, read off the meeting dates in Ohio State's own class API
# (content.osu.edu) rather than typed from a calendar page.
TERM = ("2026-08-25", "2026-12-09")

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# "Ag. Engineering (AE) | 590 Woody Hayes Drive"
BUILDING_RE = re.compile(r"^(?P<name>.{2,70}?)\s*\((?P<code>[A-Z0-9]{2,6})\)\s*\|\s*(?P<addr>.+)$")
DAY_RE = re.compile(r"^(?P<day>" + "|".join(d.capitalize() for d in DAYS) + r"):\s*(?P<val>.+)$")
# Case-insensitive on purpose: the page mixes "DAY HOURS:" with "Lab Hours:"
# and "Library Hours:". Matching only upper case let a room's hours fall through
# and overwrite the building's own, which reads as valid data and is wrong.
SECTION_RE = re.compile(r"^[A-Za-z][A-Za-z &/\.]{2,30}:$")
# A time is sometimes split across lines by a tag break: "Monday: 7am-10" then
# "pm", or even "8am-" / "10" / "pm". These fragments rejoin onto the line above.
CONTINUATION_RE = re.compile(r"^(am|pm|\d{1,2})$", re.I)
# 7am-8pm | 7:30am-10:30pm | 2pm to 6pm — both halves must carry am/pm
RANGE_RE = re.compile(
    r"^(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<s1>am|pm)\s*(?:-|to|–|—)\s*"
    r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<s2>am|pm)$",
    re.I,
)


def page_lines(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UIUC Spaces hours build)"})
    raw = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", raw))
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    merged = []
    for line in lines:
        if merged and CONTINUATION_RE.match(line):
            merged[-1] += line
        else:
            merged.append(line)
    return merged


def to_decimal(hour, minute, suffix):
    """12-hour clock -> hours since midnight. 12am = 0, 12pm = 12."""
    hour = int(hour) % 12
    if suffix.lower() == "pm":
        hour += 12
    return hour + (int(minute) / 60 if minute else 0)


def parse_range(value):
    """[[open, close]] , [] for closed, or None when it can't be read exactly."""
    v = value.strip().rstrip(".")
    if v.lower() in ("closed", "close", "closed."):
        return []
    m = RANGE_RE.match(v)
    if not m:
        return None
    start = to_decimal(m["h1"], m["m1"], m["s1"])
    end = to_decimal(m["h2"], m["m2"], m["s2"])
    # A close at or before the open means it runs past midnight (7am-12am), the
    # same convention app.js uses: close > 24 is tomorrow morning.
    if end <= start:
        end += 24
    return [[start, end]]


def parse(lines):
    """-> (buildings dict, skipped list)"""
    buildings, skipped = {}, []
    current, section = None, None

    for line in lines:
        bld = BUILDING_RE.match(line)
        if bld and bld["name"].lower() not in ("day hours", "library hours"):
            current = {
                "name": bld["name"].strip(),
                "code": bld["code"],
                "address": bld["addr"].strip(),
                "weekly": {},
            }
            buildings[current["name"]] = current
            section = None
            continue

        if SECTION_RE.match(line):
            section = line.rstrip(":").strip().lower()
            continue

        day = DAY_RE.match(line)
        # Only DAY HOURS describes the building itself; LIBRARY/LAB HOURS are a
        # room inside it and would otherwise overwrite the building's own hours.
        if day and current and section == "day hours":
            ranges = parse_range(day["val"])
            if ranges is None:
                skipped.append((current["name"], day["day"], day["val"]))
            else:
                current["weekly"][day["day"].lower()] = ranges

    return buildings, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-skipped", action="store_true")
    args = ap.parse_args()

    lines = page_lines(SOURCE_URL)
    parsed, skipped = parse(lines)

    out = {}
    dropped = []
    for name, b in parsed.items():
        # Every day must be accounted for; a half-read building is worse than
        # an absent one, because the map would treat missing days as closed.
        if sorted(b["weekly"]) != sorted(DAYS):
            dropped.append((name, sorted(set(DAYS) - set(b["weekly"]))))
            continue
        out[name] = {
            "source": SOURCE_NAME,
            "sourceUrl": SOURCE_URL,
            "code": b["code"],
            "address": b["address"],
            "valid": list(TERM),
            "weekly": {d: b["weekly"][d] for d in DAYS},
        }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "Ohio State",
        "term": "Autumn 2026",
        "campusClosedDates": [],
        "buildings": out,
    }, indent=1) + "\n")

    print(f"buildings found:   {len(parsed)}")
    print(f"buildings written: {len(out)}  -> {OUT_FILE.relative_to(ROOT)}")
    if dropped:
        print(f"dropped (incomplete week): {len(dropped)}")
        for name, missing in dropped:
            print(f"   {name}: missing {', '.join(missing)}")
    if skipped:
        print(f"unreadable day-entries: {len(skipped)}")
        if args.print_skipped:
            for name, day, val in skipped:
                print(f"   {name} / {day}: {val!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
