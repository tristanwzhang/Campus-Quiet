#!/usr/bin/env python3
"""
Build data/utsg/building_hours.json for U of T St. George.

What is published, and what is not.

PUBLISHED, dated, 12 weeks ahead, with the holiday closures already in it:
    https://library.utoronto.ca/library/<slug>  -- each library page embeds
    `hoursJson` {"2026-10-18": {"status": "open", "hours": [{"from": "10am", "to": "10pm"}]}, ...}
    Closed days are explicit (Dec 24-26, Jan 1-5 ...). The window rolls, so this runs weekly.

A building gets library hours ONLY where the building IS the library (the rule the
other campuses use; a library inside a faculty building says nothing about its doors):
    Robarts Library                      <- Robarts Library (RL)
    Sigmund Samuel Library Building      <- Gerstein Science Information Centre (SM)
                                            (the map's record for SM is "7 & 9 King's College
                                            Circle"; Gerstein's address is 9 King's College Circle)

Every other building has NO published hours and rides the class-timetable fallback in
app.js, exactly as most of Ohio State and Maryland do. Searched and found nothing public
for the academic buildings; the Athletic Centre and Hart House publish their own but are
not in this file yet (Hart House has no classes, so it is not in the class data either).

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

# library page slug -> (building name as in class_activity.json, code, label for the source)
LIBRARIES = {
    "robarts": ("Robarts Library", "RL", "Robarts Library"),
    "gerstein": ("Sigmund Samuel Library Building", "SM", "Gerstein Science Information Centre"),
}

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
    return {d: [list(weekday)] for d in ("monday", "tuesday", "wednesday", "thursday", "friday")} | \
           {d: [list(weekend)] for d in ("saturday", "sunday")}


WEEKLY = {
    "Warren Stevens Building": {
        "source": "Faculty of Kinesiology & Physical Education: Athletic Centre hours",
        "sourceUrl": "https://kpe.utoronto.ca/facility/athletic-centre", "code": "WS",
        "weekly": _week((7, 23), (9, 17)), "valid": ["2026-09-08", "2026-12-23"],
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
    if day["status"] == "closed" or not day["hours"]:
        return []
    out = []
    for r in day["hours"]:
        a, b = clock(r["from"]), clock(r["to"])
        if b <= a:                      # "to 12am" or past midnight
            b += 24
        out.append([round(a, 4), round(b, 4)])
    return out


def hours_json(slug):
    html = urllib.request.urlopen(urllib.request.Request(
        f"https://library.utoronto.ca/library/{slug}", headers={"User-Agent": "CampusQuiet/1.0"}),
        timeout=60).read().decode("utf8", "replace").replace('\\"', '"')
    i = html.find('"hoursJson":')
    if i < 0:
        raise RuntimeError(f"{slug}: no hoursJson in page")
    return json.JSONDecoder().raw_decode(html[i + 12:])[0]


def main():
    buildings = {}
    for slug, (name, code, label) in LIBRARIES.items():
        hj = hours_json(slug)
        dates = {}
        for iso, day in sorted(hj.items()):
            try:
                dates[iso] = ranges(day)
            except ValueError as e:
                print(f"!! {slug} {iso}: unreadable time {e!r}; {day}", file=sys.stderr)
        if not dates:
            continue
        ks = sorted(dates)
        buildings[name] = {
            "source": f"{label} published hours",
            "sourceUrl": f"https://library.utoronto.ca/library/{slug}",
            "code": code, "dates": dates, "valid": [ks[0], ks[-1]],
        }
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
