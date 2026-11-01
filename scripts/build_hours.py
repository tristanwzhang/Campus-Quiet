#!/usr/bin/env python3
"""
Build data/building_hours.json from official published hours only.

Sources
  1. Campus building hours spreadsheet (Office of the Vice Chancellor for
     Finance and Administration) — most academic buildings.
     https://financeadmin.illinois.edu/facility-scheduling-and-resources/daily-event-summaries/
  2. University Library hours API (what library.illinois.edu uses) — the next
     seven days for Main, Grainger and Funk ACES.
  3. University Housing dining schedule — the next seven days for the dining halls.
  4. Campus Recreation hours page — typed in below (ARC, CRCE).

Anything not covered stays "unknown" in the map. Nothing is guessed.

Usage:
  python3 scripts/build_hours.py
  python3 scripts/build_hours.py --sheet-url <newer .xlsx link>

Rerun weekly (library and dining hours only cover the next seven days) and
whenever a new building hours spreadsheet is posted. The Winter Break and Spring 2027
sheets (WINTER_URL, SPRING_URL) are read too and added as dated periods.
"""

import argparse
import html
import io
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "building_hours.json"

SHEET_URL = "https://financeadmin.illinois.edu/wp-content/uploads/2026/10/Fall-2026-Schedule-Updated-10.14.26.xlsx"
SHEET_VALID = ("2026-08-17", "2026-12-10")
# Stated at the top of the spreadsheet. The script checks the text is still there.
SHEET_CLOSED_DATES = ["2026-09-07", "2026-11-26", "2026-11-27"]
SHEET_CLOSED_TEXT = "All Facilities Closed on September 7 (Labor Day), Nov 26-27"
FALL_BREAK = ("2026-11-21", "2026-11-29")
FALL_BREAK_TEXT = "Fall Break: Nov 21-29, Building Hours Mon-Fri 7am-530pm, Sat & Sun Closed"
FALL_BREAK_DEFAULT = {"weekday": [[7, 17.5]], "saturday": [], "sunday": []}
AUG_17_23 = ("2026-08-17", "2026-08-23")

# The next two sheets, posted 2026-10-29 on the same Daily Event Summaries page. Same columns as
# the fall sheet; their exceptions are written into the building name instead ("Astronomy Building:
# Locked Dec 19 - Jan 3", "Huff Hall (All Doors) (Spring Break)"). Each header line used below is
# checked, like the fall one, so a reworded sheet warns rather than being read the old way.
WINTER_URL = "https://financeadmin.illinois.edu/wp-content/uploads/2026/10/Winter-Break-Building-Schedule-2026-27.xlsx"
WINTER = ("2026-12-18", "2027-01-17")   # the sheet runs to Jan 18, which is MLK Day: spring's sheet has it
WINTER_TEXT = ["Buildings hours from Dec 18 - 23 & Jan 4 - 17 unless exceptions noted below",
               "All buildings closed Thurs, Dec 24 - Sun, Jan 3 & Mon, Jan 18 (MLK Day) unless noted below"]
WINTER_CLOSED = [f"2026-12-{d}" for d in range(24, 32)] + [f"2027-01-0{d}" for d in range(1, 4)]
SPRING_URL = "https://financeadmin.illinois.edu/wp-content/uploads/2026/10/Spring-2027-Building-Hours.xlsx"
SPRING = ("2027-01-18", "2027-05-06")
SPRING_TEXT = ["Spring 2027 Building Hours: January 18, 2027 - May 6, 2027",
               "All buildings locked on January 18 (MLK Day) unless exceptions noted below",
               "Building Hours for Spring Break (March 13 - 21) unless noted below: Mon - Fri: 7am-530pm, Sat & Sun: Closed"]
SPRING_CLOSED = ["2027-01-18"]
SPRING_BREAK = ("2027-03-13", "2027-03-21")
SPRING_BREAK_DEFAULT = {**{d: [[7, 17.5]] for d in ("monday", "tuesday", "wednesday", "thursday", "friday")},
                        "saturday": [], "sunday": []}

LIBRARY_API = "https://libdirectory.library.illinois.edu/Api/UnitsInGateway"
OVERPASS_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
DINING_URL = "https://web.housing.illinois.edu/diningmenus"

# Semester window used for weekly patterns that come from a 7-day feed.
SEMESTER = ("2026-08-24", "2026-12-09")

