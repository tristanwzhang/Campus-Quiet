#!/usr/bin/env python3
"""
Build Maryland building hours into data/umd/building_hours.json, in the same
shape build_hours.py produces for Illinois and build_osu_hours.py for Columbus,
so app.js can read any of the three.

**Maryland publishes no campus-wide building hours.** There is no equivalent of
Illinois' Facilities spreadsheet or Ohio State's registrar classroom-pool
schedule — Facilities Management publishes none, and the registrar publishes
none. So this file is small on purpose: three sources covering the buildings
that genuinely publish, and everything else rides the class-timetable fallback
in app.js, which is already the agreed design for that gap.

The three, each checked live on 2026-10-16 and again on 2026-10-19:

  1. **University Libraries, via LibCal** — the best hours feed on any of the
     three campuses. Key-less, and it answers with DATED hours eight weeks
     ahead, where the Illinois and Ohio State feeds publish seven days.
         https://umd.libcal.com/api_hours_grid.php?iid=0&format=json&weeks=N
     Only McKeldin and Hornbake are buildings in their own right. The
     Architecture, Art, Performing Arts and STEM libraries are tenants inside
     other buildings, and a tenant's hours are not its building's hours — the
     same call Columbus made for its in-building libraries.

  2. **Stamp Student Union** — a weekly table that states its own validity
     ("Fall Semester 2026 Hours, August 27 through December 20") plus dated
     exception tables for Labor Day, Fall Break, Thanksgiving and Winter Break.
     That is the only published source on this campus for break-day hours.
         https://stamp.umd.edu/visit/hours_operation

  3. **RecWell**, on its per-facility pages. NOT on
     /facilities/todays-facility-hours, which renders empty and has no API
     behind it either — verified in a browser with the network log open. The
     four tables on a facility page are the four terms, and the labels are
     `data-title` attributes rather than visible text, which is why a naive
     text scrape sees four identical unlabelled tables.

What is deliberately NOT here:

  * **Dining.** It publishes no per-hall hours on the web — the dining-halls
    page gives meal windows and then says to use the mobile app, and
    /hours/open-now serves a full venue list with every hours cell empty.
  * **The Outdoor Aquatic Center**, whose table is shaped by date range rather
    than weekday and which is shut for the rest of the term anyway.
  * **Ritchie Coliseum**, which has no hours table on its page.
  * Any hours derived from the class timetable. Ohio State's registrar proxy
    earns its `classDerived` flag by being a published schedule; inventing one
    here from our own class data would be circular.

Usage:
  python3 scripts/build_umd_hours.py
  python3 scripts/build_umd_hours.py --print-skipped   # also list what was dropped
"""

import argparse
import html as htmllib
import json
import re
import sys
import time
import urllib.request
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "umd" / "building_hours.json"
CLASS_FILE = ROOT / "data" / "umd" / "class_activity.json"

UA = {"User-Agent": "Mozilla/5.0 (campusquiet.com hours build)"}
WEEKS = 10                      # LibCal served 8 happily; ask for the whole term

LIBCAL = "https://umd.libcal.com/api_hours_grid.php?iid=0&format=json&weeks=%d"
LIBCAL_SOURCE = "University of Maryland Libraries hours"
LIBCAL_URL = "https://www.lib.umd.edu/visit/hours"

STAMP_URL = "https://stamp.umd.edu/visit/hours_operation"
STAMP_SOURCE = "Adele H. Stamp Student Union published hours"

RECWELL_SOURCE = "UMD RecWell facility hours"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# LibCal location id -> the building name the map uses, which is the name
# Testudo's class data uses, because that is what the two files join on.
# Hornbake's official scheduling name is "Undergraduate Library"; everyone
# calls it Hornbake, and BUILDINGS_UMD carries the friendly label.
LIBCAL_BUILDINGS = {
    13231: ("McKeldin Library", "MCK"),
    17964: ("Undergraduate Library", "HBK"),
}

# RecWell facility page -> (building name the map uses, code, the row in the
# table that IS the building rather than something inside it).
#
# The row matters: Eppley's table lists the Natatorium, the Member Services
# Desk and Sneakers Cafe alongside the building, and those are tenants. Taking
# the first row would have given the building the swimming pool's hours.
RECWELL = {
    "https://recwell.umd.edu/eppley-recreation-center-0":
        ("Eppely Recreation Center", "ERC", "Eppley Recreation Center"),
    "https://recwell.umd.edu/reckord-armory":
        ("Armory (Reckord)", "ARM", "Reckord Armory Gym"),
}
RECWELL_TERM = "Fall Semester"          # which data-title tab to read

