#!/usr/bin/env python3
"""
Build Maryland class activity into data/umd/class_activity.json, matching the
shape build_class_estimates.py produces for Illinois and build_osu_class_estimates.py
for Ohio State, so app.js can read any of the three.

Source: Testudo, the university's own Schedule of Classes. No key, no mirror.

  https://app.testudo.umd.edu/soc/<term>                      the 207 departments
  https://app.testudo.umd.edu/soc/<term>/<DEPT>               course ids
  https://app.testudo.umd.edu/soc/<term>/sections?courseIds=…  the meetings
  https://app.testudo.umd.edu/soc/buildings/<CODE>%20<ROOM>    what a code is

Four things differ from the other two campuses.

  * It is HTML, not JSON or XML. Testudo serves fragments with stable classes
    (`building-code`, `section-days`, `class-start-time`), which is what makes
    this parseable at all, but it is markup and it can change — every parse
    failure is therefore counted and printed rather than skipped in silence.

  * **It is slow, and it throttles a burst.** Measured: a building lookup
    answers in 0.2s, but a DEPARTMENT page takes 20 seconds every time, and a
    fast run starts timing out after a few dozen requests. Testudo's own
    latency, not politeness, is what sets the pace — 207 department pages is
    over an hour before a single section is read. So every response is cached
    on disk, a rerun resumes instead of starting over, and a failure cools off
    for a while rather than hammering. This is why --offline exists.

  * Buildings are joined on the BUILDING CODE, and the code's meaning comes
    from Testudo itself. `/soc/buildings/KEY 0106` answers "Francis Scott Key
    Hall, Bldg Code: KEY, Bldg Number: 048" — an official name AND the
    university's own building number, which is the key Maryland's state GIS
    publishes footprints under. One cached lookup per code gives the register
    join for free, where Ohio State needed hand-written aliases.

    It also catches what a code list cannot: `TBA` resolves to "Meeting place
    to be arranged", building number 000. Codes that are not places are dropped
    on the university's own answer rather than on a list of exceptions here.

  * A meeting's type is a per-meeting label, not a section-level field. One
    section can hold a lecture row and a discussion row (CMSC131 0101 meets
    MWF in IRB 0324 and MW in CSI 2120, the second marked "Discussion"), and a
    lab section's FIRST row carries "Lab" — verified across CHEM, where 101 of
    216 sections are typed on their first row. So each row is weighted on its
    own label, and an unlabelled row is the course's main meeting.

`hours` is weighted and counted exactly as the other two builders do it — a
meeting counts its type's weight in every clock hour it touches — so all three
campuses' files mean the same thing and can be compared.

Usage:
  python3 scripts/build_umd_class_estimates.py                  # fetch and write
  python3 scripts/build_umd_class_estimates.py --offline        # rebuild from cache
  python3 scripts/build_umd_class_estimates.py --depts CMSC,MATH  # a sample, for testing
"""

import argparse
import collections
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "umd" / "class_activity.json"
CODES_FILE = ROOT / "data" / "umd" / "building_codes.json"
ROOMS_FILE = ROOT / "data" / "umd" / "rooms.json"
HOURS_FILE = ROOT / "data" / "umd" / "building_hours.json"
CACHE_DIR = ROOT / "data" / "umd" / ".cache"

SOC = "https://app.testudo.umd.edu/soc"
TERM = "202608"            # Fall 2026
TERM_LABEL = "2026/fall"
# Testudo's own term dropdown already defaults to Spring 2027, so the term is
# set here on purpose rather than read from the selected option.

COURSE_IDS_PER_REQUEST = 25   # 40 worked too; 25 keeps a retry cheap
PAUSE = 1.0                   # Testudo's latency already paces this
# Two different endpoints with two different normal speeds, so they get two
# different patiences. A department page measured 20s every time and has to be
# waited for. A building lookup normally answers in 0.2s, so a slow one is a
# hang, not work in progress — abandoning it after 15s and asking again is far
# cheaper than sitting through a 70s stall, which is what a shared 60s timeout
# turned every flaky lookup into.
PAGE_TIMEOUT, PAGE_COOL_OFF = 60, (15, 30, 60)
LOOKUP_TIMEOUT, LOOKUP_COOL_OFF = 15, (3, 10, 20)

