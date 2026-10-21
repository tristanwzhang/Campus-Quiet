#!/usr/bin/env python3
"""
Build data/utsg/building_hours.json for U of T St. George.

What is published, and what is not.

PUBLISHED, dated, 12 weeks ahead, closures explicit -- ONE feed for every library:
    https://libcal.library.utoronto.ca/api_hours_grid.php?iid=478&format=json&weeks=12
    (the public hours widget behind libcal.library.utoronto.ca/hours). The window rolls,
    so this runs weekly. It replaced reading each library's own page.

A building gets library hours ONLY where the building IS the library (the rule the
other campuses use; a library inside a faculty building says nothing about its doors):
    Robarts Library                  <- "Robarts" (8158)                     RL
    Robarts Common                   <- "Robarts Common Building Hours" (8315; LibCal
                                        names these BUILDING hours. 24 h Mon-Thu.)  RC
    Sigmund Samuel Library Building  <- "Gerstein" (8321; the map's SM record is
                                        "7 & 9 King's College Circle", Gerstein is 9)  SM
    E.J. Pratt Library               <- "E.J. Pratt" (8438)                  PR
    John M. Kelly Library            <- "Kelly" (8454)                       KL
RC is this file's own key: U of T files Robarts Common under Robarts (RL), but its
hours are not Robarts' (24 h vs 8:30am-11pm), so it is placed separately.

PUBLISHED as a weekly pattern on the building's own page: see WEEKLY below.

Searched and NOT found (official building hours do not exist publicly, or conflict):
see docs/utsg.md. Those buildings ride the class-timetable fallback in app.js.

Calendar, all from U of T's own pages (engineering.calendar.utoronto.ca "Fall 2026 and
Winter 2027 Key Dates" and the SGS sessional dates PDF):
    closed: Sep 7 Labour Day, Oct 12 Thanksgiving, Dec 24 - Jan 5 winter break,
            Feb 15 Family Day
    no classes, offices open: Fall Study Break Oct 26-30 (Arts & Science and Engineering)

Usage:  python3 scripts/build_utsg_hours.py
"""

import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "utsg" / "building_hours.json"

GRID = "https://libcal.library.utoronto.ca/api_hours_grid.php?iid=478&format=json&weeks=12&systemTime=0"
# LibCal location id -> (building name as the map/class data has it, code, label)
LIBRARIES = {
    8158: ("Robarts Library", "RL", "Robarts Library"),
    8315: ("Robarts Common", "RC", "Robarts Common"),
    8321: ("Sigmund Samuel Library Building", "SM", "Gerstein Science Information Centre"),
    8438: ("E.J. Pratt Library", "PR", "E.J. Pratt Library"),
    8454: ("John M. Kelly Library", "KL", "John M. Kelly Library"),
}

# Locations whose LibCal dates carry no closures at all (checked 2026-10-21: Kelly
# lists every one of 84 days as open, Christmas included).
NO_HOLIDAYS_IN_FEED = {8454}

CAMPUS_CLOSED = (["2026-09-07", "2026-10-12", "2027-02-15"] +
                 [(date(2026, 12, 24) + timedelta(days=i)).isoformat() for i in range(13)])  # to Jan 5
CLASSES_OUT = [(date(2026, 10, 26) + timedelta(days=i)).isoformat() for i in range(5)]


# Published as a WEEKLY pattern on the unit's own page, read 2026-10-21. No dated feed
# exists, so these are valid only for the term the page describes and hold nothing for
# the days it does not mention (the winter break after 23 Dec reads "unknown").
#   Athletic Centre  https://kpe.utoronto.ca/facility/athletic-centre
#       "Monday to Friday: 7 a.m. - 11 p.m.  Saturday & Sunday: 9 a.m. - 5 p.m."
#       55 Harbord St, which is the map's address for WS ("Athletic Centre | WS | Warren
#       Stevens Building"). Open gym is listed to 23 Dec 2026; the page names no
#       Thanksgiving, study-break or winter closure, so none is claimed.
#   Hart House       https://harthouse.ca/contact/hours   (Cloudflare blocks scripts, so it
#       was read in a browser) -- Building, "Mon - Sun 7:00 am - 11:00 pm". Its fitness
#       centre and pool print separate HOLIDAY hours, so the building's holiday hours are
#       not known and no closure rule is applied.
def _week(weekday, weekend):
    """weekend=None means published as closed (e.g. key-fob only)."""
    return {d: [list(weekday)] for d in ("monday", "tuesday", "wednesday", "thursday", "friday")} | \
           {d: ([list(weekend)] if weekend else []) for d in ("saturday", "sunday")}