# Stamp is not in the class data at all — no classes meet there — so it has no
# scheduling code. It is carried as a building in its own right, the way
# Illinois carries the Illini Union, and GIS_ALIASES_UMD points its name at the
# register's building number (163, per MD iMAP).
STAMP_BUILDING = "Stamp Student Union"

# Days the university itself is shut. Both are published, not inferred: the
# registrar's calendar names Labor Day and the Thanksgiving recess, and Stamp's
# own hours page prints "Thursday, November 26 Closed" and "Friday, November 27
# Closed". The rest of the recess (Wed 25, Sat 28, Sun 29) is a class break
# with the campus open, so it is not listed here.
CAMPUS_CLOSED = ["2026-09-07", "2026-11-26", "2026-11-27"]

TERM = "2026/fall"
TERM_RANGE = ["2026-08-31", "2026-12-11"]    # first and last day of classes
FINALS_END = "2026-12-21"                    # last day of final examinations


def fetch(url, tries=4, timeout=30):
    """GET with short retries. These hosts sit behind an edge that refuses a
    connection outright now and then — all three refused once on 2026-10-16 and
    answered seconds later — so a single attempt is not a verdict."""
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(
                urllib.request.Request(url, headers=UA), timeout=timeout
            ).read().decode("utf-8", "replace")
        except Exception as err:
            if attempt == tries - 1:
                print(f"  giving up on {url}: {type(err).__name__}", file=sys.stderr)
                return None
            time.sleep(3 * (attempt + 1))
    return None


# ── time parsing ──────────────────────────────────────────────────────────────
# One parser for all three sources, because they write the same clock three
# ways: "8am", "7 a.m.", "Noon", "midnight", "1:30 a.m.".

_TIME = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?$", re.I)


def clock(text):
    """'1:30 a.m.' -> 1.5, 'noon' -> 12, 'midnight' -> 24. None if unreadable.

    Midnight is 24 rather than 0 because every use of it here is the END of a
    range that started the same day. A start-of-day midnight is handled by the
    caller, which knows which side of the range it is reading.
    """
    t = (text or "").strip().lower().replace("–", "-").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip(" .")
    if t in ("midnight", "12 midnight"):
        return 24.0
    if t in ("noon", "12 noon"):
        return 12.0
    m = _TIME.match(t + ("" if t.endswith((".", "m")) else ""))
    if not m:
        m = _TIME.match(t)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hour += 12
    return hour + int(m.group(2) or 0) / 60