# Spreadsheet building name (text before any "(") -> exact map building name.
SHEET_NAMES = {
    "Agricultural Engineering Sciences Building": "Agricultural Engineering Sciences",
    "Altgeld Hall": "Altgeld Hall",
    "Animal Sciences Lab": "Animal Sciences Laboratory",
    "Architecture Building": "Architecture Building",
    "Armory": "Armory",
    "Art & Design": "Art and Design Building",
    "Astronomy Building": "Astronomy Building",
    "Bevier Hall": "Bevier Hall",
    "Burrill Hall": "Burrill Hall",
    "Business Instructional Facility": "Business Instructional Facility",
    "Campus Instructional Facility": "Campus Instructional Facility",
    "Ceramics Building": "Ceramics Building",
    "Chemistry Annex": "Chemistry Annex",
    "Christopher Hall": "Doris Kelley Christopher Hall",
    "Civil and Environmental Engineering Building": "Civil and Environmental Engineering Building",
    "Coordinated Science Lab": "Coordinated Science Laboratory",
    "Davenport Hall": "Davenport Hall",
    "David Kinley Hall": "David Kinley Hall",
    "Digital Computer Lab": "Digital Computer Laboratory",
    "Education Building": "Education Building",
    "Electrical & Computer Engineering Building": "Electrical and Computer Engineering Building",
    "Engineering Hall": "Engineering Hall",
    "English Building": "English Building",
    "Everitt Lab": "Everitt Laboratory",
    "Flagg Hall": "Flagg Hall",
    "Freer Hall": "Louise Freer Hall",
    "Gregory Hall": "Gregory Hall",
    "Harding Band Building": "Harding Band Building",
    "Henry Administrative Building": "Henry Administration Building",
    "Huff Hall": "Huff Hall",
    "Illini Union": "Illini Union",
    "Illini Union Bookstore": "Illini Union Bookstore",
    "Information Sciences Building": "Graduate School of Library and Information Science",
    "Krannert Center Performing Arts": "Krannert Center for the Performing Arts",
    "Labor & Employment Relations": "School of Labor & Employment Relations",
    "Law Building": "University of Illinois College of Law",
    "Lincoln Hall": "Lincoln Hall",
    "Literatures, Cultures and Linguistics Building": "Literatures, Cultures & Linguistics Building",
    "Loomis Lab": "Loomis Laboratory of Physics",
    "Material Science and Engineering Building": "Materials Science & Engineering Building",
    "Mechanical Engineering Laboratory": "Mechanical Engineering Lab",
    "Medical Science Building": "Medical Sciences Building",
    "Morrill Hall": "Morrill Hall",
    "Mumford Hall": "Mumford Hall",
    "Music Building": "Music Building",
    "National Soybean Research Center": "National Soybean Research Center",
    "Natural History Building": "Natural History Building",
    "Newmark Civil Engineering Building": "Newmark Civil Engineering Laboratory",
    "Noyes Laboratory of Chemistry": "Noyes Laboratory",
    "Psychology Building": "Psychology Building",
    "Roger Adams Lab": "Roger Adams Laboratory",
    "Sidney LU Mechanical Engineering Building": "Sidney Lu Mechanical Engineering Building",
    "Siebel Center for Computer Science": "Siebel Center for Computer Science",
    "Siebel Center for Design": "Siebel Center for Design",
    "Smith Memorial Hall": "Smith Memorial Hall",
    "Speech & Hearing Science Building": "Speech and Hearing Science Building",
    "Stock Pavilion": "Stock Pavilion",
    "Talbot Laboratory": "Talbot Laboratory",
    "Temple Buell Hall": "Temple Hoyne Buell Hall",
    "Transportation Building": "Transportation Building",
    "Turner Hall": "Turner Hall",
    "Veterinarian Medical Basic Sciences Building": "Veterinary Medicine Basic Sciences Building",
    "Wohlers Hall": "Wohlers Hall",
    "Wymer Hall": "Steven S. Wymer Hall",
}

# University Library unit id -> map building (the library is the whole building).
LIBRARY_UNITS = {
    80: "Main Library",
    1: "Grainger Engineering Library",
    9: "Funk Library",
}

# Housing dining option id -> map name.
DINING_OPTIONS = {
    "1": "Ikenberry Dining Hall",
    "3": "ISR Dining Center",
    "5": "Lincoln/Allen Dining Hall",   # Housing's "Lincoln Avenue Dining Hall (LAR Dining Hall)"
    "2": "PAR Dining Hall",
    "6": "Corner Café",                 # retail, inside Florida Avenue Residence Halls (FAR)
}

# Museum hours from https://www.spurlock.illinois.edu/visit/ (current term table).
SPURLOCK = {
    "Spurlock Museum": {
        "source": "Spurlock Museum hours",
        "sourceUrl": "https://www.spurlock.illinois.edu/visit/index.html",
        "weekly": {
            "monday": [], "tuesday": [[12, 17]], "wednesday": [[9, 17]],
            "thursday": [[9, 17]], "friday": [[9, 17]],
            "saturday": [[10, 16]], "sunday": [[12, 16]],
        },
    },
}

# Typed in from https://campusrec.illinois.edu/hours (Aug 24 – Dec 17, 2026).
CAMPUS_REC = {
    "Activities and Recreation Center": {
        "weekly": {"monday": [[6, 23]], "tuesday": [[6, 23]], "wednesday": [[6, 23]],
                   "thursday": [[6, 23]], "friday": [[6, 22]],
                   "saturday": [[9, 22]], "sunday": [[9, 22]]},
    },
    "Campus Recreation Center East": {
        "weekly": {"monday": [[7, 23]], "tuesday": [[7, 23]], "wednesday": [[7, 23]],
                   "thursday": [[7, 23]], "friday": [[7, 21]],
                   "saturday": [[11, 18]], "sunday": [[11, 18]]},
    },
}
CAMPUS_REC_VALID = ("2026-08-24", "2026-12-17")

