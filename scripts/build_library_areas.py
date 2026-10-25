#!/usr/bin/env python3
"""Build data/<campus>/library_spaces.json for Illinois and Maryland: walk-in study areas with the
libraries' OWN noise rating, in the shape U of T's file already has (build_utsg_library_spaces.py).

  python3 scripts/build_library_areas.py umd    -> data/umd/library_spaces.json
  python3 scripts/build_library_areas.py uiuc   -> data/library_spaces.json

Sources, both official and structured (no words fished out of prose):
- Maryland: lib.umd.edu/visit/libraries/<library>/<space>. Each page states "Noise Level"
  (Silent / Quiet / Collaborative), "Features" (Electrical Outlets, First Come First Served) and
  "Activities". Kept: first-come-first-served spaces whose activities include study. Bookable rooms
  are left to LibCal (study_rooms.json).
- Illinois: library.illinois.edu/using-library-spaces/study-space-directory/. Each page states
  "Volume: Level N" on the Library's own four-step scale (1 talking discouraged, 2 conversational
  buzz, 3 group work, 4 events/presentations) and its seating. No outlet field is published.

Re-run once a term.
"""
import html, json, re, sys, time, urllib.request
from datetime import datetime, timezone

UA = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36',
      'Accept': 'text/html,application/xhtml+xml', 'Accept-Language': 'en-US,en;q=0.9'}


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode('utf-8', 'ignore')


def text(page):
    t = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', page, flags=re.S)
    t = html.unescape(re.sub(r'<[^>]+>', ' | ', t))
    return re.sub(r'(\|\s*)+', '| ', re.sub(r'\s+', ' ', t))


# ── Maryland ────────────────────────────────────────────────────────────────────
# Library slug in the URL -> the map's building name (Testudo's, which the class data joins on).
UMD_BUILDINGS = {
    'mckeldin': ('McKeldin Library', 'McKeldin Library'),
    'stem': ('STEM Library', 'William E. Kirwan Hall'),
    'hornbake': ('Hornbake Library', 'Undergraduate Library'),
    'art': ('Art Library', 'Parren J. Mitchell Art-Sociology Bldg.'),
    'mspal': ('Michelle Smith Performing Arts Library', 'Clarice Smith Performing Arts Center'),
}


def umd():
    base = 'https://www.lib.umd.edu'
    urls = []
    for loc in re.findall(r'<loc>([^<]+)</loc>', get(f'{base}/sitemap.xml')):
        urls += re.findall(r'<loc>([^<]+)</loc>', get(loc)) if loc.endswith('.xml') else [loc]
    urls = sorted({u for u in urls if re.search(r'/visit/libraries/[^/]+/.', u)})
    spaces = {}
    for u in urls:
        lib = u.split('/visit/libraries/')[1].split('/')[0]
        if lib not in UMD_BUILDINGS:
            continue
        page = get(u)
        x = text(page)
        noise = re.search(r'Noise Level \| (Silent|Quiet|Collaborative)', x)
        if not noise:
            continue
        feats = (re.search(r'\| Features \| (.*?)\| Noise Level', x) or [None, ''])[1]
        acts = (re.search(r'\| Activities \| (.*?)\| (?:Capacity|Features)', x) or [None, ''])[1]
        if 'First Come First Served' not in feats or not re.search(r'(Individual|Group) Study', acts):
            continue   # bookable, or not for studying (lactation, reflection, events)
        name = html.unescape(re.sub(r'<[^>]+>', '', (re.search(r'<h1[^>]*>(.*?)</h1>', page, re.S) or [None, ''])[1])).strip()
        loc = (re.search(r'\| Location \| (.*?)\| Find it on', x) or [None, ''])[1]
        cap = re.search(r'\| Capacity \| (\d+)', x)
        lib_name, building = UMD_BUILDINGS[lib]
        spaces[u.split('/visit/libraries/')[1].strip('/').replace('/', '-')] = {
            'name': name, 'noise': noise.group(1),
            'features': ['Power Available'] if 'Electrical Outlets' in feats else [],
            'floors': re.findall(r'(\d+\w\w|Ground) Floor', loc),
            'capacity': int(cap.group(1)) if cap else None,
            'library_name': lib_name, 'building': building, 'url': u, 'area': True}
        time.sleep(0.15)
    return 'data/umd', 'University of Maryland Libraries space pages (lib.umd.edu/visit/libraries/...)', spaces


# ── Illinois ────────────────────────────────────────────────────────────────────
# Page title prefix -> the map's building name. A space whose title matches none (Oak Street,
# the off-campus storage facility) is left out rather than placed by guess.
UIUC_BUILDINGS = [
    (r'^Grainger', 'Grainger Engineering Library'),
    (r'^Main Library|^History, Philosophy|^HPNL|^International (and|&) Area|^Map Library|^The Orange Room', 'Main Library'),
    (r'^Funk', 'Funk Library'),
    (r'^Communications Library', 'Gregory Hall'),
    (r'^Music (and|&) Performing Arts|^MPAL', 'Music Building'),   # page: "W. Oregon St. side of the Music Building"
]


def uiuc():
    base = 'https://www.library.illinois.edu/using-library-spaces/study-space-directory/'
    urls = sorted(set(re.findall(r'href="(' + re.escape(base) + r'[^"#]+)"', get(base))))
    spaces = {}
    for u in urls:
        page = get(u)
        x = text(page)
        level = re.search(r'\| Volume \| Level (\d)', x)
        title = html.unescape((re.search(r'<title>(.*?)</title>', page, re.S) or [None, ''])[1]).split(' | ')[0].strip()
        where = (re.search(r'\| Closest Accessible Entrance / Exit \| (.*?)\|', x) or [None, ''])[1].strip()
        building = next((b for pat, b in UIUC_BUILDINGS if re.search(pat, title)), None)
        print(f'  {title!r:70} level={level and level.group(1)} -> {building}   [{where[:60]}]')
        if not level or not building:
            continue
        seats = re.search(r'\| Seating \| (\d+)', x)
        spaces[u.rstrip('/').rsplit('/', 1)[1]] = {
            'name': re.sub(r'\s+', ' ', title), 'noise': f'Level {level.group(1)}', 'features': [],
            'capacity': int(seats.group(1)) if seats else None,
            'library_name': title.split(' – ')[0], 'building': building, 'url': u, 'area': True}
        time.sleep(0.15)
    return 'data', 'University Library Study Spaces Directory (library.illinois.edu/using-library-spaces/study-space-directory/)', spaces


if __name__ == '__main__':
    campus = sys.argv[1] if len(sys.argv) > 1 else ''
    if campus not in ('umd', 'uiuc'):
        sys.exit('usage: build_library_areas.py umd|uiuc')
    out_dir, source, spaces = {'umd': umd, 'uiuc': uiuc}[campus]()
    with open(f'{out_dir}/library_spaces.json', 'w') as f:
        json.dump({'built_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'source': source,
                   'spaces': spaces}, f, indent=1)
        f.write('\n')
    print(f'{len(spaces)} areas -> {out_dir}/library_spaces.json')