def span(text):
    """'7 a.m. to 1:30 a.m.' -> [7, 25.5]. None when either end is unreadable.

    A closing time at or before the opening time is the next morning, so it
    gets 24 added: Stamp really is open until 1:30am on a Friday, and recording
    that as [7, 1.5] would make the building read as shut all evening.
    """
    t = (text or "").replace("–", "-").replace("—", "-").replace("\xa0", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if re.fullmatch(r"(?i)closed", t):
        return []
    if re.fullmatch(r"(?i)24\s*hours?", t):
        return [0.0, 24.0]
    parts = re.split(r"\s+to\s+|\s*-\s*|\s*–\s*", t, maxsplit=1)
    if len(parts) != 2:
        return None
    a, b = clock(parts[0]), clock(parts[1])
    if a is None or b is None:
        return None
    if a == 24.0:                       # a range that OPENS at midnight starts at 0
        a = 0.0
    if b <= a:
        b += 24
    return [a, b]


# ── day-group parsing ─────────────────────────────────────────────────────────
# Every source writes these differently, and RecWell writes them differently on
# each page: "Monday to Friday", "Monday through Friday", "MON though THURS"
# (their typo), "SAT and SUN", "Saturday & Sunday". Anything unrecognised is
# reported rather than guessed at — a mis-read day group silently moves a
# building's hours onto the wrong day.

_DAY_WORDS = {
    "mon": "monday", "monday": "monday", "tue": "tuesday", "tues": "tuesday",
    "tuesday": "tuesday", "wed": "wednesday", "weds": "wednesday",
    "wednesday": "wednesday", "thu": "thursday", "thur": "thursday",
    "thurs": "thursday", "thursday": "thursday", "fri": "friday",
    "friday": "friday", "sat": "saturday", "saturday": "saturday",
    "sun": "sunday", "sunday": "sunday",
}


def day_group(text):
    """'Monday through Thursday' -> the four weekday names. None if unreadable."""
    t = (text or "").lower().replace("\xa0", " ")
    t = re.sub(r"[–—]", "-", t)
    # "though" is RecWell's own typo for "through", on the Armory page.
    t = re.sub(r"\b(through|thru|though|to|-)\b", "-", t)
    t = re.sub(r"\b(and|&)\b", "+", t)
    t = re.sub(r"[^a-z+\-]+", " ", t).strip()
    words = [w for w in re.split(r"[\s]+", t) if w]
    if not words:
        return None

    # A range: two day words with a '-' between them.
    if "-" in words:
        i = words.index("-")
        a = _DAY_WORDS.get(words[i - 1]) if i > 0 else None
        b = _DAY_WORDS.get(words[i + 1]) if i + 1 < len(words) else None
        if not a or not b:
            return None
        ia, ib = DAYS.index(a), DAYS.index(b)
        return DAYS[ia:ib + 1] if ia <= ib else DAYS[ia:] + DAYS[:ib + 1]

    named = [_DAY_WORDS[w] for w in words if w in _DAY_WORDS]
    extra = [w for w in words if w not in _DAY_WORDS and w != "+"]
    if not named or extra:
        return None
    return named


def rows_of(table):
    out = []
    for tr in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = [re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", c))).strip()
                 for c in re.findall(r"<t[hd].*?</t[hd]>", tr, re.S)]
        out.append([c for c in cells if c])
    return [r for r in out if r]


def empty_week():
    return {d: [] for d in DAYS}


def as_ranges(one):
    """span() returns a single [open, close]; the file format is a LIST of
    them, because a building can shut for the afternoon and reopen. Closed is
    an empty list, which is a positive claim, not a missing one."""
    return [one] if one else []


# ── 1. the libraries ──────────────────────────────────────────────────────────

def libcal(skipped):
    raw = fetch(LIBCAL % WEEKS)
    if not raw:
        return {}
    grid = json.loads(raw)
    out = {}
    for loc in grid.get("locations", []):
        pair = LIBCAL_BUILDINGS.get(loc.get("lid"))
        if not pair:
            continue                 # a tenant library, or not a building
        name, code = pair
        dates = {}
        for week in loc.get("weeks", []):
            for _weekday, day in week.items():
                iso = day.get("date")
                times = day.get("times") or {}
                if not iso:
                    continue
                status = times.get("status")
                if status == "closed":
                    dates[iso] = []
                    continue
                if status == "24hours":
                    # A round-the-clock day carries no `hours` array at all.
                    # McKeldin runs 35 of the next 70 days this way, so reading
                    # the missing array as "unparseable" threw away half its
                    # calendar and left the main library reading "hours
                    # unknown" on the nights it is most useful.
                    dates[iso] = [[0.0, 24.0]]
                    continue
                ranges = []
                bad = False
                for h in times.get("hours") or []:
                    # The feed writes a 24-hour day as from 12am to 12am.
                    s = span(f"{h.get('from')} to {h.get('to')}")
                    if s is None:
                        bad = True
                        break
                    if s:
                        ranges.append(s)
                if bad or not ranges:
                    # Some other status with nothing readable in it — LibCal
                    # also serves a free-text day ("by appointment"), which is
                    # not an opening time and must not be turned into one.
                    skipped.append(f"{name} {iso}: status={status!r} "
                                   f"{str(times.get('rendered', ''))[:40]!r}")
                    continue
                dates[iso] = as_ranges(ranges)
        if not dates:
            continue
        days = sorted(dates)
        out[name] = {
            "source": LIBCAL_SOURCE,
            "sourceUrl": LIBCAL_URL,
            "code": code,
            "dates": dates,
            "valid": [days[0], days[-1]],
        }
    return out


# ── 2. Stamp ──────────────────────────────────────────────────────────────────

def stamp(skipped):
    raw = fetch(STAMP_URL)
    if not raw:
        return {}

    # Heading -> table, in document order. The first table is the building's
    # regular week; the ones under a named heading are dated exceptions.
    blocks = []
    heading = None
    for m in re.finditer(r"<h([2-4])[^>]*>(.*?)</h\1>|(<table.*?</table>)", raw, re.S):
        if m.group(2) is not None:
            heading = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        else:
            blocks.append((heading, m.group(3)))
    if not blocks:
        return {}

    weekly, valid, dates = empty_week(), None, {}
    first_heading, first_table = blocks[0]

    # The heading states the validity: "Fall Semester 2026 HoursAugust 27
    # through December 20". Taken from the page rather than assumed from the
    # term, because the union opens before classes start and closes after.
    rng = re.search(r"([A-Z][a-z]+ \d{1,2})\s*(?:through|to|-|–)\s*([A-Z][a-z]+ \d{1,2})",
                    first_heading or "")
    if rng:
        a, b = (as_iso(rng.group(1), 2026), as_iso(rng.group(2), 2026))
        if a and b:
            valid = [a, b]

    for row in rows_of(first_table):
        if len(row) < 2 or row[0].lower() == "day":
            continue
        group, ranges = day_group(row[0]), span(row[1])
        if not group or ranges is None:
            skipped.append(f"Stamp weekly {row[0]!r} -> {row[1]!r}")
            continue
        for d in group:
            weekly[d] = as_ranges(ranges)

    # Dated exceptions. Only tables whose rows name a real date are read, which
    # is what keeps the dozen tenant tables ("Stamp Centers", "Student
    # Involvement Suite") out: those are weekly, and they are not the building.
    for heading, table in blocks[1:]:
        for row in rows_of(table):
            if len(row) < 2:
                continue
            for iso in dates_in(row[0]):
                ranges = span(row[1])
                if ranges is None:
                    # "TBD (Based on home football start time.)" and friends.
                    # A guess here is a locked door someone walked to.
                    skipped.append(f"Stamp {heading} {row[0]!r} -> {row[1]!r}")
                    continue
                dates[iso] = as_ranges(ranges)

    if not any(weekly.values()):
        return {}
    entry = {
        "source": STAMP_SOURCE,
        "sourceUrl": STAMP_URL,
        "weekly": weekly,
        "valid": valid or TERM_RANGE,
    }
    if dates:
        entry["dates"] = dates
    else:
        # Without the exception tables the weekly pattern would claim the union
        # keeps ordinary hours through Thanksgiving, so fall back to the
        # campus-closure list rather than to the pattern.
        entry["followsCampusClosures"] = True
    return {STAMP_BUILDING: entry}


_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def as_iso(text, year):
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})", text or "")
    if not m or m.group(1).lower() not in _MONTHS:
        return None
    return f"{year:04d}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"