# Hours from the building's Google Maps listing. These outrank everything else:
# Google reflects when a place is actually open to people, while the campus
# spreadsheet only says when Facilities unlocks the doors.
# Until the SerpApi key is in place these are read off Google Maps by hand;
# scripts/fetch_google_hours.py will fill this automatically.
GOOGLE_HOURS = {
    "Illini Union Bookstore": {
        "monday": [[8, 18]], "tuesday": [[8, 18]], "wednesday": [[8, 18]],
        "thursday": [[8, 18]], "friday": [[8, 18]],
        "saturday": [[11, 16]], "sunday": [[11, 16]],
    },
    # Beckman is the fourth most-opened building on the map and had no hours at
    # all: it isn't in the Facilities spreadsheet and publishes none itself.
    "Beckman Institute": {
        "monday": [[8, 17]], "tuesday": [[8, 17]], "wednesday": [[8, 17]],
        "thursday": [[8, 17]], "friday": [[8, 17]],
        "saturday": [], "sunday": [],
    },
    # The spreadsheet row for the Ice Arena just points at a link, so it had no
    # hours either. These windows are short enough that they look like the
    # public skate sessions rather than when the doors are open — which is the
    # more useful thing to know about an ice rink anyway.
    "Ice Arena": {
        "monday": [[11, 13]], "tuesday": [[11, 13]], "wednesday": [[11, 13]],
        "thursday": [[11, 13]], "friday": [[11, 13]],
        "saturday": [[13.5, 16]], "sunday": [[13.5, 16]],
    },
}

# Hours confirmed by the site owner (no published source). Regular semester
# days only; holidays, Fall Break and after classes end stay unknown.
OWNER_CONFIRMED = {
    "Student Dining and Residential Programs (SDRP)": {
        "weekly": {d: [[7, 24]] for d in ["monday", "tuesday", "wednesday", "thursday",
                                          "friday", "saturday", "sunday"]},
    },
}

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
WEEKDAYS = DAYS[:5]
DAY_TOKENS = {"m": ["monday"], "t": ["tuesday"], "w": ["wednesday"], "th": ["thursday"],
              "f": ["friday"], "sa": ["saturday"], "su": ["sunday"]}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (uiuc-study-space)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


# ─── Spreadsheet ──────────────────────────────────────────────────────────────

def read_xlsx_rows(data):
    z = zipfile.ZipFile(io.BytesIO(data))
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    tag = "{%s}" % ns["m"]
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter(tag + "t")))
    rows = []
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    for row in sheet.iter(tag + "row"):
        cells = {}
        for c in row.findall("m:c", ns):
            col = re.sub(r"\d+", "", c.get("r"))
            v = c.find("m:v", ns)
            text = "" if v is None else (v.text or "")
            if c.get("t") == "s" and text:
                text = shared[int(text)]
            elif c.get("t") == "inlineStr":
                text = "".join(x.text or "" for x in c.iter(tag + "t"))
            cells[col] = text.strip()
        rows.append(cells)
    return rows


def parse_clock(token, is_close=False):
    """'730am' -> 7.5, '12am' as a closing time -> 24."""
    m = re.fullmatch(r"(\d{1,2})(\d{2})?(am|pm)", token)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3) == "pm":
        hour += 12
    value = hour + minute / 60
    if is_close and value == 0:
        value = 24
    return value


def parse_days(text):
    days = []
    for token in re.split(r"[&/,\s]+", text.strip().lower()):
        if not token:
            continue
        if token not in DAY_TOKENS:
            return None
        days += DAY_TOKENS[token]
    return days


def parse_hours(text, applies_to):
    """
    Turn a spreadsheet cell into {day: [[open, close], ...]} for the given days.
    Returns None when the cell can't be read with certainty.
    """
    raw = re.sub(r"\s+", " ", text.strip().lower())
    if raw in ("locked", "closed"):
        return {d: [] for d in applies_to}
    if not raw or not re.match(r"^\d", raw):
        return None   # "Department", "Info Link", "Open for Classes ...", blanks

    main, _, extra = raw.partition("(")
    main = main.replace(" ", "")
    ranges = []
    for part in main.split("/"):
        m = re.fullmatch(r"(\d{1,4}(?:am|pm))-(\d{1,4}(?:am|pm))", part)
        if not m:
            return None
        start, end = parse_clock(m.group(1)), parse_clock(m.group(2), is_close=True)
        if start is None or end is None or end <= start:
            return None
        ranges.append([start, end])

    result = {d: [list(r) for r in ranges] for d in applies_to}
    if not extra:
        return result

    # Modifiers like "(5pm F)", "(Th 10pm; 7pm F)", "(7pm T&Th)": a different
    # closing time on some days. Anything else is too ambiguous to trust.
    if len(ranges) != 1:
        return None
    for segment in extra.rstrip(")").split(";"):
        segment = segment.strip()
        m = re.fullmatch(r"(\d{1,4}(?:am|pm))\s+([a-z&/ ]+)|([a-z&/ ]+?)\s+(\d{1,4}(?:am|pm))", segment)
        if not m:
            return None
        clock = m.group(1) or m.group(4)
        days = parse_days(m.group(2) or m.group(3))
        close = parse_clock(clock, is_close=True)
        if not days or close is None or close <= ranges[0][0]:
            return None
        for d in days:
            if d in result:
                result[d] = [[ranges[0][0], close]]
    return result


