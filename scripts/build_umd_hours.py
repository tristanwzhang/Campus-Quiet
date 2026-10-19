#!/usr/bin/env python3
"""
Build Maryland building hours into data/umd/building_hours.json, in the same
shape build_hours.py produces for Illinois and build_osu_hours.py for Columbus,
so app.js can read any of the three.

**Maryland publishes no per-building hours spreadsheet** — nothing like
Illinois' Facilities file or Ohio State's registrar classroom-pool schedule. It
DOES publish one campus-wide rule, which an earlier version of this file missed
because it was looking for a table. UMPD Building Security Services, the office
that controls the door locks ("Locking/unlocking is controlled by remote
electronic programming"), states:

    Campus academic and administrative facilities are generally open to the
    public from 7:00am to 9:00pm Monday through Friday during the academic
    year. Unless specifically requested, these facilities are closed on
    weekends and University holidays. [...] Regularly scheduled classes and
    exams [...] exterior doors to the appropriate facilities will be unlocked
    during the scheduled period.
    https://umpd.umd.edu/about-us/our-units/building-security-systems

That is applied below to the buildings that are plainly academic, with each
building's own scheduled classes added on top, because the same page says the
doors unlock for them. It is a GENERAL rule, not a per-building schedule, and
the entries say so (`generalRule`) rather than posing as one.

Everything else rides the class-timetable fallback in app.js.

The sources, each checked live on 2026-10-16 and again on 2026-10-19:

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

  * **Dining venues that are tenants.** The cafes in McKeldin, Tawes, Iribe and
    the rest publish hours, but a cafe's hours are not its building's hours.
    Only the three dining HALLS, which are buildings in their own right, are
    used. (An earlier version of this file said Dining publishes no hours at
    all. It does — they load a few seconds after the page does, from a public
    Google Sheet the page itself reads, which a first look at the page missed.)
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

DINING_PAGE = "https://dining.umd.edu/hours/open-now"
DINING_SOURCE = "UMD Dining Services published hours"
# The page's own script names the sheet and the tab, so they are read from it
# rather than trusted as constants. These are only the fallback if that fails.
DINING_SHEET_FALLBACK = ("1vdWskGO2-aJfKLSW8-3zMaj_nx4SBJHF3OvMEy4-ZNo", "479022338")
# Hall label in the sheet's first column -> the building the map uses. 251 North
# is the Denton Area Dining Hall (the printed campus directory pairs them:
# "251 NORTH/DENTON AREA DINING HALL"); Yahentamitsi is its class-data name.
DINING_HALLS = {
    "South Campus": "South Campus Dining Hall",
    "251 North": "Denton Area Dining Hall",
    "Yahentamitsi": "Yahentamitsi Dining Hall",
}

HEALTH_URL = "https://health.umd.edu/your-visit/hours-and-location"
HEALTH_SOURCE = "University Health Center published hours"
HEALTH_BUILDING = "University Health Center"

UMPD_URL = "https://umpd.umd.edu/about-us/our-units/building-security-systems"
UMPD_SOURCE = "UMD Police Building Security Services \u2014 general academic building hours"
DIRECTORY_FILE = ROOT / "data" / "umd" / "directory.json"
ROOMS_FILE = ROOT / "data" / "umd" / "rooms.json"

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
    # No classes meet in Ritchie, so it has no scheduling code; it is joined to
    # the register by number (004) through GIS_ALIASES_UMD, as Stamp is. The page
    # was once described as old, but its Fall Semester tab matches Eppley's
    # exactly and RecWell's dated /facility-alerts table lists both on the same
    # hours, so the two agree.
    "https://recwell.umd.edu/ritchie-coliseum-0":
        ("Ritchie Coliseum", None, "Ritchie Coliseum"),
}
POOL_URL = "https://recwell.umd.edu/outdoor-aquatic-center"
# The register calls it "Aquatic Center" (building 399); RecWell calls it the
# Outdoor Aquatic Center and places it "on the west end of Eppley Recreation
# Center". The directory puts both in map grid D7. The identification is an
# inference from that — there is no other standalone aquatic building — and is
# flagged as one in docs/maryland.md.
POOL_BUILDING = "Aquatic Center"
RECWELL_TERM = "Fall Semester"          # which data-title tab to read

# Stamp is not in the class data at all — no classes meet there — so it has no
# scheduling code. It is carried as a building in its own right, the way
# Illinois carries the Illini Union, and GIS_ALIASES_UMD points its name at the
# register's building number (163, per MD iMAP).
STAMP_BUILDING = "Stamp Student Union"

# Days the UNIVERSITY is shut, from its own staff holiday calendar — the
# observed column, not the earned one, because that is the day the doors are
# locked. https://uhr.umd.edu/employee-resources/holiday-calendar
#
# This is the distinction the Ohio State work turned on: a day with no classes
# is not the same as a day with locked doors, and only the second belongs here.
# Two published sources agree on the one that is easy to get wrong — HR lists
# 12 October as "Indigenous Peoples Day - Fall Break", and Stamp's own hours
# page independently prints that Monday as Closed while showing the Tuesday
# open until 6pm.
#
# Election Day is earned on 3 November 2026 but OBSERVED on 17 March 2027, so
# it is not a closure this term; Veteran's Day and President's Day are likewise
# observed in the December break rather than on the date they are named for.
CAMPUS_CLOSED = [
    "2026-09-07",   # Labor Day
    "2026-10-12",   # Indigenous Peoples Day / Fall Break
    "2026-11-26",   # Thanksgiving Day
    "2026-11-27",   # Thanksgiving Holiday
    "2026-12-25",   # Christmas Day
    "2026-12-28",   # President's Day, observed
    "2026-12-29",   # Winter Break
    "2026-12-30",   # Veteran's Day, observed
    "2026-12-31",   # Winter Break
]

# No classes, but the university is open and the doors are very likely
# unlocked. On these days the class-timetable fallback has run out of ground to
# stand on and app.js makes it say nothing rather than guess shut — the same
# treatment Ohio State's "Academic Holidays (no classes, offices open)" get.
#
# Derived by subtracting the holiday calendar above from the registrar's
# no-class days, which is two published sources rather than a judgement:
# Fall Break is 12-13 October and only the 12th is a holiday; the Thanksgiving
# recess starts Wednesday the 25th and only the 26th and 27th are holidays.
CLASSES_OUT = ["2026-10-13", "2026-11-25"]

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


# ── 4. Dining halls ───────────────────────────────────────────────────────────

def merge_ranges(ranges):
    """[[7,10.5],[10.5,16],[16,21]] -> [[7,21]]. Meals that touch are one stretch
    of open doors, which is what the map is asking about."""
    out = []
    for a, b in sorted(ranges):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def dining(skipped):
    """The three dining halls, DATED, from the sheet dining.umd.edu itself reads.

    The hours do not appear in the page's HTML: a script fetches them from a
    public Google Sheet a few seconds after load, which is why a first read of
    the page (and a plain scrape of it) shows every cell empty. The page names
    the sheet and the tab in its own code, so both are taken from there; the tab
    is then checked by its CONTENT (rows called "South Campus | Breakfast")
    rather than trusted by number.

    One column per calendar day, a year ahead, so this is dated hours like the
    libraries' — no weekly pattern to reason from and nothing to guess at breaks.
    """
    sheet, gid = DINING_SHEET_FALLBACK
    page = fetch(DINING_PAGE)
    if page:
        m = re.search(r"diningUrl\s*=\s*'https://docs\.google\.com/spreadsheets/d/([\w-]+)/gviz/tq\?gid=(\d+)'", page)
        if m:
            sheet, gid = m.group(1), m.group(2)
        else:
            skipped.append("dining page no longer names its sheet; using the last known one")
    raw = fetch(f"https://docs.google.com/spreadsheets/d/{sheet}/gviz/tq?gid={gid}&tqx=out:json")
    if not raw:
        return {}
    m = re.search(r"setResponse\((.*)\);?\s*$", raw, re.S)
    if not m:
        skipped.append("dining sheet: unrecognised response")
        return {}
    table = json.loads(m.group(1)).get("table", {})
    rows = table.get("rows", [])

    def text(c):
        return ((c or {}).get("f") or (c or {}).get("v") or "")

    if not rows:
        return {}
    header = [str(text(c)).strip() for c in rows[0]["c"]]
    isodates = {}
    for i, h in enumerate(header[1:], 1):
        mo = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", h)
        if mo:
            isodates[i] = f"{int(mo.group(3)):04d}-{int(mo.group(1)):02d}-{int(mo.group(2)):02d}"

    # meal rows per hall: {hall: [row, row, row]}
    halls = {}
    for r in rows[1:]:
        cells = r["c"]
        label = str(text(cells[0])).strip() if cells else ""
        hall = label.split("|")[0].strip()
        if hall in DINING_HALLS and "|" in label:
            halls.setdefault(hall, []).append(cells)
    if set(halls) != set(DINING_HALLS):
        skipped.append(f"dining sheet: expected halls {sorted(DINING_HALLS)}, found {sorted(halls)}")

    out = {}
    for hall, meal_rows in halls.items():
        dates = {}
        for i, iso in isodates.items():
            if iso < "2026-08-17":
                continue                     # the rest of the year behind us
            ranges, bad = [], False
            for cells in meal_rows:
                cell = str(text(cells[i]) if i < len(cells) else "").strip()
                if not cell:
                    bad = True               # a blank is not the same as Closed
                    break
                sp = span(cell)
                if sp is None:
                    bad = True               # "TBD" and friends: say nothing
                    break
                if sp:
                    ranges.append(sp)
            if bad:
                skipped.append(f"{DINING_HALLS[hall]} {iso}: blank or TBD")
                continue
            dates[iso] = merge_ranges(ranges)
        if not dates:
            continue
        keys = sorted(dates)
        out[DINING_HALLS[hall]] = {
            "source": DINING_SOURCE,
            "sourceUrl": DINING_PAGE,
            "dates": dates,
            "valid": [keys[0], keys[-1]],
        }
    return out


# ── 5. University Health Center ───────────────────────────────────────────────

# Closures the Health Center prints in its own holiday table, as dates. Labor
# Day and the Thanksgiving recess are named; the registrar's calendar gives the
# recess as Wednesday 25 to Sunday 29 November. Christmas to New Year's is
# outside this term. Fall Break is NOT in its table: HR lists 12 October as a
# university holiday, but the Health Center never says it closes, so that day
# is left unknown rather than assumed either way.
HEALTH_CLOSED = ["2026-09-07", "2026-11-25", "2026-11-26", "2026-11-27", "2026-11-28", "2026-11-29"]


def health(skipped):
    raw = fetch(HEALTH_URL)
    if not raw:
        return {}
    tables = re.findall(r"<table.*?</table>", raw, re.S)
    # The first table is FALL/SPRING for the building; the later ones are the
    # pharmacy, the lab, summer and the holiday list, none of which are the
    # building's public hours.
    first = rows_of(tables[0]) if tables else []
    if not first or "FALL" not in first[0][0].upper():
        skipped.append("Health Center: first table is not FALL/SPRING any more")
        return {}
    weekly = empty_week()
    for row in first[1:]:
        if len(row) < 2:
            continue
        group = day_group(row[0].rstrip(": "))
        # "8:00am - 5:00pm, plus limited evening services from 5:00 - 7:00pm by
        # appointment only." The evening sessions are by appointment, not
        # public hours, so only the range before the comma is read.
        cell = re.split(r",\s*plus\b", row[1], maxsplit=1)[0]
        ranges = span(cell)
        if group is None or ranges is None:
            skipped.append(f"Health Center {row[0]!r} -> {row[1][:48]!r}")
            continue
        for d in group:
            # A later row for the same weekday would overwrite an earlier one,
            # and the Monday/Tuesday/Thursday row repeats Monday-Friday.
            weekly[d] = as_ranges(ranges)
    if not any(weekly.values()):
        return {}
    return {HEALTH_BUILDING: {
        "source": HEALTH_SOURCE,
        "sourceUrl": HEALTH_URL,
        "weekly": weekly,
        "valid": ["2026-08-31", "2026-12-21"],
        "closedDates": HEALTH_CLOSED,
        "unknownDuring": [["2026-10-12", "2026-10-12"]],
    }}


# ── 6. The outdoor pool ───────────────────────────────────────────────────────

def pool(skipped):
    """Rows are DATE RANGES, not weekday groups, so it becomes `periods`."""
    raw = fetch(POOL_URL)
    if not raw:
        return {}
    panels = re.findall(r'<div data-title="([^"]*)">(.*?)(?=<div data-title="|\Z)', raw, re.S)
    panel = next((body for title, body in panels if title.strip() == RECWELL_TERM), None)
    table = re.search(r"<table.*?</table>", panel or "", re.S)
    if not table:
        skipped.append("Aquatic Center: no Fall Semester table")
        return {}
    rows = rows_of(table.group(0))
    header, periods = rows[0], []
    groups = [day_group(h) for h in header[1:]]
    for row in rows[1:]:
        m = re.fullmatch(r"([A-Za-z]+ \d{1,2})\s+to\s+([A-Za-z]+ \d{1,2})", row[0])
        start, end = (as_iso(m.group(1), 2026), as_iso(m.group(2), 2026)) if m else (None, None)
        if not (start and end):
            skipped.append(f"Aquatic Center date range {row[0]!r}")
            continue
        weekly = empty_week()
        for i, cell in enumerate(row[1:]):
            ranges = span(cell)
            if i >= len(groups) or groups[i] is None or ranges is None:
                skipped.append(f"Aquatic Center {row[0]!r} -> {cell[:30]!r}")
                continue
            for d in groups[i]:
                weekly[d] = as_ranges(ranges)
        periods.append({"start": start, "end": end, "weekly": weekly})
    if not periods:
        return {}
    return {POOL_BUILDING: {
        "source": RECWELL_SOURCE,
        "sourceUrl": POOL_URL,
        "periods": periods,
        "weekly": empty_week(),
        "valid": [periods[0]["start"], periods[-1]["end"]],
        "noExtension": True,
    }}


# ── 7. The campus-wide rule, for the academic buildings ───────────────────────

# Class buildings the directory does not list but that are plainly academic:
# the Computer Science Instructional Center opened after the directory was
# printed. Anything added here needs a reason, because the rule is "academic and
# administrative" and a wrong inclusion shows a building open to the public that
# is not.
ACADEMIC_NOT_IN_DIRECTORY = {"Computer Science Instructional Center"}

# In the directory's "University Buildings" but not academic or administrative in
# the sense the rule means, so they keep the class-timetable fallback instead.
NOT_GENERAL_ACADEMIC = {
    "Cambridge Community Center": "a housing community centre, open to residents",
    "Leonardtown Community Center": "a housing community centre, open to residents",
    "Preinkert Field House": "an athletics building",
    "Avrum Gudelsky Veterinary Center": "a clinical veterinary facility with its own hours",
}


def umpd_rule(existing, skipped):
    """Mon-Fri 7am-9pm, plus the hours classes are scheduled, for each academic
    building that has no hours of its own.

    Which buildings is decided by the university's own directory, not by name:
    its printed section for a building is "University Buildings" (academic,
    administrative, research, service), "Key Places of Interest" (libraries, the
    stadium, the health center — all of which keep their own hours) or "Campus
    Housing". Eight residence halls host classes and would otherwise have been
    shown open to the public at 7am; they are the reason this reads the
    directory at all.

    The class windows are exact, from rooms.json (a 9:30 class is 9.5, not the
    whole of hour 9), because the rule says the doors unlock for "the scheduled
    period", not for the clock hour it touches.
    """
    if not (DIRECTORY_FILE.exists() and ROOMS_FILE.exists() and CLASS_FILE.exists()):
        skipped.append("campus rule: needs data/umd/{directory,rooms,class_activity}.json")
        return {}
    directory = json.loads(DIRECTORY_FILE.read_text())["buildings"]
    rooms = json.loads(ROOMS_FILE.read_text())["buildings"]
    classes = json.loads(CLASS_FILE.read_text())["buildings"]

    out, why = {}, {"housing": [], "places": [], "unlisted": [], "excluded": [], "has own hours": []}
    for name, v in sorted(classes.items()):
        section = (directory.get(v.get("number")) or {}).get("section")
        if name in existing:
            why["has own hours"].append(name)
            continue
        if name in NOT_GENERAL_ACADEMIC:
            why["excluded"].append(f"{name} ({NOT_GENERAL_ACADEMIC[name]})")
            continue
        if section == "housing":
            why["housing"].append(name)
            continue
        if section == "places":
            why["places"].append(name)
            continue
        if section is None and name not in ACADEMIC_NOT_IN_DIRECTORY:
            why["unlisted"].append(name)
            continue

        weekly = empty_week()
        for d in DAYS:
            spans = [[a, b] for r in (rooms.get(name, {}).get("rooms") or {}).values()
                     for a, b in (r.get("busy") or {}).get(d, [])]
            base = [[7.0, 21.0]] if d in DAYS[:5] else []
            weekly[d] = merge_ranges(base + spans)
        out[name] = {
            "source": UMPD_SOURCE,
            "sourceUrl": UMPD_URL,
            "code": v.get("code"),
            "weekly": weekly,
            "valid": ["2026-08-31", "2026-12-21"],
            "followsCampusClosures": True,
            "generalRule": True,
            "weeklyNote": "7am-9pm on weekdays plus the hours classes are scheduled; "
                          "closed weekends and university holidays unless something is scheduled",
        }
    for reason, names in why.items():
        if names:
            skipped.append(f"campus rule not applied [{reason}]: {', '.join(names)}")
    return out



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print-skipped", action="store_true")
    args = ap.parse_args()

    skipped = []
    buildings = {}
    for label, got in (("libraries", libcal(skipped)),
                       ("Stamp", stamp(skipped)),
                       ("RecWell", recwell(skipped)),
                       ("dining", dining(skipped)),
                       ("health", health(skipped)),
                       ("pool", pool(skipped))):
        print(f"{label:<10} {len(got)} building(s): {', '.join(got) or '—'}")
        buildings.update(got)
    # Last, and never over a building that publishes its own: the campus rule is
    # the fallback for academic buildings, not a rival to a real schedule.
    got = umpd_rule(buildings, skipped)
    print(f"{'campus rule':<10} {len(got)} building(s)")
    buildings.update(got)

    if not buildings:
        print("no hours from any source; leaving the existing file alone", file=sys.stderr)
        return 1

    # Carry the weekly patterns across the gap between the last day of classes
    # and the end of finals, which is exactly when people most want to know.
    # The dated feeds need no help: they publish past it already.
    for entry in buildings.values():
        if ("weekly" in entry and not entry.get("noExtension") and not entry.get("generalRule")
                and not entry.get("dates") and entry.get("valid", [None, None])[1] <= TERM_RANGE[1]):
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
        "classesOutDates": CLASSES_OUT,
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
        # Buildings with no classes: each needs a GIS_ALIASES_UMD entry in
        # app.js to be placed, and a BUILDINGS_UMD entry to be known at all.
        print(f"no class data (need GIS_ALIASES_UMD + BUILDINGS_UMD entries): "
              f"{', '.join(off_join)}")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