def dates_in(text):
    """Every date a Stamp row's first cell names.

    Handles "Monday, September 7", "Friday, December 25 - Sunday, January 3"
    and "October 10-October 11". The WEEKDAY WORD IS IGNORED: the page prints
    "Sunday, November 30" and November 30 2026 is a Monday, so trusting the
    word would shift a closure onto the wrong day. The date is the data.

    A range that runs backwards through the calendar has crossed into January,
    which is how the winter-break row is read.
    """
    t = re.sub(r"\s+", " ", (text or "").replace("–", "-").replace("—", "-"))
    found = re.findall(r"([A-Za-z]+)\s+(\d{1,2})", t)
    stamps = [(mo.lower(), int(d)) for mo, d in found if mo.lower() in _MONTHS]
    if not stamps:
        return []
    year = 2026
    parsed = []
    for mo, d in stamps:
        # December then January means the next year.
        if parsed and _MONTHS[mo] < _MONTHS[parsed[-1][0]]:
            year += 1
        parsed.append((mo, d, year))
    if len(parsed) == 1:
        mo, d, y = parsed[0]
        return [f"{y:04d}-{_MONTHS[mo]:02d}-{d:02d}"]
    # A range: walk it day by day.
    (mo1, d1, y1), (mo2, d2, y2) = parsed[0], parsed[-1]
    try:
        start = Date(y1, _MONTHS[mo1], d1)
        end = Date(y2, _MONTHS[mo2], d2)
    except ValueError:
        return []
    if end < start or (end - start).days > 40:
        return []
    out, cur = [], start
    while cur <= end:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


# ── 3. RecWell ────────────────────────────────────────────────────────────────