WEEKDAY_LETTERS = ["m", "t", "w", "th", "f"]


def expand_weekdays(token):
    """'M-Th' / 'MWF' / 'T/Th' / 'F' -> weekday names, or None."""
    days = []
    for part in token.lower().replace(" ", "").split("/"):
        m = re.fullmatch(r"(th|m|t|w|f)-(th|m|t|w|f)", part)
        if m:
            a, b = WEEKDAY_LETTERS.index(m.group(1)), WEEKDAY_LETTERS.index(m.group(2))
            if b < a:
                return None
            days += WEEKDAYS[a:b + 1]
            continue
        letters = re.findall(r"th|m|t|w|f", part)
        if not letters or "".join(letters) != part:
            return None
        days += [WEEKDAYS[WEEKDAY_LETTERS.index(x)] for x in letters]
    return days


def parse_weekday_segments(text):
    """
    The spring sheet's weekday cell: 'M-Th: 7am-10pm; F: 5pm' -- the first segment gives opening
    and closing, each later one only a closing time for its days ("F: 5pm" = Friday 7am-5pm).
    'MWF: 8am-530pm; T/Th: 7pm', 'M-W: 730am-8pm; Th: 10pm; F: 7pm'. Every weekday must be
    covered exactly once, or the cell is unreadable.
    """
    segments = [x.strip() for x in re.sub(r"\s+", " ", text.strip().lower()).split(";")]
    m = re.fullmatch(r"([a-z/\-]+): ?(\d{1,4}(?:am|pm)) ?- ?(\d{1,4}(?:am|pm))", segments[0])
    if not m:
        return None
    days, start = expand_weekdays(m.group(1)), parse_clock(m.group(2))
    end = parse_clock(m.group(3), is_close=True)
    if not days or start is None or end is None or end <= start:
        return None
    out = {d: [[start, end]] for d in days}
    for seg in segments[1:]:
        m = re.fullmatch(r"([a-z/\-]+): ?(\d{1,4}(?:am|pm))", seg)
        more = m and expand_weekdays(m.group(1))
        close = m and parse_clock(m.group(2), is_close=True)
        if not more or close is None or close <= start or any(d in out for d in more):
            return None
        out.update({d: [[start, close]] for d in more})
    return out if sorted(out) == sorted(WEEKDAYS) else None


def row_hours(cells):
    """Weekly hours for one spreadsheet row, or None if any cell is unreadable."""
    weekly = {}
    for column, days in (("E", WEEKDAYS), ("F", ["saturday"]), ("G", ["sunday"])):
        cell = cells.get(column, "")
        if column == "E" and re.match(r"^\s*[MTWFmtwf][A-Za-z/\-]*\s*:", cell):
            parsed = parse_weekday_segments(cell)
        elif cell.strip() == "-":
            parsed = {d: None for d in days}   # "not applicable" (a one-day row on a Monday): unknown
        else:
            parsed = parse_hours(cell, days)
        if parsed is None:
            return None
        weekly.update(parsed)
    return weekly


def union_weekly(a, b):
    """Several door rows for one building: open if any listed door is open."""
    out = {}
    for d in DAYS:
        ranges = sorted((a.get(d) or []) + (b.get(d) or []))
        merged = []
        for r in ranges:
            if merged and r[0] <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], r[1])
            else:
                merged.append(list(r))
        out[d] = merged
    return out


def weekly_to_period(weekly):
    return {d: weekly[d] for d in DAYS}