WEEKLY = {
    "Warren Stevens Building": {
        "source": "Faculty of Kinesiology & Physical Education: Athletic Centre hours",
        "sourceUrl": "https://kpe.utoronto.ca/facility/athletic-centre", "code": "WS",
        "weekly": _week((7, 23), (9, 17)), "valid": ["2026-09-08", "2026-12-23"],
    },
    # oise.utoronto.ca/about/cao/facilities, read 2026-10-21: "Building Hours
    # Monday-Friday: 7:00AM - 9:00PM | Saturday & Sunday: 9:00AM - 9:00PM". No holiday note.
    "Ontario Institute for Studies in Education": {
        "source": "OISE Building & Facilities Information",
        "sourceUrl": "https://www.oise.utoronto.ca/about/cao/facilities", "code": "OI",
        "weekly": _week((7, 21), (9, 21)), "valid": ["2026-09-08", "2026-12-23"],
    },
    # wdw.utoronto.ca/contact, read 2026-10-21, under "Building Hours: The building is
    # open: Monday - Friday: 8:30 am - 8:00 pm; Saturday - Sunday: 10:00 am - 6:00 pm".
    "Woodsworth College": {
        "source": "Woodsworth College building hours",
        "sourceUrl": "https://wdw.utoronto.ca/contact", "code": "WW",
        "weekly": _week((8.5, 20), (10, 18)), "valid": ["2026-09-08", "2026-12-23"],
    },
    # innis.utoronto.ca/contact, read 2026-10-21: "The college building is typically open
    # Monday-Friday, 8am-9pm" and "2 Sussex Avenue will be closed for renovation October
    # 26-30." Weekends are not stated, so they are left out (unknown), not closed.
    "Innis College": {
        "source": "Innis College building hours",
        "sourceUrl": "https://innis.utoronto.ca/contact/", "code": "IN",
        "weekly": {d: [[8, 21]] for d in ("monday", "tuesday", "wednesday", "thursday", "friday")},
        "valid": ["2026-09-08", "2026-12-23"],
        "dates": {f"2026-10-{d}": [] for d in range(26, 31)},
    },
    # rotman.utoronto.ca/registrar/resources/rotman-administrative-services, read
    # 2026-10-21: "hours of operation are Monday through Friday from 6:30 a.m. to 9:00 p.m.
    # Access from 9:00 p.m. to 6:30 a.m. and on weekends requires the use of an access key
    # fob" -- so weekends are closed to anyone without a Rotman fob.
    "Rotman School of Management": {
        "source": "Rotman School of Management hours of operation",
        "sourceUrl": "https://www.rotman.utoronto.ca/registrar/resources/rotman-administrative-services/",
        "code": "RT", "weekly": _week((6.5, 21), None), "valid": ["2026-09-08", "2026-12-23"],
    },
    # utsu.ca/contact-us, read 2026-10-21: "The Student Commons is located at 230 College
    # St. and the building is open from 9am to 9pm, Monday - Friday." The operator's own
    # page, though its footer is (c) 2020. Weekends not stated, so left unknown.
    "Student Commons": {
        "source": "UTSU: Student Commons building hours",
        "sourceUrl": "https://www.utsu.ca/contact-us/", "code": "SU",
        "weekly": {d: [[9, 21]] for d in ("monday", "tuesday", "wednesday", "thursday", "friday")},
        "valid": ["2026-09-08", "2026-12-23"],
    },
    "Hart House": {
        "source": "Hart House published building hours",
        "sourceUrl": "https://harthouse.ca/contact/hours", "code": "HH",
        "weekly": _week((7, 23), (7, 23)), "valid": ["2026-09-08", "2026-12-23"],
    },
}


def clock(text):
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m", text.strip().lower())
    if not m:
        raise ValueError(text)
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    h = h % 12 + (12 if ap == "p" else 0)
    return h + mi / 60


def ranges(day):
    """[[open, close], ...], [] for closed, None for a day the library has not set."""
    if day["status"] == "not-set":
        return None
    if day["status"] == "24hours":
        return [[0, 24]]
    if day["status"] in ("closed", "text") or not day.get("hours"):
        return []
    out = []
    for r in day["hours"]:
        a, b = clock(r["from"]), clock(r["to"])
        if r["to"].strip().lower() == "11:59pm":
            b = 24
        if b <= a:                      # "to 12am" or past midnight
            b += 24
        out.append([round(a, 4), round(b, 4)])
    return out


def grid():
    """{lid: {date: day}} for every location and sub-location in the feed."""
    body = urllib.request.urlopen(urllib.request.Request(GRID, headers={"User-Agent": "CampusQuiet/1.0"}),
                                  timeout=60).read()
    out = {}

    def walk(locs):
        for loc in locs:
            days = {}
            for wk in loc.get("weeks", []):
                for day in wk.values():
                    days[day["date"]] = day["times"]
            out[int(loc["lid"])] = (loc["name"], days)
            walk(loc.get("children", []))
    walk(json.loads(body)["locations"])
    return out


def main():
    feed = grid()
    buildings = {}
    for lid, (name, code, label) in LIBRARIES.items():
        if lid not in feed:
            print(f"!! LibCal location {lid} ({label}) is missing from the feed", file=sys.stderr)
            continue
        dates = {}
        for iso, day in sorted(feed[lid][1].items()):
            try:
                r = ranges(day)
            except ValueError as e:
                print(f"!! {label} {iso}: unreadable time {e!r}; {day}", file=sys.stderr)
                continue
            if r is None:
                continue              # not set: unknown, never "closed"
            # Kelly's feed is its regular week copied onto every date -- it says open
            # 8:30am-11:30pm on Christmas Day. Where a feed never marks a closure, the
            # university's own closure days are applied instead of its dated hours.
            if lid in NO_HOLIDAYS_IN_FEED and iso in CAMPUS_CLOSED:
                continue
            dates[iso] = r
        if not dates:
            continue
        ks = sorted(dates)
        buildings[name] = {
            "source": f"{label} published hours (U of T Libraries)",
            "sourceUrl": "https://libcal.library.utoronto.ca/hours/",
            "code": code, "dates": dates, "valid": [ks[0], ks[-1]],
        }
        if lid in NO_HOLIDAYS_IN_FEED:
            buildings[name]["followsCampusClosures"] = True
        print(f"{name}: {len(dates)} days {ks[0]}..{ks[-1]}; closed {sum(1 for v in dates.values() if not v)}")

    buildings.update(WEEKLY)

    OUT.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "campus": "University of Toronto — St. George",
        "term": "2026/fall",
        "campusClosedDates": CAMPUS_CLOSED,
        "classesOutDates": CLASSES_OUT,
        "buildings": buildings,
    }, indent=1) + "\n")
    print(f"-> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