def recwell(skipped):
    out = {}
    for url, (name, code, row_name) in RECWELL.items():
        raw = fetch(url)
        if not raw:
            continue
        # The term tabs are `data-title` attributes, not visible text, and they
        # carry a trailing space on some pages.
        panels = re.findall(r'<div data-title="([^"]*)">(.*?)(?=<div data-title="|\Z)', raw, re.S)
        panel = next((body for title, body in panels if title.strip() == RECWELL_TERM), None)
        if panel is None:
            skipped.append(f"{name}: no {RECWELL_TERM!r} tab (saw {[t.strip() for t, _ in panels]})")
            continue
        table = re.search(r"<table.*?</table>", panel, re.S)
        if not table:
            skipped.append(f"{name}: {RECWELL_TERM} tab has no table")
            continue
        rows = rows_of(table.group(0))
        if not rows:
            continue
        header, weekly, got = rows[0], empty_week(), False
        # Column 0 of the header is the word "Facility"; the rest are day groups.
        groups = [day_group(h) for h in header[1:]]
        for i, g in enumerate(groups):
            if g is None:
                skipped.append(f"{name}: unreadable day column {header[1 + i]!r}")
        for row in rows[1:]:
            if row[0].strip().lower() != row_name.lower():
                continue                       # a tenant: the pool, the cafe, the desk
            for i, cell in enumerate(row[1:]):
                if i >= len(groups) or groups[i] is None:
                    continue
                # Cells carry free-text caveats: "3pm to midnight (limited
                # availability beginning at 6pm when Intramural Sports begin)".
                # The parenthetical is advice about what is open inside, not a
                # second range, so the hours are read from the part before it.
                ranges = span(re.sub(r"\s*\(.*?\)\s*", " ", cell).strip())
                if ranges is None:
                    skipped.append(f"{name} {header[1 + i]!r} -> {cell[:48]!r}")
                    continue
                for d in groups[i]:
                    weekly[d] = as_ranges(ranges)
                got = True
        if not got:
            skipped.append(f"{name}: no row called {row_name!r} (saw {[r[0] for r in rows[1:]]})")
            continue
        out[name] = {
            "source": RECWELL_SOURCE,
            "sourceUrl": url,
            "code": code,
            "weekly": weekly,
            "valid": TERM_RANGE,
            # A term pattern, not dated hours. RecWell publishes dated
            # exceptions only on /facility-alerts, which on 2026-10-19 still
            # showed the week of 9-13 October — it is an occasional-notice
            # page, not a feed, so it cannot carry a weekly job. Without it the
            # pattern would claim the gym keeps ordinary hours on Thanksgiving.
            "followsCampusClosures": True,
        }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-skipped", action="store_true")
    args = ap.parse_args()

    skipped = []
    buildings = {}
    for label, got in (("libraries", libcal(skipped)),
                       ("Stamp", stamp(skipped)),
                       ("RecWell", recwell(skipped))):
        print(f"{label:<10} {len(got)} building(s): {', '.join(got) or '—'}")
        buildings.update(got)

    if not buildings:
        print("no hours from any source; leaving the existing file alone", file=sys.stderr)
        return 1

    # Carry the weekly patterns across the gap between the last day of classes
    # and the end of finals, which is exactly when people most want to know.
    # The dated feeds need no help: they publish past it already.
    for entry in buildings.values():
        if "weekly" in entry and entry.get("valid", [None, None])[1] <= TERM_RANGE[1]:
            entry["extendedThrough"] = FINALS_END

    # Sanity-check the join before writing: an entry keyed on a name the class
    # data does not use would be invisible on the map, which is the failure
    # mode that would be hardest to notice.
    class_names = set()
    if CLASS_FILE.exists():
        class_names = set(json.loads(CLASS_FILE.read_text())["buildings"])
    off_join = [n for n in buildings if n not in class_names]

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "Maryland — College Park",
        "term": TERM,
        "campusClosedDates": CAMPUS_CLOSED,
        "buildings": buildings,
    }, indent=1) + "\n")

    dated = sum(1 for v in buildings.values() if v.get("dates"))
    print(f"\nwritten:    {len(buildings)} buildings ({dated} with dated hours, "
          f"{len(buildings) - dated} with a weekly pattern)")
    print(f"skipped:    {len(skipped)} unparseable entries"
          f"{' (--print-skipped to list)' if skipped and not args.print_skipped else ''}")
    if args.print_skipped:
        for s in skipped:
            print(f"   {s}")
    if off_join:
        # Expected for Stamp, which has no classes. Anything else here is a bug.
        print(f"not in the class data: {', '.join(off_join)} "
              f"(fine for Stamp — it needs a GIS_ALIASES_UMD entry; "
              f"anything else is a join failure)")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