def build_from_sheet(url):
    rows = read_xlsx_rows(get(url))
    header = " ".join(r.get("A", "") for r in rows[:5])
    warnings = []
    if SHEET_CLOSED_TEXT.lower() not in re.sub(r"\s+", " ", header).lower():
        warnings.append("Closure note at the top of the spreadsheet changed — check SHEET_CLOSED_DATES.")
    if FALL_BREAK_TEXT.lower() not in re.sub(r"\s+", " ", header).lower():
        warnings.append("Fall Break note at the top of the spreadsheet changed — check FALL_BREAK_DEFAULT.")

    buildings = {}
    unreadable = []
    for cells in rows[5:]:
        name = cells.get("C", "")
        if not name:
            continue
        kind = "regular"
        if name.lower().startswith("fall break hours - "):
            kind, name = "fallbreak", name[len("fall break hours - "):]
        elif name.lower().startswith("aug 17-23 - "):
            kind, name = "aug17", name[len("aug 17-23 - "):]

        base = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
        map_name = SHEET_NAMES.get(base)
        if not map_name:
            continue

        weekly = row_hours(cells)
        if weekly is None:
            unreadable.append(f"{name}: {cells.get('E','')} | {cells.get('F','')} | {cells.get('G','')}")
            continue

        entry = buildings.setdefault(map_name, {
            "source": "Campus building hours spreadsheet",
            "sourceUrl": url,
            "valid": list(SHEET_VALID),
            "followsCampusClosures": True,
            "periods": [],
        })
        if kind == "regular":
            # Lock code E (electronic) or B (electronic & key) means the doors
            # have a card reader, so students with access can get in when the
            # public doors are locked.
            if cells.get("B", "").strip().upper() in ("E", "B"):
                entry["cardAccess"] = True
            entry["weekly"] = union_weekly(entry["weekly"], weekly) if "weekly" in entry else weekly
            if "open labor day" in name.lower():
                entry["openDates"] = ["2026-09-07"]
        elif kind == "aug17":
            entry["periods"].append({"start": AUG_17_23[0], "end": AUG_17_23[1], "weekly": weekly})
        elif kind == "fallbreak":
            period = {"start": FALL_BREAK[0], "end": FALL_BREAK[1], "weekly": weekly}
            # e.g. Illini Union "(Nov 25 at 5pm- 11/29)": also closes early on Nov 25
            m = re.search(r"nov (\d+) at (\d{1,4}(?:am|pm))", name.lower())
            if m:
                day = f"2026-11-{int(m.group(1)):02d}"
                period["start"] = day
                close = parse_clock(m.group(2), is_close=True)
                weekday = DAYS[date.fromisoformat(day).weekday()]
                entry.setdefault("dates", {})[day] = None   # filled once weekly is known
                entry.setdefault("_earlyClose", []).append((day, weekday, close))
                period["start"] = f"2026-11-{int(m.group(1)) + 1:02d}"
            entry["periods"].append(period)

    for name, entry in buildings.items():
        if "weekly" not in entry:
            unreadable.append(f"{name}: only special-period rows could be read")
            entry["unknown"] = True
            continue
        for day, weekday, close in entry.pop("_earlyClose", []):
            ranges = entry["weekly"][weekday]
            entry["dates"][day] = [[r[0], min(r[1], close)] for r in ranges if r[0] < close]
        if not any(p["start"] <= FALL_BREAK[0] <= p["end"] or p["start"] <= FALL_BREAK[1] <= p["end"]
                   for p in entry["periods"]):
            entry["periods"].append({
                "start": FALL_BREAK[0], "end": FALL_BREAK[1],
                "weekly": {**{d: FALL_BREAK_DEFAULT["weekday"] for d in WEEKDAYS},
                           "saturday": FALL_BREAK_DEFAULT["saturday"],
                           "sunday": FALL_BREAK_DEFAULT["sunday"]},
            })

    buildings = {k: v for k, v in buildings.items() if not v.get("unknown")}
    return buildings, unreadable, warnings


MONTHS = {"dec": (2026, 12), "jan": (2027, 1)}   # the winter sheet's two months


def winter_dates(qual):
    """'Locked Dec 19 - Jan 3' / 'Jan 4 - 17' / 'Jan 18' -> (start, end) ISO, or None if anything else."""
    q = re.sub(r"^(locked|open)\s+", "", qual.strip().lower())
    m = re.fullmatch(r"(dec|jan) (\d{1,2})(?:\s*-\s*(?:(dec|jan) )?(\d{1,2}))?", q)
    if not m:
        return None
    y1, m1 = MONTHS[m.group(1)]
    start = date(y1, m1, int(m.group(2)))
    if not m.group(4):
        return start.isoformat(), start.isoformat()
    y2, m2 = MONTHS[m.group(3) or m.group(1)]
    return start.isoformat(), date(y2, m2, int(m.group(4))).isoformat()


def read_term_sheet(url, texts, warnings):
    """Rows of a winter/spring sheet, as (map name, kind, dates or None, weekly or None, raw)."""
    rows = read_xlsx_rows(get(url))
    header = re.sub(r"\s+", " ", " ".join(r.get("A", "") for r in rows[:5])).lower()
    for text in texts:
        if text.lower() not in header:
            warnings.append(f"Header of {url.rsplit('/', 1)[1]} changed (no longer says \"{text}\") -- check it.")
    out = []
    for cells in rows[5:]:
        name = re.sub(r"\s+", " ", cells.get("C", "")).strip()
        if not name:
            continue
        head, _, qual = name.partition(":")
        base = re.split(r"\s*\(", head, maxsplit=1)[0].strip()
        map_name = SHEET_NAMES.get(base)
        if not map_name:
            continue
        lower = name.lower()
        weekly = row_hours(cells)
        raw = f"{name}: {cells.get('E','')} | {cells.get('F','')} | {cells.get('G','')}"
        if qual.strip():
            span = winter_dates(qual)
            out.append((map_name, "dated" if span else "unreadable", span, weekly, raw))
        elif "spring break" in lower:
            out.append((map_name, "springbreak", None, weekly, raw))
        elif "(january 18)" in lower:
            out.append((map_name, "dated", ("2027-01-18", "2027-01-18"), weekly, raw))
        elif re.search(r"\b(dec|jan|january|march|mar)\b", lower):
            out.append((map_name, "unreadable", None, weekly, raw))   # dates in a form not read above
        else:
            out.append((map_name, "regular", None, weekly, raw))
    return out


