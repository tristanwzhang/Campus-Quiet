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

LIB_URL = "https://library.osu.edu/hours"
LIB_SOURCE = "Ohio State University Libraries hours"

# Which published libraries are a BUILDING in their own right, and the scheduling
# code the rest of the pipeline joins on. The others — Architecture, Geology,
# Music & Dance, Fine Arts, FAES — are departments inside Knowlton, Orton,
# Sullivant, the Wexner Center and Ag Admin, and their hours are NOT those
# buildings' hours (Knowlton's doors are open an hour past its library), so they
# are deliberately left out rather than overwriting a host building.
LIBRARY_BUILDINGS = {
    "Thompson Library": "LI",
    "18th Avenue Library": "SE",
}

# Buildings that publish their own hours but aren't in the registrar's classroom
# pool. Read off the official page by hand — the same approach Illinois uses for
# Beckman — because each unit publishes in its own format on its own site and
# there is no feed to scrape. Keep the sourceUrl: it's how the next person
# re-checks these when the term turns over.
HAND_ENTERED = {
    "OU": {
        "name": "Ohio Union",
        "source": "Ohio Union published building hours",
        "sourceUrl": "https://ohiounion.osu.edu/visiting/hours",
        "weekly": {
            "monday":    [[8, 23]], "tuesday": [[8, 23]], "wednesday": [[8, 23]],
            "thursday":  [[8, 23]], "friday":  [[8, 23]],
            "saturday":  [[10, 23]], "sunday": [[10, 23]],
        },
        # "Hours vary during holidays, academic breaks and the summer months":
        # Academic Break and Summer Hours are 8am-8pm weekdays, 10am-8pm weekends.
        # Applied only to the two spans the registrar actually calls a Break;
        # single holidays like Labor Day aren't named as academic breaks.
        "breakWeekly": {
            "monday":    [[8, 20]], "tuesday": [[8, 20]], "wednesday": [[8, 20]],
            "thursday":  [[8, 20]], "friday":  [[8, 20]],
            "saturday":  [[10, 20]], "sunday": [[10, 20]],
        },
        "breaks": [("2026-10-15", "2026-10-16"), ("2026-11-25", "2026-11-27")],
    },
}

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


# "9:00 a.m. - 4:30 p.m.", "7:30am - 11:30pm", "11:00am - 12:00am", "8:00am - 4:00am"
LIB_RANGE_RE = re.compile(
    r"(?P<h1>\d{1,2})(?::(?P<m1>\d{2}))?\s*(?P<s1>a\.?m\.?|p\.?m\.?)\s*[-–—]\s*"
    r"(?P<h2>\d{1,2})(?::(?P<m2>\d{2}))?\s*(?P<s2>a\.?m\.?|p\.?m\.?)",
    re.I,
)


def parse_library_cell(value):
    """[[open, close]] | [] for closed | None when it can't be read exactly."""
    v = re.sub(r"\s+", " ", (value or "")).strip()
    if not v:
        return None
    low = v.lower()
    if low.startswith("closed"):
        return []
    # "See <X> website for hours." and "<ID> Swipe Required" carry no times.
    if "website for hours" in low or "swipe required" in low:
        return None
    # Appointment-only reading rooms are open to a booking, not to someone
    # looking for a seat, so they are reported as unknown rather than open.
    if "appointment only" in low:
        return None
    if low.startswith("24 hours"):
        return [[0, 24]]
    m = LIB_RANGE_RE.search(v)
    if not m:
        return None
    start = to_decimal(m["h1"], m["m1"], m["s1"].replace(".", "")[:2])
    end = to_decimal(m["h2"], m["m2"], m["s2"].replace(".", "")[:2])
    if end <= start:
        end += 24
    return [[start, end]]


