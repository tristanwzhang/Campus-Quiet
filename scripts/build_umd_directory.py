#!/usr/bin/env python3
"""
Build data/umd/directory.json: the University of Maryland's own campus-map
building directory, as {building number: {name, section}}.

Source: the campus map PDF the university publishes (also linked from its
campus-map pages), whose back page is a "BUILDING DIRECTORY" in three printed
sections:

    KEY PLACES OF INTEREST   visitor-facing places: libraries, the stadium,
                             the health center, dining halls, the hotel
    UNIVERSITY BUILDINGS     academic, administrative, research, service
    CAMPUS HOUSING           residence halls and apartments

Why this exists. The map needs to know whether a building is a residence hall,
and nothing else on the campus publishes that. It matters because the one
campus-wide hours rule Maryland publishes — UMPD Building Security Services:
"Campus academic and administrative facilities are generally open to the public
from 7:00am to 9:00pm Monday through Friday" — is explicitly NOT about
residence halls, which are card access. Eight residence halls host classes
(LaPlata, Somerset, Cumberland, Centreville, Dorchester, Prince Frederick,
Anne Arundel, Queen Ann's), and without this they would be read as academic
buildings and shown open to the public at 7am.

The PDF has no letter codes and no functions, only number, name and a map
grid, so this is a classification and nothing more.

The PDF is parsed from its raw content streams with the standard library, which
is enough because the text is stored as plain strings. If the university
re-exports it with different encoding this will find nothing and say so, rather
than write an empty file.

Usage:  python3 scripts/build_umd_directory.py
"""

import json
import re
import sys
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "data" / "umd" / "directory.json"
CACHE = ROOT / "data" / "umd" / ".cache" / "campus-map.pdf"

PDF_URL = "https://umdconf.umd.edu/drupal/current_map.pdf"
SECTIONS = [("places", "KEY PLACES OF INTEREST"),
            ("university", "UNIVERSITY BUILDINGS"),
            ("housing", "CAMPUS HOUSING")]
# The entries a successful parse should roughly find, as a tripwire. The
# printed directory held 32, 125 and 53 on 2026-10-19.
EXPECT = {"places": 20, "university": 90, "housing": 35}


def pdf_text(raw):
    """Concatenate every string shown by a Tj/TJ operator, in stream order."""
    shown = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            body = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        shown += re.findall(rb"\((?:\\.|[^()\\])*\)\s*Tj|\[(?:[^\]])*\]\s*TJ", body)
    joined = b" ".join(shown).decode("latin-1")
    text = "".join(c[1:-1] for c in re.findall(r"\((?:\\.|[^()\\])*\)", joined))
    return text.replace("\\(", "(").replace("\\)", ")")


def entries(section_text):
    """'024   ALLEGANY HALL E12008   ANNAPOLIS HALL E12…' -> [(number, name)].

    The number comes BEFORE the name, and the next entry's number follows the
    map grid reference with no separator ('E12' then '008'), so entries are cut
    at 'three digits followed by two or more spaces' and the grid reference is
    stripped from the end of what is left.
    """
    marks = list(re.finditer(r"(\d{3}(?:-\d{3})?|N/A)\s{2,}", section_text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(section_text)
        name = section_text[m.end():end].strip()
        # Cut at the FIRST map grid reference, not the last: the final entry of
        # the final section runs on into the map's legend and footer, and the
        # last grid token in that is nowhere near the building.
        name = re.split(r"\s+[A-Z]{1,2}\d{1,2}(?=\s|$)", name)[0]
        name = re.sub(r"\s+(GREENMEAD DR|METZEROTT RD|INSET)\b.*$", "", name)
        # Octal escapes survive from the PDF string encoding: \222 is the
        # right single quote in Windows-1252, which is how "Queen Anne's" is set.
        name = re.sub(r"\\(\d{3})", lambda mo: bytes([int(mo.group(1), 8)]).decode("cp1252"), name)
        out.append((m.group(1), re.sub(r"\s+", " ", name).strip()))
    return out


def main():
    if CACHE.exists():
        raw = CACHE.read_bytes()
    else:
        req = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0 (campusquiet.com directory build)"})
        raw = urllib.request.urlopen(req, timeout=90).read()
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_bytes(raw)

    text = pdf_text(raw)
    marks = []
    for key, heading in SECTIONS:
        i = text.find(heading)
        if i < 0:
            print(f"section {heading!r} not found — the PDF layout changed", file=sys.stderr)
            return 1
        marks.append((key, i))
    marks.sort(key=lambda kv: kv[1])

    # The housing list is the last thing printed, and the map's legend follows
    # it in the same text stream: first "Adele H. Stamp Student Union" as a
    # callout, then street names, parking notes and a URL. Left in, the Stamp
    # callout read as the last residence hall and the legend produced a junk
    # entry. The callout is the marker, since nothing in the real list matches.
    legend = text.find("STAMP STUDENT UNION D9")
    if legend > 0:
        # The number comes BEFORE the name, so the callout's own number ("163")
        # sits just ahead of the marker and has to go with it.
        text = re.sub(r"\d{3}\s*$", "", text[:legend])

    directory, counts = {}, {}
    for n, (key, start) in enumerate(marks):
        end = marks[n + 1][1] if n + 1 < len(marks) else len(text)
        found = entries(text[start:end])
        counts[key] = len(found)
        for num, name in found:
            # A range ('987-994' Courtyards) is several buildings under one
            # name; it is stored under the range as printed and expanded by
            # whoever needs a single number.
            directory.setdefault(num, {"name": name, "section": key})

    # Tripwires, in both directions: too few entries means the layout changed,
    # and the Stamp union showing up as housing means the legend cut moved.
    if directory.get("163", {}).get("section") == "housing":
        print("Stamp Student Union parsed as housing — the legend cut is wrong", file=sys.stderr)
        return 1
    short = {k: (counts.get(k, 0), v) for k, v in EXPECT.items() if counts.get(k, 0) < v}
    if short:
        print(f"parse looks wrong (found, expected at least): {short}", file=sys.stderr)
        return 1

    OUT_FILE.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "University of Maryland campus map — building directory",
        "sourceUrl": PDF_URL,
        "note": "number -> {name, section}. section is the printed heading: "
                "places (key places of interest), university (academic, "
                "administrative, research, service) or housing (residence halls).",
        "buildings": dict(sorted(directory.items())),
    }, indent=1) + "\n")
    print(f"{counts} -> {OUT_FILE.relative_to(ROOT)} ({len(directory)} numbers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