def add_later_terms(buildings, unreadable, warnings):
    """
    Winter break and spring 2027, folded into each building's entry as dated periods, so the
    fall `valid` window and the finals carry-over are untouched. A row that can't be read leaves
    its span UNKNOWN rather than falling back to the term's default.
    """
    unknown_week = {d: None for d in DAYS}
    for url, (start, end), texts in ((WINTER_URL, WINTER, WINTER_TEXT), (SPRING_URL, SPRING, SPRING_TEXT)):
        try:
            rows = read_term_sheet(url, texts, warnings)
        except Exception as e:
            warnings.append(f"{url.rsplit('/', 1)[1]} not read: {e}")
            continue
        regular, special, breaks = {}, defaultdict(list), {}
        for map_name, kind, span, weekly, raw in rows:
            if weekly is None or kind == "unreadable":
                unreadable.append(raw)
                weekly = None
            if kind == "regular":
                if weekly is None:
                    regular[map_name] = None          # one unreadable door: the whole term is unknown
                elif regular.get(map_name, {}) is not None:
                    prev = regular.get(map_name)
                    regular[map_name] = union_weekly(prev, weekly) if prev else weekly
            elif kind == "springbreak":
                if weekly is None:
                    breaks[map_name] = None
                elif breaks.get(map_name, {}) is not None:
                    prev = breaks.get(map_name)
                    breaks[map_name] = union_weekly(prev, weekly) if prev else weekly
            elif kind == "dated" and span:
                special[map_name].append({"start": span[0], "end": span[1], "weekly": weekly or unknown_week})
        for map_name in set(regular) | set(special) | set(breaks):
            entry = buildings.get(map_name)
            if entry is None:
                entry = buildings[map_name] = {
                    "source": "Campus building hours spreadsheet", "sourceUrl": url,
                    "valid": [start, start], "followsCampusClosures": True, "periods": []}
            entry.setdefault("periods", [])
            for p in special.get(map_name, []):
                if p["start"] == p["end"]:   # one day (MLK Day exceptions): beats the campus closure
                    ranges = p["weekly"][DAYS[date.fromisoformat(p["start"]).weekday()]]
                    entry.setdefault("dates", {})[p["start"]] = ranges
                else:
                    entry["periods"].append(p)
            if url == SPRING_URL:
                week = breaks.get(map_name, SPRING_BREAK_DEFAULT)
                entry["periods"].append({"start": SPRING_BREAK[0], "end": SPRING_BREAK[1],
                                         "weekly": week or unknown_week})
            week = regular.get(map_name)
            entry["periods"].append({"start": start, "end": end, "weekly": week or unknown_week})
            entry["laterSources"] = sorted(set(entry.get("laterSources", [])) | {url})
        print(f"{url.rsplit('/', 1)[1]}: {len(set(regular) | set(special) | set(breaks))} map buildings")

    # The winter sheet's Vet Med rows put their dates in a form read_term_sheet does not take
    # ("(W Orange door)(Dec 24 & 26; Locked Dec 25 & Jan 1) 8am-12pm", "(Dec 29, 30, 31) 8am-7pm").
    # Typed from those rows, because otherwise the campus closure would call it locked on days
    # the sheet says the west door opens.
    vet = buildings.get("Veterinary Medicine Basic Sciences Building")
    if vet is not None:
        vet.setdefault("dates", {}).update({
            "2026-12-24": [[8, 12]], "2026-12-25": [], "2026-12-26": [[8, 12]],
            "2026-12-29": [[8, 19]], "2026-12-30": [[8, 19]], "2026-12-31": [[8, 19]], "2027-01-01": []})


# ─── Libraries ────────────────────────────────────────────────────────────────

def hours_from_times(start, end, day):
    """ISO start/end (end may be the next day) -> [open, close] in hours of `day`."""
    s = datetime.fromisoformat(start)
    e = datetime.fromisoformat(end)
    base = datetime.fromisoformat(day)
    return [round((s - base).total_seconds() / 3600, 2), round((e - base).total_seconds() / 3600, 2)]


def build_libraries():
    units = json.loads(get(LIBRARY_API))
    out = {}
    for unit in units:
        name = LIBRARY_UNITS.get(unit.get("unit_id"))
        if not name:
            continue
        dates = {}
        for day in (unit.get("calendar") or {}).get("nextSevenDays") or []:
            iso = datetime.strptime(day["date"], "%m/%d/%Y").date().isoformat()
            ranges = []
            for h in day.get("hours") or []:
                label = (h.get("label") or "").lower()
                if "closed" in label:
                    continue
                if "24 hours" in label:
                    ranges.append([0, 24])
                elif h.get("startTime") and h.get("endTime"):
                    ranges.append(hours_from_times(h["startTime"], h["endTime"], iso))
                else:
                    ranges = None   # "To Be Announced" etc.
                    break
            if ranges is not None:
                dates[iso] = ranges
        out[name] = with_weekly_from_dates({
            "source": "University Library hours",
            "sourceUrl": "https://www.library.illinois.edu/library-hours/",
            "dates": dates,
        })
    return out


def with_weekly_from_dates(entry):
    """A seven-day feed also gives the usual week, used for other semester days."""
    weekly = {}
    for iso, ranges in entry["dates"].items():
        weekly[DAYS[date.fromisoformat(iso).weekday()]] = ranges
    if len(weekly) == 7:
        entry["weekly"] = weekly
        entry["valid"] = list(SEMESTER)
        entry["weeklyNote"] = "usual week, taken from the published seven-day hours"
        entry["unknownDuring"] = [list(FALL_BREAK)] + [[d, d] for d in SHEET_CLOSED_DATES]
    return entry


