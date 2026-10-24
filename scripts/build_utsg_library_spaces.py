#!/usr/bin/env python3
"""
Build data/utsg/library_spaces.json: every St. George library study space the University of
Toronto Libraries publish, with its noise level (Silent / Quiet / Collaborative) and amenities,
read from each space's own page on library.utoronto.ca (/space/<library>/<space>). The space
pages are found from each library's page. A space is attached to a map building through its
library, using the same library -> building links as the hours and rooms work (an address on the
library's own page that matches the map, or the map's own record naming the library).

Usage:  python3 scripts/build_utsg_library_spaces.py   (once a term)
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "utsg" / "library_spaces.json"
SITE = "https://library.utoronto.ca"

# library page slug -> building on the map
LIBRARIES = {
    "robarts": "Robarts Library", "gerstein": "Sigmund Samuel Library Building",
    "kelly": "John M. Kelly Library", "engineering": "Sandford Fleming Building",
    "chemistry": "Lash Miller Chemical Laboratories", "math": "Bahen Centre for Information Technology",
    "physics": "McLennan Physical Laboratories", "music": "Edward Johnson Building",
    "oise": "Ontario Institute for Studies in Education", "uc": "University College",
    "architecture": "Daniels Building", "rotman": "Rotman School of Management",
    "art": "Sidney Smith Hall", "innis": "Innis College", "emmanuel": "Emmanuel College",
    "ivey": "Wilson Hall", "trinity": "Trinity College & Residence", "ej-pratt": "E.J. Pratt Library",
}
# Library name as a space page prints it ("More information > Library") -> map building.
LIBRARY_NAMES = {
    "Robarts Library": "Robarts Library",
    "Gerstein Science Information Centre": "Sigmund Samuel Library Building",
    "St. Michael's College - John M. Kelly Library": "John M. Kelly Library",
    "St. Michael\u2019s College - John M. Kelly Library": "John M. Kelly Library",
    "Engineering & Computer Science Library": "Sandford Fleming Building",
    "Chemistry Library (A D Allen)": "Lash Miller Chemical Laboratories",
    "Mathematical Sciences Library": "Bahen Centre for Information Technology",
    "Physics Library": "McLennan Physical Laboratories",
    "Music Library": "Edward Johnson Building",
    "OISE Library": "Ontario Institute for Studies in Education",
    "University College Library": "University College",
    "Architecture, Landscape, and Design (Eberhard Zeidler Library)": "Daniels Building",
    "Business (Milt Harris Library, Rotman School of Management)": "Rotman School of Management",
    "Department of Art Library": "Sidney Smith Hall",
    "Innis College Library": "Innis College",
    "Victoria University - Emmanuel College Library": "Emmanuel College",
    "New College Library (Ivey)": "Wilson Hall",
    "Trinity College Library (John W Graham Library)": "Trinity College & Residence",
    "Victoria University - E J Pratt Library": "E.J. Pratt Library",
    "Map & Data Library": "Robarts Library",
    "East Asian Library (Cheng Yu Tung)": "Robarts Library",
    "Thomas Fisher Rare Book Library": "Robarts Library",
}

# Spaces that are their own building on this map, not part of their library's building.
SPACE_BUILDING = {"/space/robarts/robarts-common": "Robarts Common"}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (campusquiet.com)"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf8", "replace")


def text(html):
    html = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return [unescape(x).strip() for x in re.sub(r"<[^>]+>", "\n", html).split("\n") if x.strip()]


def parse_space(url):
    html = get(SITE + url)
    title = (re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S) or [None, ""])[1]
    title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
    toks = text(html)
    library = toks[toks.index("Library", toks.index("More information")) + 1] if "More information" in toks else None
    feats = []
    if "Space features" in toks:
        for t in toks[toks.index("Space features") + 1:]:
            if t in ("Noise Level", "Copy, Print, Scan", "More information"):
                break
            feats.append(t)
    noise = None
    if "Noise Level" in toks:
        nxt = toks[toks.index("Noise Level") + 1]
        noise = nxt if nxt in ("Silent", "Quiet", "Collaborative") else None
    # Amenities are the short labels in the block before "Noise Level" (Print, Scan, Power, ...).
    amen = []
    for k in ("Power", "Print", "Scan", "Computers", "Wi-Fi", "Wifi", "Whiteboard", "Food and drink",
              "Accessible", "Natural light", "Lockers", "Water fountain", "Microwave"):
        if any(t.lower() == k.lower() for t in toks):
            amen.append(k)
    return {"name": title, "noise": noise, "features": feats, "library_name": library}


def main():
    sitemap = get(f"{SITE}/sitemap.xml")
    urls = sorted(set(u.replace(SITE, "") for u in re.findall(r"<loc>([^<]*/space/[^<]+)</loc>", sitemap)))
    print(f"{len(urls)} space pages in the sitemap")
    spaces, skipped = {}, {}
    for url in urls:
        try:
            rec = parse_space(url)
        except Exception as e:                                  # noqa: BLE001
            print(f"!! {url}: {e}", file=sys.stderr); continue
        building = SPACE_BUILDING.get(url) or LIBRARY_NAMES.get(rec["library_name"] or "")
        if not building:
            skipped[rec["library_name"]] = skipped.get(rec["library_name"], 0) + 1
            continue
        rec.update(building=building, url=SITE + url)
        spaces[url] = rec
        time.sleep(0.12)
    print("not on this map (library -> spaces):", skipped)
    # Open study areas only: the places a student can walk in and sit. Bookable rooms are
    # already in study_rooms.json; prayer/reflection rooms, staff workrooms, teaching labs,
    # consultation rooms and assigned carrels are not somewhere to drop in and study.
    NOT_AN_AREA = re.compile(r"workroom|reflection|classroom|consultation|instruction lab|madlab|"
                             r"technology lab|teaching and learning|family|carrel|bookable|group study room|"
                             r"study rooms|floor plans|history of|recording|theatre|screening|^b\d", re.I)
    for rec in spaces.values():
        rec["area"] = bool(rec["noise"]) and not NOT_AN_AREA.search(rec["name"])
    print("open study areas:", sum(1 for r in spaces.values() if r["area"]))
    OUT.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "University of Toronto Libraries space pages (library.utoronto.ca/space/...)",
        "spaces": spaces}, indent=1, ensure_ascii=False) + "\n")
    n = sum(1 for s in spaces.values() if s["noise"])
    print(f"{len(spaces)} spaces, {n} with a noise level -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