def library_hours():
    """-> ({code: {date: ranges}}, [notes]) for libraries that are buildings."""
    req = urllib.request.Request(LIB_URL, headers={"User-Agent": "Mozilla/5.0 (UIUC Spaces hours build)"})
    raw = urllib.request.urlopen(req, timeout=40).read().decode("utf-8", "replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.S | re.I)

    def cells(r):
        return [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip()
                for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S | re.I)]

    if not rows:
        return {}, ["library hours table not found"]
    header = cells(rows[0])
    dates = []
    for c in header[2:9]:
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{2})", c)
        dates.append(f"20{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None)

    out, notes = {}, []
    for r in rows[1:]:
        c = cells(r)
        if len(c) < 9:
            continue
        loc = re.sub(r"\s*Upcoming Hours\s*$", "", re.sub(r"\s+", " ", c[0])).strip()
        svc = re.sub(r"\s+", " ", c[1]).strip()
        if svc or loc not in LIBRARY_BUILDINGS:
            continue                       # sub-spaces and in-building libraries
        code = LIBRARY_BUILDINGS[loc]
        byday = {}
        for date, raw_cell in zip(dates, c[2:9]):
            if not date:
                continue
            parsed = parse_library_cell(raw_cell)
            if parsed is None:
                notes.append(f"{loc} / {date}: {re.sub(chr(92)+'s+',' ',raw_cell).strip()!r}")
            else:
                byday[date] = parsed
        if byday:
            out[code] = {"name": loc, "dates": byday}
    return out, notes


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
            # This schedule says when a classroom can be BOOKED, not when the
            # doors are unlocked. On a day the university has said classes do
            # not meet, it therefore describes nothing at all, and the map must
            # not read it as an official claim that the building is open.
            # Verified 2026-10-15: during Autumn Break the Architecture and
            # Geology libraries cut to 10am-2pm, while this schedule still
            # claimed their buildings were open into the evening.
            "classDerived": True,
        }

    # Key on whatever name the class data already uses for this code, so the two
    # files join. Ohio State's class API calls the union "Ohio Union, New" and
    # Thompson "Library, Wm Oxley Thompson"; the map shows a friendlier label
    # from BUILDINGS_OSU rather than renaming here, because renaming would break
    # the join the codes exist to guarantee.
    class_names = {}
    class_file = ROOT / "data" / "osu" / "class_activity.json"
    if class_file.exists():
        for n, v in json.loads(class_file.read_text())["buildings"].items():
            if v.get("code"):
                class_names.setdefault(v["code"], n)

    # Libraries are published by the Libraries themselves, a week at a time, so
    # they arrive as dated entries rather than a weekly pattern — the same shape
    # Illinois' library feed produces. Outside that published week the map shows
    # no data for them, which is why this has to run weekly.
    try:
        libs, lib_notes = library_hours()
    except Exception as err:
        libs, lib_notes = {}, [f"library fetch failed: {type(err).__name__}: {err}"]

    for code, info in libs.items():
        existing = next((k for k, v in out.items() if v.get("code") == code), None)
        name = existing or class_names.get(code) or info["name"]
        covered = sorted(info["dates"])
        entry = out.get(name, {})
        entry.update({
            "source": LIB_SOURCE,
            "sourceUrl": LIB_URL,
            "code": code,
            "dates": info["dates"],
            # Only the published week is known. Anything else is left unknown
            # rather than extrapolated from a single week that may contain a
            # break — this week carries Autumn Break, and the libraries' hours
            # on those days are not their normal ones.
            "unknownDuring": [[TERM[0], covered[0]], [covered[-1], TERM[1]]],
            "valid": list(TERM),
        })
        entry.setdefault("weekly", {d: [] for d in DAYS})
        out[name] = entry

    for code, info in HAND_ENTERED.items():
        name = (next((k for k, v in out.items() if v.get("code") == code), None)
                or class_names.get(code) or info["name"])
        out[name] = {
            "source": info["source"],
            "sourceUrl": info["sourceUrl"],
            "code": code,
            "valid": list(TERM),
            "weekly": info["weekly"],
            "periods": [
                {"start": a, "end": b, "weekly": info["breakWeekly"]}
                for a, b in info.get("breaks", [])
            ],
        }
    print(f"hand-entered buildings: {len(HAND_ENTERED)} "
          f"({', '.join(v['name'] for v in HAND_ENTERED.values())})")

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
    print(f"library buildings added: {len(libs)}  ({', '.join(sorted(libs)) or 'none'})")
    if lib_notes:
        print(f"library days not readable: {len(lib_notes)}")
        if args.print_skipped:
            for n in lib_notes:
                print(f"   {n}")
    if skipped:
        print(f"unreadable day-entries: {len(skipped)}")
        if args.print_skipped:
            for name, day, val in skipped:
                print(f"   {name} / {day}: {val!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