# ─── Dining ───────────────────────────────────────────────────────────────────

def build_dining():
    page = get(DINING_URL).decode("utf-8", "ignore")
    table = page[page.find('<table id="sTable">'):]
    table = table[:table.find("</table>")]
    cells = r"\s*".join([r"<td>([^<]*)</td>"] * 8)
    rows = re.findall(r"<tr>\s*" + cells + r"\s*</tr>", table)
    by_place = defaultdict(lambda: defaultdict(list))
    for option_id, day, _weekday, _period, start24, end24, *_ in rows:
        name = DINING_OPTIONS.get(option_id.strip())
        if not name:
            continue
        to_hours = lambda t: int(t.split(":")[0]) + int(t.split(":")[1]) / 60
        start, end = to_hours(start24), to_hours(end24)
        if end <= start:
            end += 24
        by_place[name][day.strip()].append([start, end])

    out = {}
    for name, dates in by_place.items():
        merged = {}
        for day, ranges in dates.items():
            ranges.sort()
            joined = []
            for r in ranges:   # lunch + light lunch back to back -> one range
                if joined and r[0] <= joined[-1][1]:
                    joined[-1][1] = max(joined[-1][1], r[1])
                else:
                    joined.append(list(r))
            merged[day] = [[round(a, 2), round(b, 2)] for a, b in joined]
        out[name] = with_weekly_from_dates({
            "source": "University Housing dining schedule",
            "sourceUrl": DINING_URL,
            "dates": merged,
        })
    return out


# ─── OpenStreetMap opening hours ──────────────────────────────────────────────
# Public hours as mapped by the community. Better than the door-unlock
# spreadsheet for places like the bookstore that are open to everyone, but
# behind official feeds (it can be out of date). Anything we can't parse with
# certainty is skipped rather than guessed.

OSM_DAYS = {"mo": "monday", "tu": "tuesday", "we": "wednesday", "th": "thursday",
            "fr": "friday", "sa": "saturday", "su": "sunday"}
OSM_ORDER = list(OSM_DAYS)


def parse_opening_hours(text):
    """'Mo-Fr 07:00-22:00; Sa,Su 08:00-22:00' -> {day: [[open, close], …]}, or None."""
    text = (text or "").strip().lower()
    if not text or text == "closed":
        return None
    if text == "24/7":
        return {d: [[0, 24]] for d in DAYS}

    week = {d: [] for d in DAYS}
    for rule in text.split(";"):
        rule = rule.strip()
        if not rule:
            continue
        m = re.fullmatch(r"(?:([a-z,\- ]+?)\s+)?((?:\d{1,2}:\d{2}-\d{1,2}:\d{2})(?:\s*,\s*\d{1,2}:\d{2}-\d{1,2}:\d{2})*)", rule)
        if not m:
            return None
        day_part, time_part = m.group(1), m.group(2)

        days = []
        for chunk in (day_part or "mo-su").split(","):
            chunk = chunk.strip()
            if "-" in chunk:
                a, b = [c.strip()[:2] for c in chunk.split("-", 1)]
                if a not in OSM_DAYS or b not in OSM_DAYS:
                    return None
                i, j = OSM_ORDER.index(a), OSM_ORDER.index(b)
                span = OSM_ORDER[i:j + 1] if i <= j else OSM_ORDER[i:] + OSM_ORDER[:j + 1]
                days += [OSM_DAYS[d] for d in span]
            else:
                if chunk[:2] not in OSM_DAYS:
                    return None
                days.append(OSM_DAYS[chunk[:2]])

        ranges = []
        for span in time_part.split(","):
            start, end = span.strip().split("-")
            to_hours = lambda t: int(t.split(":")[0]) + int(t.split(":")[1]) / 60
            open_h, close_h = to_hours(start), to_hours(end)
            if close_h <= open_h:
                close_h += 24          # runs past midnight
            ranges.append([round(open_h, 2), round(close_h, 2)])
        for d in days:
            week[d] += ranges
    return week if any(week.values()) else None


def build_osm_hours(wanted):
    """Public opening hours from OpenStreetMap, for the buildings we know."""
    query = ('[out:json][timeout:60];'
             'way["building"]["opening_hours"]["name"](40.06,-88.33,40.16,-88.16);'
             'out tags center;')
    last_error = None
    for mirror in OVERPASS_MIRRORS:
        try:
            body = urllib.parse.urlencode({"data": query}).encode()
            req = urllib.request.Request(mirror, data=body, headers={"User-Agent": "campusquiet/0.1"})
            with urllib.request.urlopen(req, timeout=120) as resp:
                elements = json.load(resp)["elements"]
            break
        except Exception as e:
            last_error = e
    else:
        raise RuntimeError(f"Overpass unavailable: {last_error}")

    out, skipped = {}, []
    for element in elements:
        tags = element.get("tags", {})
        name = tags.get("name")
        if name not in wanted:
            continue
        week = parse_opening_hours(tags.get("opening_hours"))
        if not week:
            skipped.append(f"{name}: {tags.get('opening_hours')!r}")
            continue
        out[name] = {
            "source": "OpenStreetMap opening hours",
            "sourceUrl": "https://www.openstreetmap.org/",
            "valid": list(SEMESTER),
            "weekly": week,
        }
    return out, skipped


