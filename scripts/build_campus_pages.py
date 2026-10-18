#!/usr/bin/env python3
"""
Write a static page per campus from index.html.

Reddit, iMessage and Snapchat build their link preview from the raw HTML and
never run the JavaScript, so a page that swaps its own title at runtime shares
as whatever the file says — a link to the Ohio State map would have previewed
as "UIUC Spaces" over a picture of Illinois. Each campus therefore needs a real
file with its own title, description, canonical and preview image.

index.html stays the Illinois page and the source of truth. Everything else is
generated from it, so the layout, styles and script only ever exist once.

Usage:  python3 scripts/build_campus_pages.py
"""

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://campusquiet.com"

CAMPUSES = {
    "osu": {
        "out": "osu.html",
        "path": "/osu",
        "title": "Ohio State Spaces",
        "university": "The Ohio State University",
        "short": "Ohio State",
        "description": ("A live 3D map of how busy Ohio State campus buildings are right now — "
                        "Thompson Library, the 18th Avenue Library, the Ohio Union and more — "
                        "built from class schedules and official building hours."),
        "og_description": "A live 3D map of how busy Ohio State campus buildings are right now.",
        # Set this once a screenshot of the Ohio State map exists. Until then the
        # card shares without an image, which is better than sharing Illinois'.
        "preview": "osu-preview.png",
        "data_dir": "data/osu",
        "blurb": ("A live 3D map of how busy study spaces are around The Ohio State University "
                  "campus in Columbus — libraries, the Ohio Union and academic buildings — so you "
                  "can see how busy a spot is before walking over. Busyness comes from class "
                  "schedules and official building hours."),
    },
}


def building_list(data_dir):
    """Every building the campus has data for, for the no-JavaScript fallback."""
    names = set()
    for f in ("class_activity.json", "building_hours.json"):
        p = ROOT / data_dir / f
        if p.exists():
            names |= set(json.loads(p.read_text())["buildings"])
    return sorted(names)


def render(html, c):
    out = html

    # --- head: everything that names Illinois ---
    out = out.replace("<title>UIUC Spaces</title>", f"<title>{c['title']}</title>", 1)
    out = re.sub(r'<meta name="description" content="[^"]*">',
                 f'<meta name="description" content="{c["description"]}">', out, count=1)
    out = re.sub(r'<link rel="canonical" href="[^"]*">',
                 f'<link rel="canonical" href="{SITE}{c["path"]}">', out, count=1)
    for prop, val in (("og:site_name", c["title"]), ("og:title", c["title"]),
                      ("og:description", c["og_description"]), ("og:url", f"{SITE}{c['path']}")):
        out = re.sub(rf'<meta property="{prop}" content="[^"]*">',
                     f'<meta property="{prop}" content="{val}">', out, count=1)
    for name, val in (("twitter:title", c["title"]), ("twitter:description", c["og_description"])):
        out = re.sub(rf'<meta name="{name}" content="[^"]*">',
                     f'<meta name="{name}" content="{val}">', out, count=1)

    # A preview card with the wrong campus' photo is worse than one with none.
    if c["preview"]:
        out = re.sub(r'(<meta property="og:image" content=")[^"]*(")', rf'\1{SITE}/{c["preview"]}\2', out, count=1)
        out = re.sub(r'(<meta name="twitter:image" content=")[^"]*(")', rf'\1{SITE}/{c["preview"]}\2', out, count=1)
        out = re.sub(r'(<meta property="og:image:alt" content=")[^"]*(")',
                     rf'\1A 3D map of the {c["short"]} campus with buildings shaded green to red by how busy they are.\2',
                     out, count=1)
    else:
        out = re.sub(r'\s*<meta (?:property="og:image(?::\w+)?"|name="twitter:image") content="[^"]*">', "", out)
        out = out.replace('<meta name="twitter:card" content="summary_large_image">',
                          '<meta name="twitter:card" content="summary">', 1)

    # --- structured data ---
    out = re.sub(r'("name":\s*)"UIUC Spaces"', rf'\1"{c["title"]}"', out, count=1)
    out = re.sub(r'("url":\s*)"[^"]*"', rf'\1"{SITE}{c["path"]}"', out, count=1)
    out = re.sub(r'("description":\s*)"A live 3D map of how busy study spaces[^"]*"',
                 rf'\1"{c["og_description"]}"', out, count=1)
    out = re.sub(r'("image":\s*)"[^"]*",?\n', "" if not c["preview"] else rf'\1"{SITE}/{c["preview"]}",\n', out, count=1)
    out = re.sub(r'("about":\s*\{ "@type": "CollegeOrUniversity", "name": )"[^"]*"',
                 rf'\1"{c["university"]}"', out, count=1)

    # Any remaining "UIUC Spaces" in the structured data (isPartOf names the
    # parent site, and naming it after Illinois on an Ohio State page is wrong).
    out = out.replace('"UIUC Spaces"', f'"{c["title"]}"')

    # --- the visible header, which app.js also rewrites at runtime ---
    # It has to be right in the file too: a crawler reads this and never runs
    # the script, and so does anyone whose JavaScript fails.
    out = out.replace("<h1>UIUC Spaces</h1>", f"<h1>{c['title']}</h1>", 1)
    out = re.sub(r'(<div class="sub" id="header-sub">)[^<]*(</div>)',
                 rf'\1{c["university"]}\2', out, count=1)
    out = out.replace("not affiliated with the University of Illinois",
                      f"not affiliated with {c['university']}")
    out = out.replace("Not affiliated with the University of Illinois",
                      f"Not affiliated with {c['university']}")

    # --- tell app.js which campus this file is, so no query string is needed ---
    out = out.replace('<html lang="en">', f'<html lang="en" data-campus="{c["id"]}">', 1)

    # --- the no-JavaScript fallback, which is the only text a crawler reads ---
    names = building_list(c["data_dir"])
    items = "\n".join(f"      <li>{n}</li>" for n in names)
    block = re.search(r'<div id="no-js">.*?</div>\s*</noscript>', out, re.S)
    if block:
        new_block = f"""<div id="no-js">
    <h2>{c['title']}</h2>
    <p>
      {c['blurb']}
    </p>
    <p>
      If you are working out where to study right now, it shows which buildings
      are open now, which are quiet and which are packed, and what time each one
      closes tonight.
    </p>
    <p>The map needs JavaScript to draw. It covers these {len(names)} buildings:</p>
    <ul>
{items}
    </ul>
    <p>A student project · not affiliated with {c['university']}.</p>
  </div>
</noscript>"""
        out = out[:block.start()] + new_block + out[block.end():]

    # The redirect in index.html is for the old Illinois address only.
    out = re.sub(r"<script>\n// The site moved to campusquiet\.com\..*?\n</script>\n", "", out, count=1, flags=re.S)
    return out


def main():
    html = (ROOT / "index.html").read_text()
    for cid, c in CAMPUSES.items():
        c = {**c, "id": cid}
        page = render(html, c)
        (ROOT / c["out"]).write_text(page)
        n = len(building_list(c["data_dir"]))
        img = c["preview"] or "none (shares without an image)"
        print(f"  {c['out']:<12} title={c['title']!r:<24} canonical={SITE}{c['path']:<8} buildings={n:<4} preview={img}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