# The weights Illinois and Ohio State use, mapped onto the labels Testudo
# prints. An unlabelled row is the course's main scheduled meeting — that is
# what Testudo leaves unlabelled, and it is the lecture in every department
# sampled — so it takes the lecture weight. Anything new prints itself at the
# end instead of being silently defaulted.
MAIN_MEETING_WEIGHT = 3.0     # Illinois LEC/LCD, Ohio State "Lecture"
TYPE_WEIGHTS = {
    "Discussion": 1.0,
    "Recitation": 1.0,
    "Lab": 1.5,
    "Laboratory": 1.5,
    "Seminar": 1.0,
    "Studio": 1.0,
    "Workshop": 1.0,
    "Clinic": 0.5,
    "Practicum": 0.5,
    "Field Work": 0.5,
    "Independent Study": 0.2,
}
DEFAULT_WEIGHT = 1.0

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
# Two-letter tokens first, or "Th" reads as T followed by H.
DAY_TOKENS = [("Tu", "tuesday"), ("Th", "thursday"), ("Sa", "saturday"), ("Su", "sunday"),
              ("M", "monday"), ("W", "wednesday"), ("F", "friday")]

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*([ap])\.?m\.?$", re.I)
COURSE_SECTIONS_RE = re.compile(r'<div id="([A-Z]{4}\d{3}[A-Z]?)" class="course-sections">')
SECTION_RE = re.compile(r'<div class="section ([^"]*)">')
NOT_A_PLACE = "000"       # the building number Testudo gives TBA


def cached(name):
    return CACHE_DIR / name


FAILED = {}        # cache name -> why, for the report at the end


def fetch(url, name, offline, timeout=PAGE_TIMEOUT, cool_off=PAGE_COOL_OFF):
    """One GET, cached on disk by `name`. Returns the body or None.

    A failure is cached too, as `<name>.failed` holding the reason. Testudo's
    building lookup answers 404 for a code it has never heard of and 500 for
    one it knows and chokes on — and those two mean completely different
    things (off-campus versus a real building we are losing), so the reason has
    to survive a rerun rather than being re-discovered by hammering a dead URL.
    """
    path = cached(name)
    if path.exists():
        return path.read_text(encoding="utf-8")
    dead = cached(name + ".failed")
    if dead.exists():
        FAILED[name] = dead.read_text(encoding="utf-8").strip()
        return None
    if offline:
        FAILED[name] = "not cached"
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (UIUC Spaces build)"})
    for attempt in range(len(cool_off) + 1):
        try:
            body = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
            time.sleep(PAUSE)
            return body
        except Exception as err:
            why = f"HTTP {err.code}" if isinstance(err, urllib.error.HTTPError) \
                else type(err).__name__
            # An HTTP status is Testudo's answer, not a hiccup. Retrying a 404
            # or a 500 four times only wastes a minute per code: measured 3/3
            # 500s on BMS 3118 back to back.
            if isinstance(err, urllib.error.HTTPError) or attempt == len(cool_off):
                print(f"  giving up on {name}: {why}", flush=True)
                FAILED[name] = why
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cached(name + ".failed").write_text(why, encoding="utf-8")
                return None
            print(f"  {name}: {why}, waiting {cool_off[attempt]}s", flush=True)
            time.sleep(cool_off[attempt])
    return None


def to_decimal(text):
    """'10:00am' -> 10.0. None when it can't be read exactly."""
    m = TIME_RE.match((text or "").strip())
    if not m:
        return None
    hour = int(m.group(1)) % 12
    if m.group(3).lower() == "p":
        hour += 12
    return hour + int(m.group(2)) / 60


def parse_days(text):
    """'TuTh' -> ['tuesday', 'thursday']. None when any of it is unreadable, so
    a day string we don't understand is reported rather than half-counted."""
    rest, out = (text or "").strip(), []
    while rest:
        for token, day in DAY_TOKENS:
            if rest.startswith(token):
                out.append(day)
                rest = rest[len(token):]
                break
        else:
            return None
    return out or None


def hours_touched(start, end):
    """The clock hours a meeting occupies. A part-hour counts as a whole one and
    a class ending exactly on the hour does not reach into it — the convention
    the Illinois and Ohio State builders use, kept so the three files compare."""
    return range(int(start), min(int(end - 1 / 60) + 1, 24))


def one(pattern, text):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def departments(offline):
    body = fetch(f"{SOC}/{TERM}", f"depts-{TERM}.html", offline)
    if not body:
        return []
    return sorted(set(re.findall(rf'href="{TERM}/([A-Z]{{4}})"', body)))


def course_ids(dept, offline):
    body = fetch(f"{SOC}/{TERM}/{dept}", f"dept-{dept}.html", offline)
    if not body:
        return []
    return sorted(set(re.findall(r'<div class="course-id"[^>]*>\s*([A-Z]{4}\d{3}[A-Z]?)\s*</div>', body)))