# ─── Main ─────────────────────────────────────────────────────────────────────


# The published schedules stop at the last day of classes; the term runs on
# through finals, which is exactly when people most want to know where is open.
# Nobody publishes finals-week building hours at either campus, so the weekly
# pattern is carried across that gap and app.js drops the "official" label on
# it -- an assumption, shown as one, instead of a week of "closed".
#
# Only entries with a real weekly pattern are extended. The library and rec
# feeds publish a rolling week of dated hours and carry an EMPTY weekly, so
# extending those would assert "closed" rather than assume the usual week;
# their own dated hours answer for finals once the weekly refresh picks them up.
FINALS_THROUGH = "2026-12-17"


def extend_through_finals(out, through=FINALS_THROUGH):
    """Mark entries whose weekly pattern should hold past its published end."""
    extended = []
    for name, entry in out.items():
        weekly = entry.get("weekly") or {}
        if not any(weekly.values()):
            continue
        valid = entry.get("valid")
        if valid and valid[1] < through:
            entry["extendedThrough"] = through
            extended.append(name)
    return extended


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet-url", default=SHEET_URL)
    args = parser.parse_args()

    buildings, unreadable, warnings = build_from_sheet(args.sheet_url)
    print(f"Spreadsheet: {len(buildings)} map buildings")
    add_later_terms(buildings, unreadable, warnings)

    for label, builder in (("Libraries", build_libraries), ("Dining", build_dining)):
        try:
            found = builder()
            buildings.update(found)
            print(f"{label}: {', '.join(found) or 'none'}")
        except Exception as e:   # keep the rest if one source is down
            warnings.append(f"{label} hours not updated: {e}")

    for name, entry in SPURLOCK.items():
        buildings[name] = {
            **entry,
            "valid": list(SEMESTER),
            "followsCampusClosures": True,   # closed on University holidays
            "unknownDuring": [list(FALL_BREAK)],
        }
    print(f"Spurlock: {', '.join(SPURLOCK)}")

    for name, entry in CAMPUS_REC.items():
        buildings[name] = {
            "source": "Campus Recreation hours",
            "sourceUrl": "https://campusrec.illinois.edu/hours",
            "valid": list(CAMPUS_REC_VALID),
            "weekly": entry["weekly"],
            "unknownDuring": [list(FALL_BREAK)] + [[d, d] for d in SHEET_CLOSED_DATES],
        }

    for name, entry in OWNER_CONFIRMED.items():
        buildings[name] = {
            "source": "hours confirmed by the site owner",
            "valid": list(SEMESTER),
            "weekly": entry["weekly"],
            "unknownDuring": [list(FALL_BREAK)] + [[d, d] for d in SHEET_CLOSED_DATES],
        }

    # Google listings win over every other source. Fetched ones first, then the
    # hand-read entries above (so a hand correction beats a stale fetch).
    google_file = ROOT / "data" / "google_hours.json"
    fetched = {}
    if google_file.exists():
        fetched = {name: entry["weekly"]
                   for name, entry in json.loads(google_file.read_text()).get("buildings", {}).items()}
        print(f"Google (fetched): {', '.join(fetched) or 'none'}")

    # Google supplies a WEEKLY PATTERN and nothing else, so it is merged in
    # rather than written over the top. Replacing the whole entry threw away
    # every richer thing a unit's own feed carries -- on the first real fetch
    # (2026-10-18) Main, Grainger and Funk each lost 7 days of exact DATED
    # hours and got a generalised week in their place. Dated hours win over a
    # weekly pattern in app.js precisely because they are better: they carry
    # the days a library closes early for a break.
    #
    # Where an entry has dated hours it also keeps its own source name. The
    # dated days are what the map actually reads, and they did not come from
    # Google, so they must not be labelled as if they had.
    for name, weekly in {**fetched, **GOOGLE_HOURS}.items():
        existing = buildings.get(name)
        if existing is None:
            buildings[name] = {
                "source": "Google Maps listing",
                "valid": list(SEMESTER),
                "weekly": weekly,
                "unknownDuring": [list(FALL_BREAK)] + [[d, d] for d in SHEET_CLOSED_DATES],
            }
            continue
        merged = dict(existing)
        merged["weekly"] = weekly
        if not existing.get("dates"):
            merged["source"] = "Google Maps listing"
            merged.pop("sourceUrl", None)
        buildings[name] = merged
    print(f"Google (by hand): {', '.join(GOOGLE_HOURS) or 'none'}")

    carried = extend_through_finals(buildings)
    print(f"weekly hours carried through finals ({FINALS_THROUGH}): {len(carried)}")

    out = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campusClosedDates": SHEET_CLOSED_DATES + WINTER_CLOSED + SPRING_CLOSED,
        "buildings": dict(sorted(buildings.items())),
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(out, indent=1))
    print(f"\nWrote {OUT_FILE.relative_to(ROOT)} with {len(buildings)} buildings")

    for line in unreadable:
        print("  unreadable (left unknown):", line)
    for line in warnings:
        print("  WARNING:", line)


if __name__ == "__main__":
    main()
