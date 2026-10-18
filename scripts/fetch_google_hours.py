#!/usr/bin/env python3
"""
Fetch opening hours from Google Maps listings (via SerpApi) into
data/google_hours.json. build_hours.py then uses them above every other source:
Google says when a place is actually open to people, while the campus
spreadsheet only says when Facilities unlocks the doors.

Usage:
  export SERPAPI_KEY=your_key_here
  python3 scripts/fetch_google_hours.py --dry-run           # 0 searches
  python3 scripts/fetch_google_hours.py --only "Illini Union"
  python3 scripts/fetch_google_hours.py                     # all places below

Budget: one search per place. The free SerpApi plan allows 250/month, so the
list below is the public-facing buildings where Google is likely to be both
present and right — run it monthly, or weekly for a shorter list.

Nothing is guessed: a listing that doesn't match the expected name, or hours we
can't parse exactly, is skipped and reported.
"""

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "google_hours.json"
CAMPUS_LL = "@40.1065,-88.2270,15z"

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# map building name -> what to search, and words the result's title must contain
PLACES = {
    "Illini Union Bookstore": ("Illini Union Bookstore, Champaign, IL", ["bookstore"]),
    "Illini Union":           ("Illini Union, Champaign, IL", ["illini union"]),
    "Main Library":           ("Main Library, 1408 W Gregory Dr, Urbana, IL", ["main library"]),
    "Grainger Engineering Library": ("Grainger Engineering Library Information Center, Urbana, IL", ["grainger"]),
    "Funk Library":           ("Funk ACES Library, Urbana, IL", ["funk"]),
    "Activities and Recreation Center": ("Activities and Recreation Center, Champaign, IL", ["activities and recreation"]),
    "Campus Recreation Center East":   ("Campus Recreation Center East, Urbana, IL", ["campus recreation center east"]),
    "Campus Instructional Facility":   ("Campus Instructional Facility, Urbana, IL", ["campus instructional"]),
    "Business Instructional Facility": ("Business Instructional Facility, Champaign, IL", ["business instructional"]),
    "Student Dining and Residential Programs (SDRP)": ("Ikenberry Dining Center, Champaign, IL", ["ikenberry", "dining"]),
    "Krannert Center for the Performing Arts": ("Krannert Center for the Performing Arts, Urbana, IL", ["krannert"]),
    "Spurlock Museum":        ("Spurlock Museum, Urbana, IL", ["spurlock"]),
    "Ice Arena":              ("University of Illinois Ice Arena, Champaign, IL", ["ice arena"]),
}

# Ohio State is a PROBE, not a source yet, and deliberately small.
#
# Google outranks every other source in build_hours.py, which is right for
# Illinois -- there the campus spreadsheet records when Facilities unlocks a
# door, while Google records when a place is open to people. Ohio State is the
# opposite case: the registrar page IS the lock-up schedule, and the libraries
# and rec centres publish exact dated hours. Pointing Google at those would
# replace good data with worse, so none of them are listed here.
#
# What is listed is six buildings with NO other source, plus two controls whose
# real hours the registrar already publishes. The controls are the point: they
# say whether Google can be trusted for an Ohio State academic building at all.
# A first look on 2026-10-18 was not encouraging -- Hamilton Hall's listing is
# unclaimed and reads "Opens 12 AM Mon" -- so measure before wiring any of this
# into build_osu_hours.py.
#
# Run with: python3 scripts/fetch_google_hours.py --campus osu
PLACES_OSU = {
    # --- controls: the registrar publishes these, so we can score Google ---
    # Ag. Admin.    Mon 7-20, Tue-Thu 7-18, Fri 7-17, Sat/Sun closed
    # Pomerene Hall Mon-Fri 7-21:30, Sat closed, Sun 16-21:30
    "Ag. Admin.":     ("Agricultural Administration Building, 2120 Fyffe Rd, Columbus, OH",
                       ["agricultural administration"]),
    "Pomerene Hall":  ("Pomerene Hall, Ohio State University, Columbus, OH", ["pomerene"]),

    # --- the gap: busiest buildings with no published hours ---
    "Hamilton Hall":            ("Hamilton Hall, 1645 Neil Ave, Columbus, OH", ["hamilton hall"]),
    "Drinko Hall, John Deaver": ("Moritz College of Law, 55 W 12th Ave, Columbus, OH",
                                 ["moritz", "drinko", "law"]),
    "Atwell Hall":              ("Atwell Hall, 453 W 10th Ave, Columbus, OH", ["atwell"]),
    "Mason Hall":               ("Mason Hall, 250 W Woodruff Ave, Columbus, OH", ["mason hall"]),
    "Younkin Success Center":   ("Younkin Success Center, 1640 Neil Ave, Columbus, OH", ["younkin"]),
    "Pressey Hall":             ("Pressey Hall, 1070 Carmack Rd, Columbus, OH", ["pressey"]),
}