def sections_html(ids, offline):
    q = ",".join(ids)
    name = f"sections-{ids[0]}-{len(ids)}.html"
    return fetch(f"{SOC}/{TERM}/sections?courseIds={urllib.parse.quote(q)}", name, offline)


def building(code, room, offline):
    """Testudo's own answer for a code: (official name, building number)."""
    body = fetch(f"{SOC}/buildings/{urllib.parse.quote(f'{code} {room}')}",
                 f"building-{code}.html", offline,
                 timeout=LOOKUP_TIMEOUT, cool_off=LOOKUP_COOL_OFF)
    if not body:
        return None, None
    name = one(r'class="building-name">\s*(?:<!--.*?-->)?\s*<a[^>]*>([^<]*)</a>',
               body.replace("\n", " "))
    codes = re.findall(r'<span class="code">([^<]*)</span>', body)
    # Bldg Code, Bldg Number, Room Number, in that order.
    number = codes[1].strip() if len(codes) > 1 else None
    return name, number


def meetings(html, stats):
    """Every scheduled meeting in one sections response.
    -> (course, section, kind, code, room, days, start, end, seats)"""
    out = []
    bounds = [(m.group(1), m.end()) for m in COURSE_SECTIONS_RE.finditer(html)]
    for i, (course, start_at) in enumerate(bounds):
        end_at = bounds[i + 1][1] if i + 1 < len(bounds) else len(html)
        block = html[start_at:end_at]

        marks = [(m.group(1), m.end()) for m in SECTION_RE.finditer(block)]
        for j, (delivery, sec_at) in enumerate(marks):
            sec_end = marks[j + 1][1] if j + 1 < len(marks) else len(block)
            sec = block[sec_at:sec_end]
            number = one(r'name="sectionId" value="([^"]*)"', sec) or "?"
            seats = one(r'class="total-seats-count">\s*(\d+)', sec)
            seats = int(seats) if seats else 0
            stats[f"delivery:{delivery}"] += 1

            if "class-days-container" not in sec:
                stats["sections_with_no_meetings"] += 1
                continue
            rows = re.split(r'<div class="row">', sec.split("class-days-container", 1)[1])[1:]
            for row in rows:
                code = one(r'class="building-code">\s*([A-Z0-9]+)\s*<', row)
                if not code:
                    # Online and arranged meetings have no room. Not an error.
                    stats["rows_with_no_room"] += 1
                    continue
                room = one(r'class="class-room">\s*([^<\s]+)\s*<', row) or ""
                days = parse_days(one(r'class="section-days">\s*([^<]*?)\s*<', row))
                start = to_decimal(one(r'class="class-start-time">\s*([^<]*?)\s*<', row))
                end = to_decimal(one(r'class="class-end-time">\s*([^<]*?)\s*<', row))
                if not days or start is None or end is None:
                    stats["rows_with_no_day_or_time"] += 1
                    continue
                if end <= start:
                    stats["rows_with_bad_range"] += 1
                    continue
                kind = one(r'class="class-type">\s*([^<]*?)\s*<', row)
                out.append((course, number, kind, code, room, days, start, end, seats))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="rebuild from cache only")
    ap.add_argument("--depts", help="comma-separated department codes, for testing")
    args = ap.parse_args()

    depts = args.depts.split(",") if args.depts else departments(args.offline)
    if not depts:
        print("could not reach Testudo (and nothing cached)", file=sys.stderr)
        return 1
    print(f"{len(depts)} departments in {TERM}")

    started = time.time()
    stats = collections.Counter()
    by_kind = collections.Counter()
    unknown_kinds = collections.Counter()
    slots = {}                 # (code, room, day, start, end) -> (weight, seats)
    rooms = collections.defaultdict(set)
    missing_courses = []
    no_sections = []

    for n, dept in enumerate(depts, 1):
        ids = course_ids(dept, args.offline)
        if not ids:
            stats["departments_with_no_courses"] += 1
            continue
        stats["courses"] += len(ids)
        for i in range(0, len(ids), COURSE_IDS_PER_REQUEST):
            batch = ids[i:i + COURSE_IDS_PER_REQUEST]
            html = sections_html(batch, args.offline)
            if html is None:
                missing_courses += batch
                continue
            # Testudo answers with one container per course that HAS sections.
            # A course in the catalog with none this term comes back as an empty
            # <div> — verified by asking for AAAS399 on its own, which returns
            # 21 bytes and no container. So this is ordinary, and counted rather
            # than flagged; a real hole is a fetch that failed, which
            # missing_courses below carries.
            got = set(COURSE_SECTIONS_RE.findall(html))
            no_sections += sorted(set(batch) - got)

            for course, sec, kind, code, room, days, start, end, seats in meetings(html, stats):
                weight = MAIN_MEETING_WEIGHT if kind is None else TYPE_WEIGHTS.get(kind, DEFAULT_WEIGHT)
                if kind is not None and kind not in TYPE_WEIGHTS:
                    unknown_kinds[kind] += 1
                by_kind[kind or "(main meeting)"] += 1
                if not weight:
                    stats["rows_zero_weight"] += 1
                    continue
                rooms[code].add(room)
                for day in days:
                    slot = (code, room, day, start, end)
                    # A room holds one thing at a time, so two sections in the
                    # same room at the same hour are one event listed twice —
                    # cross-listed courses do this constantly. Count the slot
                    # once, at the heavier weight, as both other campuses do.
                    if weight > slots.get(slot, (0, 0))[0]:
                        slots[slot] = (weight, seats)
                    else:
                        stats["duplicate_room_hour"] += 1
                stats["rows_used"] += 1
        if n % 20 == 0 or n == len(depts):
            print(f"  {n}/{len(depts)} departments, {stats['rows_used']} meetings, "
                  f"{len(rooms)} codes", flush=True)

    # --- what each code actually is, from Testudo ---
    names, numbers, not_places = {}, {}, []
    unresolved = {}
    for code in sorted(rooms):
        # TBA arrives with an empty room, which would make a malformed URL.
        # It is not a place either way, so it is named as one here rather than
        # counted as a lookup that failed.
        room = next((r for r in sorted(rooms[code]) if r), None)
        if room is None:
            not_places.append(f"{code} (no room given)")
            continue
        name, number = building(code, room, args.offline)
        if not name:
            unresolved[code] = FAILED.get(f"building-{code}.html", "no name in response")
            continue
        if number == NOT_A_PLACE:
            # "Meeting place to be arranged" and anything else the university
            # files under building 000. Dropped on its own answer.
            not_places.append(f"{code} ({name})")
            continue
        names[code] = name
        numbers[code] = number

    # --- accumulate, once per surviving slot ---
    counts = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    seats_h = collections.defaultdict(lambda: {d: [0.0] * 24 for d in DAYS})
    for (code, _room, day, start, end), (weight, seats) in slots.items():
        if code not in names:
            continue
        for h in hours_touched(start, end):
            counts[code][day][h] += weight
            seats_h[code][day][h] += weight * seats

    hours_names = {}
    if HOURS_FILE.exists():
        hours_names = {v.get("code"): k
                       for k, v in json.loads(HOURS_FILE.read_text())["buildings"].items()}

    buildings = {}
    for code, days in counts.items():
        used = {d: [round(v, 2) for v in vals] for d, vals in days.items() if any(vals)}
        if not used:
            continue
        entry = {
            "peak": round(max(max(v) for v in used.values()), 2),
            "hours": used,
            "code": code,
            "number": numbers[code],
        }
        s_used = {d: [round(v, 1) for v in vals]
                  for d, vals in seats_h[code].items() if any(vals)}
        if s_used:
            entry["seats"] = s_used
            entry["seatsPeak"] = round(max(max(v) for v in s_used.values()), 1)
        entry["hasHours"] = code in hours_names
        buildings[names[code]] = entry

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps({
        "term": TERM_LABEL,
        "campus": "Maryland — College Park",
        "source": "University of Maryland Schedule of Classes (Testudo)",
        "sourceUrl": f"{SOC}/{TERM}",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Weighted count of class meetings in progress. Not people. "
                "Weights and hour counting match data/class_activity.json. "
                "`seats` is the same weighting times each section's seat total — "
                "Testudo publishes the SECTION cap, not the room's capacity, "
                "which is what Ohio State's `seats` uses.",
        "buildings": buildings,
    }, indent=1) + "\n")

    # ── room-level output ──
    # The aggregate above answers "how busy is this building". It cannot answer
    # "which room is free", because summing to a per-hour count throws the room
    # away. `slots` already holds exactly that detail, so write it out too
    # rather than sweeping Testudo twice for the same thing.
    #
    # A room appearing here means no class is SCHEDULED in it. It does not mean
    # the door is unlocked, so whatever reads this file has to say "no class
    # scheduled", not "free".
    #
    # No `capacity` is written, unlike Columbus. Ohio State publishes the ROOM's
    # capacity; Testudo publishes the SECTION's seat cap, and the largest
    # section timetabled in a room is only a floor on how many seats it has.
    # Printing "seats 35" for a room that holds 60 would be a confident wrong
    # answer, and app.js already drops the clause when the number is absent.
    room_rows = {}
    for (code, room, day, start, end), (_weight, _seats) in slots.items():
        if code not in names:
            continue
        fid = f"{code}{room}"
        entry = room_rows.setdefault(fid, {"code": code, "busy": {}})
        entry["busy"].setdefault(day, []).append([start, end])
    for entry in room_rows.values():
        # Merge touching or overlapping classes so a run of back-to-back
        # lectures reads as one closed stretch rather than several.
        for day, spans in entry["busy"].items():
            merged = []
            for a, b in sorted(spans):
                if merged and a <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], b)
                else:
                    merged.append([a, b])
            entry["busy"][day] = merged

    by_building = {}
    for fid, entry in room_rows.items():
        name = names[entry["code"]]
        by_building.setdefault(name, {"code": entry["code"], "rooms": {}})
        by_building[name]["rooms"][fid] = {"busy": entry["busy"]}

    ROOMS_FILE.write_text(json.dumps({
        "term": TERM_LABEL,
        "campus": "Maryland — College Park",
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Hours each room is taken by a scheduled class, per weekday. "
                "A room not listed as busy has NO CLASS SCHEDULED — which is not "
                "the same as unlocked or available. Room seat counts are not "
                "published by Testudo, so none are given.",
        "buildings": by_building,
    }, indent=1) + "\n")

    # The code table, so build_umd_buildings.py joins to the state GIS on the
    # university's own building numbers without asking Testudo all over again.
    CODES_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "University of Maryland Schedule of Classes building lookup",
        "sourceUrl": f"{SOC}/buildings/",
        "codes": {c: {"name": names[c], "number": numbers[c]} for c in sorted(names)},
    }, indent=1) + "\n")

    print(f"\ncourses asked for:  {stats['courses']}")
    print(f"meetings used:      {stats['rows_used']}  "
          f"({', '.join(f'{k}={v}' for k, v in by_kind.most_common())})")
    print(f"rows with no room:  {stats['rows_with_no_room']} (online or arranged)")
    print(f"sections with none:  {stats['sections_with_no_meetings']} (no meeting rows at all)")
    print(f"rows unreadable:    day/time {stats['rows_with_no_day_or_time']}, "
          f"range {stats['rows_with_bad_range']}")
    print(f"room-hours kept:    {len(slots)} "
          f"(dropped {stats['duplicate_room_hour']} already taken by another section)")
    print(f"codes:              {len(rooms)} seen, {len(names)} are buildings, "
          f"{len(unresolved)} unresolved")
    if not_places:
        print(f"not places:         {', '.join(not_places)}")
    if unresolved:
        # 404 = the College Park lookup has never heard of this code, which is
        # what an off-campus teaching centre looks like (Shady Grove, the DC
        # centre) — the Wooster case, and correctly dropped. 500 = Testudo
        # knows the code and errors on it, which is a REAL building being lost.
        gone = collections.defaultdict(list)
        for code, why in sorted(unresolved.items()):
            gone[why].append(code)
        for why, codes in sorted(gone.items()):
            kind = ("off campus — the College Park lookup has no such code"
                    if why == "HTTP 404" else
                    "Testudo errors on a code it knows: REAL buildings, see docs/maryland.md"
                    if why == "HTTP 500" else "")
            print(f"  {why:<12} {' '.join(codes)}"
                  f"{chr(10) + ' ' * 15 + kind if kind else ''}")
    print(f"buildings:          {len(buildings)}")
    deliveries = {k.split(':', 1)[1]: v for k, v in stats.items() if k.startswith('delivery:')}
    print(f"delivery modes:     {deliveries}")
    if unknown_kinds:
        print(f"!! meeting types with no weight (counted as {DEFAULT_WEIGHT}): "
              f"{dict(unknown_kinds)}", file=sys.stderr)
    if stats["departments_with_no_courses"]:
        print(f"!! {stats['departments_with_no_courses']} departments listed no courses",
              file=sys.stderr)
    print(f"courses with none:  {len(no_sections)} (in the catalog, not offered "
          f"this term)")
    if missing_courses:
        print(f"!! {len(missing_courses)} courses never fetched (rerun to resume): "
              f"{missing_courses[:10]}{'…' if len(missing_courses) > 10 else ''}",
              file=sys.stderr)
    print(f"rooms written:      {len(room_rows)} in {len(by_building)} buildings")
    print(f"-> {OUT_FILE.relative_to(ROOT)}")
    print(f"-> {CODES_FILE.relative_to(ROOT)}")
    print(f"-> {ROOMS_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