# name -> where its results go, where to search, and what to run afterwards.
CAMPUSES = {
    "uiuc": {
        "places": PLACES,
        "out": ROOT / "data" / "google_hours.json",
        "ll": CAMPUS_LL,
        "then": "scripts/build_hours.py",
    },
    "osu": {
        "places": PLACES_OSU,
        "out": ROOT / "data" / "osu" / "google_hours.json",
        "ll": "@40.0125,-83.0307,15z",   # centroid of the 454 Columbus buildings
        "then": None,                    # nothing reads this yet, on purpose
    },
}


def serpapi(params, api_key):
    url = "https://serpapi.com/search.json?" + urllib.parse.urlencode({**params, "api_key": api_key})
    with urllib.request.urlopen(url, timeout=60) as resp:
        return json.load(resp)


def parse_clock(text):
    """'8 AM' / '8:30 PM' / 'noon' / 'midnight' -> hours as a number, or None."""
    text = text.strip().lower().replace(".", "")
    if text in ("noon", "12 noon"):
        return 12.0
    if text in ("midnight", "12 midnight"):
        return 24.0
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*([ap])m?", text)
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2) or 0)
    if m.group(3) == "p":
        hour += 12
    return hour + minute / 60


def parse_day_hours(text):
    """'8 AM–6 PM' -> [[8, 18]]; 'Closed' -> []; '24 hours' -> [[0, 24]]; None if unclear."""
    if not text:
        return None
    text = text.strip().lower().replace(" ", " ")
    if "closed" in text:
        return []
    if "24 hours" in text or text == "open 24 hours":
        return [[0, 24]]

    ranges = []
    for span in re.split(r",|\band\b", text):
        span = span.strip()
        if not span:
            continue
        m = re.fullmatch(r"(.+?)\s*[–\-—to]+\s*(.+)", span)
        if not m:
            return None
        start, end = parse_clock(m.group(1)), parse_clock(m.group(2))
        if start is None or end is None:
            return None
        if end <= start:
            end += 24                      # runs past midnight
        ranges.append([round(start, 2), round(end, 2)])
    return ranges or None


def hours_from_place(place):
    """SerpApi place_results -> {day: [[open, close], …]} or None."""
    raw = place.get("hours") or place.get("operating_hours")
    by_day = {}
    if isinstance(raw, list):              # [{"monday": "8 AM–6 PM"}, …]
        for entry in raw:
            for day, text in entry.items():
                by_day[day.strip().lower()] = text
    elif isinstance(raw, dict):            # {"monday": "8 am–6 pm", …}
        by_day = {k.strip().lower(): v for k, v in raw.items()}
    else:
        return None

    week = {}
    for day in DAYS:
        parsed = parse_day_hours(by_day.get(day))
        if parsed is None:
            return None                    # incomplete or unreadable: use nothing
        week[day] = parsed
    return week


def fetch(name, query, expect, api_key):
    response = serpapi({"engine": "google_maps", "type": "search", "q": query, "ll": ll}, api_key)
    if "error" in response:
        raise RuntimeError(response["error"])
    place = response.get("place_results")
    if not place:
        candidates = [r.get("title") for r in response.get("local_results") or []][:5]
        raise RuntimeError(f"no single match (candidates: {candidates})")
    title = place.get("title", "")
    if not all(word in title.lower() for word in expect):
        raise RuntimeError(f"result '{title}' doesn't look like this building")
    week = hours_from_place(place)
    if not week:
        raise RuntimeError("no readable hours in the listing")
    return {"google_title": title, "weekly": week}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--campus", choices=sorted(CAMPUSES), default="uiuc",
                        help="which campus's place list to search (default: uiuc)")
    parser.add_argument("--only", help="just this building (exact key from the campus list)")
    parser.add_argument("--dry-run", action="store_true", help="list what would be searched")
    args = parser.parse_args()

    campus = CAMPUSES[args.campus]
    all_places, out_file = campus["places"], campus["out"]

    places = all_places if not args.only else {args.only: all_places.get(args.only)}
    if args.only and not places[args.only]:
        sys.exit(f"Unknown building '{args.only}'. Options: {', '.join(all_places)}")

    if args.dry_run:
        for name, (query, _) in places.items():
            print(f"{name:48} <- {query}")
        print(f"\nWould use {len(places)} SerpApi search(es) against {args.campus}.")
        return

    api_key = os.environ.get("SERPAPI_KEY")
    if not api_key:
        sys.exit("Set SERPAPI_KEY first:  export SERPAPI_KEY=your_key_here")

    existing = json.loads(out_file.read_text()) if out_file.exists() else {"buildings": {}}
    for name, (query, expect) in places.items():
        try:
            result = fetch(name, query, expect, api_key, campus["ll"])
            existing["buildings"][name] = result
            print(f"OK    {name}: '{result['google_title']}' — {result['weekly']['monday']} Mon")
        except Exception as e:
            print(f"SKIP  {name}: {e}")

    existing["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(existing, indent=1))
    print(f"\nWrote {out_file.relative_to(ROOT)} ({len(existing['buildings'])} buildings)")
    if campus["then"]:
        print(f"Now run: python3 {campus['then']}")
    else:
        print("Nothing reads this yet -- compare the two control buildings against\n"
              "the registrar's published hours before wiring it into build_osu_hours.py.")


if __name__ == "__main__":
    main()
