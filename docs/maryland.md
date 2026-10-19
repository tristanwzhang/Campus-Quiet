# Adding Maryland

A layout for a third campus: the University of Maryland, College Park, at
`/umd`. Written 2026-10-16. Every source below was called live that day; where I
could not reach something, it says so rather than assuming it works.

Nothing here is committed or pushed — expansion work waits to be asked for.

## What the code already does for you

Ohio State paid for the abstraction, so a campus is now mostly data. The edits:

| Where | What |
|---|---|
| `app.js` → `CAMPUS_SITES` | one entry: title, timezone, data dir, area, centre, camera, ground height |
| `app.js` → `BUILDINGS_UMD`, `STUDY_SPOTS_UMD`, `PICK_LABELS_UMD`, `GIS_ALIASES_UMD`, `ACADEMIC_CALENDAR_UMD` | campus content, plus one row in `CAMPUS_CONTENT` |
| `scripts/build_basemap.py` → `CAMPUSES` | one bbox, then `--campus umd` |
| `scripts/build_campus_pages.py` → `CAMPUSES` | one entry; it generates `umd.html` |
| `.github/workflows/weekly-hours.yml` | one `continue-on-error` step |
| new: `scripts/build_umd_buildings.py`, `build_umd_class_estimates.py`, `build_umd_hours.py` | the three data builders |

Nothing in the map, the estimates, the panel or the picks needs touching.
`data/umd/` needs the same four files Columbus has: `buildings.json`,
`class_activity.json`, `building_hours.json`, `basemap.json`.

Also: add `/umd` to `sitemap.xml` only when it launches (Ohio State is
deliberately absent until 26 Oct), and bump `app.js?v=NN` in every page.

## Sources, all verified on 2026-10-16

### Classes — Testudo, official, no key

The Schedule of Classes serves sections as HTML:

```
https://app.testudo.umd.edu/soc/202608                      → 207 department codes
https://app.testudo.umd.edu/soc/202608/CMSC                 → course ids in a department
https://app.testudo.umd.edu/soc/202608/sections?courseIds=A,B,C   → the meetings
```

Each meeting carries `section-days`, `class-start-time`, `class-end-time`,
`building-code` and `class-room`, which is everything
`build_class_estimates.py` needs. `202608` is Fall 2026; the term dropdown
publishes its own codes, so read them rather than deriving them — note the page
*defaults to Spring 2027* already, so a scraper that takes the selected option
will build the wrong term.

Batching works: `courseIds` took 25–40 ids in one request in testing.
`scripts/build_umd_class_estimates.py` now does all of this; the notes below are
what writing it turned up.

**Testudo is slow and erratic, and that — not politeness — sets the pace.** A
department page takes **20 seconds every time** (measured repeatedly), so 207 of
them is over an hour before a single section is read. And roughly **one request
in three simply hangs**, whatever the URL: `/soc/buildings/ESJ 2212` answered in
0.13 s, then timed out at 20 s, then answered in 0.15 s, back to back. This is
the same shape as `recsports.osu.edu` on the Columbus side — "answers in under a
second or not at all" — and it takes the same fix: a *short* timeout and another
try, because a slow response is a hang rather than work in progress. The builder
gives department and section pages 60 s (they really are that slow) and building
lookups 15 s, with separate cool-offs. Everything is cached, so a rerun resumes.

The cold sweep took **5h20m** (02:42 to 08:03, 207 departments), so plan it as
an overnight job. A rerun from cache takes seconds, which is what `--offline`
and the cached failures are for — every change to the weighting or the output
shape can be tested without touching Testudo again.

**The full sweep has run.** 207 departments, 4,708 courses, **9,434 meetings**
in **63 buildings**, no parse failures worth the name (16 unreadable day/time
rows out of 13,003). 3,553 rows carry no room — online and arranged meetings,
which drop out on their own. 4,788 room-hours were already taken by another
section and counted once, which is the cross-listing de-duplication both other
campuses do.

The class-load distribution lands almost exactly on Illinois', which matters
because `CLASS_COVERAGE_MIN` and the picks cutoff are tuned against the campus
median:

| | buildings | peak max | **median peak** |
|---|---|---|---|
| Illinois | 68 | 143.5 | 28.5 |
| **Maryland** | **63** | **156.0** | **27.0** |
| Ohio State | 101 | 178.5 | 16.0 |

Busiest: Van Munching 156, Jimenez 145.5, Tawes 145, Edward St. John 98,
Plant Sciences 88.5.

### The 12 codes that did not resolve, and why

The two failure modes mean opposite things, so the builder now prints them
apart:

- **HTTP 404 — `4MLK BA BLD2 BLD3 BLD4 BSE4 DC`.** The College Park lookup has
  never heard of these. They are the off-campus teaching centres — Shady Grove's
  Building II/III/IV and BSE, the DC centre. This is the Wooster case and they
  are correctly dropped. Filtering on `teachingCenter` turned out to be
  unnecessary: the register answers the question on its own.
- **HTTP 500 — `BMS HIL PWS SEN`.** Testudo *knows* these codes and errors on
  them. Measured 3/3 on `BMS 3118`, so it is a server-side gap, not a hiccup.
  **These are real buildings being lost**, and each has only one room in the
  whole term's data, so there is no second room to try.
- **`TBA`** arrives with an empty room and is named as not-a-place.

The likely identities, from the official printed directory — **candidates to
confirm, deliberately not written into the code**, because an inferred code
expansion is exactly the kind of guess that puts a building in the wrong place:
`BMS` → 296 Biomolecular Sciences Building, `SEN` → 812 Seneca Building,
`PWS` → 111 Physics Welding Shop, `HIL` → Rosenbloom Hillel Center (which the
map lists under places of interest with **no building number at all**, so it has
no state-GIS footprint either). Until someone confirms these, they stay out and
the map shows nothing for them rather than something wrong.

**Testudo's name for a building is not always the one students use.** `HBK`
resolves to **"Undergraduate Library"**, where the Libraries' own pages and
every student call it Hornbake. This is the Columbus situation exactly ("Library,
Wm Oxley Thompson" vs Thompson Library), and it has the same two consequences:
the hours file and the class file must join on the **code**, never the name, and
the friendly name belongs in `BUILDINGS_UMD` as a `label` rather than being
renamed in either data file.

Two more parsing facts worth keeping:

- A course in the catalog with **no sections this term** comes back as an empty
  `<div>` — verified by asking for `AAAS399` alone, which returns 21 bytes and
  no container. The dept page gives every course the same "show sections"
  toggle, so there is no way to know in advance. This is ordinary and must be
  counted, not flagged, or the script cries wolf on every run.
- `delivery-f2f`, `delivery-online` and `delivery-blended` appear as classes on
  the section div. Online meetings carry no room, so they drop out on their own
  — no need to filter on the mode.

Section seat counts come from the same pages, so the `seats` signal Columbus has
is available here too. It is the *section* cap, not the room capacity Ohio State
publishes — close enough to be worth recording, different enough to say so in
the file's `note`.

**No off-campus filter turned out to be needed.** `teachingCenter` has 15 values
(College Park, Shady Grove, Hagerstown, DC, Frostburg…) and the plan was to
filter on it, Wooster-style. In the event every off-campus building code 404s in
the building lookup, so they drop out on the university's own answer — a better
guard than a facet, because it cannot be fooled by a centre that shares a
building code with College Park.

`api.umd.io` mirrors all of this as clean JSON (`/v1/courses/sections?course_id=…`,
verified working) and is much easier to parse. It is a student project, not the
university, so it is fine for exploring and wrong for shipping — the same reason
this map reads Course Explorer rather than a mirror.

### The register — code → name → number → footprint, all official

This is the piece that was hard on Columbus, and Maryland hands it over.
Testudo has an endpoint behind the room links in its own JavaScript
(`soc.js:199`):

```
https://app.testudo.umd.edu/soc/buildings/KEY%200106
```

which returns, in labelled fields:

```
Francis Scott Key Hall      Bldg Code: KEY      Bldg Number: 048
```

Verified on SQH→233 Susquehanna Hall, MCK→035 McKeldin Library,
KEY→048 Francis Scott Key Hall, IRB→432 Brendan Iribe Center and
ASY→146 Parren J. Mitchell Art-Sociology Bldg. The numbers match the
university's own printed building directory
(`https://umdconf.umd.edu/drupal/current_map.pdf`, which lists Bldg# and name
but no letter codes), so the chain is confirmed twice from different official
publications.

It also settles what is *not* a place, which a code list cannot: **`TBA`
resolves to "Meeting place to be arranged", building number `000`.** The builder
drops those on the university's own answer rather than on a hardcoded list — the
same reason Ohio State's builder requires digits after the code rather than
listing ONLINE and OFFCAMPUS by hand.

The room number is required (`/soc/buildings/ASY` alone 404s), and any real room
in that building works.

Footprints and coordinates then come from the state's GIS, which carries UMD's
building numbers as its key:

```
https://mdgeodata.md.gov/imap/rest/services/Structure/MD_CampusFacilities/FeatureServer/2
fields: BUILDINGID, NAME, polygon geometry      308 features
```

So `build_umd_buildings.py` is: sweep the codes the class data actually uses →
one Testudo lookup per code (cache them; the set changes once a term) → join to
MD iMAP on building number for name, outline and centroid. Everything official,
and the join key is the code the class data is already keyed by, which is
exactly what `gisFor()` wants. `GIS_ALIASES_UMD` should start empty and stay
empty unless a code genuinely fails.

`api.umd.io/v1/map/buildings` also publishes 108 code→number→lat/long rows and
is a useful cross-check (it agreed on every code I spot-checked), but one of its
421 rows is in Web Mercator rather than degrees — don't trust it unchecked.

### Hours — corrected 2026-10-19: weaker than Illinois, not weaker than Columbus

> **Correction.** This section originally said Maryland publishes no building
> hours and that Dining publishes none on the web. **Both were wrong**, and both
> were stated more firmly than the evidence supported. Dining's hours load a few
> seconds after the page does, from a public Google Sheet, so a first look (and
> a plain scrape) sees empty cells. And UMPD publishes a campus-wide rule for
> academic buildings that I never found because I was looking for a table. Both
> are now in `scripts/build_umd_hours.py`; see "Third pass" below.

Maryland has no per-building hours spreadsheet — nothing like Illinois'
Facilities file or Ohio State's registrar schedule — but it has one real
campus-wide rule and five real per-building sources.

What is real:

- **University Libraries, via LibCal, no key:**
  `https://umd.libcal.com/api_hours_grid.php?iid=0&format=json&weeks=8`
  Dated hours per day, and it answered for **8 weeks ahead** — far better than
  the 7-day windows on both existing campuses. Ten locations, six categorised
  `library`. Also carries a `note` field that names the reason
  ("Fall Break", "Terp Carnival"), which the panel can show.
  The parser must handle `"24hours"`, ranges that cross midnight
  (McKeldin read `12am–5pm` on one day and `24hours` on the next), and
  `status: "closed"` with no hours array.
- **Which libraries are buildings in their own right**, confirmed from the
  Libraries' own location pages rather than guessed:
  McKeldin (035, `MCK`) and Hornbake (147, `HBK`) are buildings; the STEM
  Library is *inside* William E. Kirwan Hall room 1403, the Art Library inside
  the Parren J. Mitchell Art-Sociology Building, the Architecture Library inside
  the Architecture Building, and the Michelle Smith Performing Arts Library
  inside The Clarice. Tenants' hours are not their building's hours — same call
  Columbus made.
- **Google listing hours** via the existing `fetch_google_hours.py` + the
  hand-entered table pattern, for the handful of buildings worth it.

### RecWell, Dining and Stamp — checked 2026-10-16

All three refused connections on the first attempt and answered fine later, so
that was their edge being flaky, not a block. Checked properly, they are three
different answers.

**Stamp: the best hours source on this campus, and not just for Stamp.**
`stamp.umd.edu/visit/hours_operation` publishes 14 HTML tables. The first is the
building itself, under a heading that states its own validity —
"Fall Semester 2026 Hours, August 27 through December 20":

    Monday through Thursday   7 a.m. to midnight
    Friday                    7 a.m. to 1:30 a.m.
    Saturday                  8 a.m. to 1:30 a.m.
    Sunday                    11 a.m. to midnight

Then **dated exception tables** for Labor Day, Fall Break, Thanksgiving and
Winter Break — Oct 12 closed, Nov 26–27 closed, Dec 25–Jan 3 closed. That is
the `periods` and `campusClosedDates` data Ohio State never got, from a
published source. It independently corroborates the Fall Break dates the LibCal
feed named.

Two caveats. Some cells are free text — "TBD (Based on home football start
time.)" — and must be skipped, not interpreted. And the page's own weekday
labels can be wrong: it says "Sunday, November 30", but Nov 30 2026 is a Monday.
Parse the date, ignore the weekday word.

**Stamp is not in the class data** (no classes meet there), so it has to be added
as a building in its own right, exactly as Illinois carries the Illini Union.
The state GIS has it: **Stamp Student Union, building 163**.

**RecWell: real hours, but not where the site says.**
`/facilities/todays-facility-hours` renders **empty** — no hours, and no API
call behind it either (checked in a browser with the network log open). Do not
use it. `/facility-hours` 403s. The hours live on the per-facility pages:

| Page | Shape |
|---|---|
| `/eppley-recreation-center-0` | facility × weekday-group, 4 term tabs |
| `/reckord-armory` | same, different day-header wording |
| `/outdoor-aquatic-center` | rows are **date ranges**, not facilities |
| `/natatorium` | tenant inside Eppley — excluded |
| `/ritchie-coliseum` | no tables; hours not published here |

The four tables per page are the four terms, and the labels are **not visible
text** — they are `data-title` attributes (`<div data-title="Fall Semester ">`),
which is why a naive text extraction sees four identical unlabelled tables and
cannot tell which applies today. A regex over the raw HTML reads them fine, so
no browser is needed in CI. Note the trailing spaces in those attributes.

Day headers are inconsistent across pages — "Monday to Friday", "Monday through
Friday", "MON though THURS" (their typo), "SAT and SUN" — so parse defensively
and report anything unrecognised rather than guessing. Cells carry parenthetical
caveats too ("limited availability beginning at 6pm when Intramural Sports
begin").

These are **term patterns, not dated**, so they need `followsCampusClosures` and
break `periods` the way Illinois' entries do. `/facility-alerts` does carry a
dated table (Eppley, Natatorium, Ritchie, Reckord, Outdoor Aquatic by exact
date) but it is **stale** — on 16 Oct it still showed 9–13 Oct, the Fall Break
window. It is an occasional-exceptions page, not a rolling feed, so it cannot
carry a weekly job.

Confirmed in the state GIS: Eppley **068**, Reckord Armory **078**, Ritchie
Coliseum **004**, Aquatic Center **399**.

**Dining: publishes dated hours** (corrected — this paragraph said it did not).
`dining.umd.edu/hours/open-now` shows every cell as "—" in the raw HTML and for
the first seconds after load, then fills them in from a public Google Sheet the
page's own script names (`const diningUrl = 'https://docs.google.com/
spreadsheets/d/<id>/gviz/tq?gid=…'`). That is why it was missed twice: a scrape
sees nothing, and a browser read taken immediately sees nothing. Network
monitoring did not show it either, because the calls go to `docs.google.com`.
One column per calendar day, 394 days, three meal rows per hall. Used for the
three halls that are buildings in their own right; the cafes in other buildings
are tenants and their hours are not the building's.

### What this does to the hours count

Superseded by the third pass below: 11 buildings now have a source of their own
(2 libraries, Stamp, Eppley, Reckord Armory, Ritchie, 3 dining halls, the Health
Center, the outdoor pool) and 43 academic buildings are covered by UMPD's
campus-wide rule.

### Academic calendar

Confirmed from the registrar's own Fall 2026 final-exam page: **exams run
Dec 14–21, 2026** (listed exam days: 14, 15, 16, 17, 18, 21).

The catalog's semester calendar
(`academiccatalog.umd.edu/about-university/academic-calendar/semester-calendar/`)
gives classes **Aug 31 – Dec 11** with a **reading day Dec 12**; I have that
from search results, not from reading the page — it refused my fetches — so
**read it once directly before typing it into `ACADEMIC_CALENDAR_UMD`.**

One bonus: the LibCal feed labelled **2026-10-11 and 10-12 "Fall Break"** in its
own `note` field, which is an official feed naming a break day. Confirm it
against the calendar page, then it belongs in `periods`. Thanksgiving and Labor
Day need the same treatment, and `campusClosedDates` should be populated from
the start — Columbus shipped with it empty and that is the known gap there.

## The config entry

Computed from the 108 code-carrying buildings in the cross-check register
(bbox W −76.9547, E −76.9262, S 38.9770, N 38.9936 — 2.5 km by 1.8 km, almost
exactly Columbus' footprint, so Columbus' camera is the right starting point):

```js
umd: {
  id: 'umd',
  title: 'Maryland Spaces',
  subtitle: 'University of Maryland — College Park',
  disclaimer: 'A student project · not affiliated with the University of Maryland',
  tz: 'America/New_York',
  dataDir: 'data/umd',
  // AREA clamps the camera, not its target: at -38°/1700 m the camera sits
  // 1339 m behind the target, which here is 0.0120° of latitude and 0.0155°
  // of longitude, so every side is padded by that much past the outermost
  // building. Recompute if the camera changes.
  area: { west: -76.971, south: 38.964, east: -76.910, north: 39.007 },
  center: { lon: -76.9428, lat: 38.9870, height: 220 },   // ≈ McKeldin Mall
  view: { pitchDeg: -38, range: 1700 },
  viewNarrow: { pitchDeg: -50, range: 1300 },
  groundM: /* SAMPLE IT */,
},
```

**Do not copy a `groundM`.** Illinois' 190 and Columbus' 196 are ellipsoid
heights sampled from Cesium's terrain at each campus centre; College Park is
near sea level and its value will be nothing like either. Sample it the same way
before shipping, or every label floats.

Redo `area` and `center` from `class_activity.json` once it exists — the 108
codes are a proxy for "buildings that host classes", not the thing itself. UMD
also has genuinely distant holdings (the observatory on Metzerott Road, the vet
centre on Greenmead Drive, the research park), which `offMap()` will drop on the
register's own coordinates, as it does for Wooster.

## What needs a Maryland student

Keep this thin and sourced, exactly as Columbus did. Sourced already, from the
Libraries' own pages:

```js
const STUDY_SPOTS_UMD = {
  'MCK': 1,      // McKeldin Library
  'HBK': 1,      // Hornbake Library
  // 0.75 — buildings that contain a library, hours not the library's:
  //   Kirwan Hall (STEM), Art-Sociology (Art), Architecture, The Clarice (MSPAL)
  // The union (Stamp) belongs at 0.75 too, once its hours are verified.
};
```

What a sourced list cannot say is which atrium people actually work in — the
part of Illinois' twelve that came from knowing the campus. Leave the picks card
showing nothing rather than guessing; a wrong pick puts someone in front of a
locked door. `PICK_LABELS_UMD` and the short-label entries in `BUILDINGS_UMD`
(Testudo's names are reasonable, so this may be nearly empty) are the same kind
of local knowledge.

## State as of 2026-10-19 — built, not public

Everything below is on the local `maryland` branch and **nothing is pushed**.
`/umd` does not exist on campusquiet.com, the sitemap is untouched, and the
campus picker has no Maryland card.

| Piece | State |
|---|---|
| `scripts/build_umd_class_estimates.py` | done — 207 departments, 4,708 courses, 9,434 meetings, 63 buildings |
| `data/umd/class_activity.json` | done |
| `data/umd/rooms.json` | done — 721 classrooms in 63 buildings, from the same sweep |
| `scripts/build_umd_buildings.py` | done — 308 footprints, 60 of 63 codes joined |
| `data/umd/buildings.json` | done |
| `scripts/build_umd_hours.py` | done — 5 buildings, 3 dated and 2 weekly |
| `data/umd/building_hours.json` | done |
| `data/umd/basemap.json` | done — 7,630 features |
| `app.js` config + content | done — `CAMPUS_SITES.umd`, `BUILDINGS_UMD`, `STUDY_SPOTS_UMD`, `PICK_LABELS_UMD`, `GIS_ALIASES_UMD`, `ACADEMIC_CALENDAR_UMD`, `CAMPUS_CONTENT` |
| `api/rooms.mjs` | done — 96 bookable rooms in 4 buildings, tested live |
| `umd.html` | generated, not served |
| CI hours step | done |
| `scripts/hours_accuracy.mjs` | knows `--campus umd` |
| Campus picker card + `logos/umd.png` | **not done, on purpose** |
| sitemap entry | **not done, on purpose** |
| preview image | not done — needs a screenshot of a map nobody can see yet |

### The launch checklist, when it is wanted

Three edits, all in files that are live, which is why they are not made:

1. `index.html` line 106 — a card beside the other two:
   `<a class="campus" href="/umd"><div class="logo"><img src="logos/umd.png" alt=""></div><div><b>Maryland</b><span>University of Maryland — College Park</span></div></a>`
2. `index.html` line 14 — add `umd` to the remembered-campus redirect, or a
   returning Maryland visitor keeps landing on the picker.
3. `sitemap.xml` — add `https://campusquiet.com/umd`.

`logos/umd.png` needs a decision rather than a download: the other two cards
carry each university's own mark, and whether to use Maryland's is a
trademark call for the owner of the site, not something to settle by fetching a
file.

### Measured accuracy, and the problem it exposes

> **Superseded.** These are the 2026-10-19 morning figures, before the campus
> rule and the new sources. The third pass below has the current ones, and
> explains why one of them must not be quoted.

`node scripts/hours_accuracy.mjs --campus umd`, week of 2026-10-19:

| | Illinois | Ohio State | **Maryland** |
|---|---|---|---|
| buildings | 74 | 93 | 61 |
| silent (no answer at all) | 0.4% | 18.3% | **34.0%** |
| claims from the class fallback | 1.0% | 32.3% | **87.6%** |
| fallback accuracy, measured | 85.7% | 90.9% | **43.8%** |
| scored slots behind that number | 2,608 | 2,040 | **112** |
| composite, of claims made | 93.1% | 92.5% | **50.1%** |
| composite, counting silence as wrong | 92.8% | 75.6% | **33.1%** |

**Do not quote the 43.8% as Maryland's accuracy.** The hold-out works by hiding
the hours of buildings that publish them and asking the fallback what it would
have guessed — and Maryland has only five such buildings, all of them the worst
possible case for a class-schedule proxy: a library open 24 hours with almost no
classes in it, a union, two gyms. 112 scored slots against Illinois' 2,608. The
number is real but it measures "the fallback is bad at libraries and gyms",
which was already known, on a sample too small and too biased to carry a
campus-wide claim.

What is *not* a measurement artifact is the row above it: **87.6% of Maryland's
claims come from the class timetable**, against 32% at Ohio State and 1% at
Illinois, and **a third of the time the map declines to answer at all**. Grant
the fallback Ohio State's measured 90.9% and the composite lands near 91%;
grant it the 43.8% and it lands at 50%. The honest position is that Maryland's
accuracy is unmeasurable from the inside until more buildings publish hours,
and that it is the thinnest of the three either way.

### Hours: what was ruled out (see the third pass for what was missed)

Checked and ruled out, so nobody repeats it:

- **Facilities Management** — publishes no building hours. (The rule that
  matters comes from UMPD Building Security Services instead; see below.)
- **The registrar** — no classroom-pool schedule, the thing that covers 47
  Columbus buildings.
- **25Live**, which the Provost's classroom search runs on — every
  `25live.collegenet.com/25live/data/umd/run/*` endpoint answers **HTTP 401**.
  Closed, like Ohio State's room-booking app. Do not retry.
- ~~**Dining** — nothing on the web~~ **WRONG, corrected:** Dining publishes
  dated hours via a public Google Sheet. See above.
- **Individual high-load buildings** — Van Munching, the busiest building on
  campus, publishes *break* hours as news announcements ("2026 Summer Hours")
  and no academic-year hours; the Smith Service Center hours on that site are an
  office inside it, not the building.

### A thing this campus has that the other two do not

The terrain is **not flat**. Sampled from Cesium at all 60 placed buildings:
median 3.4 m, running from **−12.8 m** (A. James Clark Hall) to **+20.7 m** (the
Education Building) — a 33 m spread, where Illinois varies by about 3 m. The
single `groundM` that both existing campuses rely on is therefore a compromise
here, and labels at the extremes sit up to ~17 m off their building. It is set
to the median and flagged in the config; per-building sampling is the real fix
if it ever reads badly on screen. Worth looking at before launch.


## 2026-10-19, second pass: accuracy

### A bug that blanked the whole map, found on this campus

`applyStyle()` built a Cesium 3D-Tiles style by quoting each building name into
a style expression and escaping apostrophes as `\'`. **Cesium's expression
parser does not understand backslash escapes**, so `'Queen Anne\'s Hall'` ends
at the apostrophe and throws *"Unclosed quote"* — which stopped Cesium
rendering altogether. One building name took the entire map down.

Illinois and Ohio State have no apostrophe in any building name, which is why
this survived two campuses. Maryland has four: Queen Ann's Hall (in the class
data), Queen Anne's Hall, Prince George's Hall and St. Mary's Hall.

Fixed in both `app.js` and `classic.js` by quoting with whichever character the
name does not contain, since Cesium accepts both. A name containing both is
unrepresentable and is now skipped — it loses its colour instead of taking the
map with it. Verified against all 332 Maryland names: every one parses, none
skipped.

### The fallback, measured and changed

Two changes, both measured with `scripts/hours_accuracy.mjs`, scoring every
slot with silence counted as wrong.

**1. Order of guards in `assumedStatus()` — a bug fix, on for every campus.**
The "nothing timetabled today" check ran before the "no classes meet today"
check, so during a recess two buildings could disagree about the same day: one
with a Saturday timetable read *closed*, one without read *silent*. The
campus-wide questions are now settled first. This improves the live campuses:

| Thanksgiving week | before | after |
|---|---|---|
| Illinois | 82.9% | **90.0%** |
| Ohio State | 69.6% | **72.6%** |
| Maryland | 40.9% | **65.1%** |

Unchanged on ordinary weeks for both live campuses.

**2. `assumeShutWithoutClasses` — a judgement call, on for Maryland only.**
Maryland timetables **no Saturday classes at all**, so the fallback said
nothing every weekend: 34% of all building-hours, against Ohio State's 18% and
Illinois' 0.4%. Reading "nothing timetabled here today" as *probably closed*
removes that silence. It can only ever be wrong in the safer direction — it
adds "said closed when open" and **never a single "said open when closed"**, so
it cannot send anyone to a locked door.

| week of 2026-10-19 | silent | assumed shut | new claims right |
|---|---|---|---|
| Illinois | 92.8% | 93.0% | 685/1144 (60%) |
| Ohio State | 75.6% | **90.2%** | 637/840 (76%) |
| Maryland | 33.1% | **51.6%** | 58/112 (52%) |

**Ohio State would gain 14.6 points from switching this on.** It is off there
because that map is live and this changes what it tells people — an owner's
decision, not a side effect of building a third campus.

**A negative result worth not re-deriving:** `assumedHours()` widens every
building to the campus-wide class window, which looks too aggressive — it is
why Reckord Armory, open from 3pm, reads open at 6am. Removing it was tested
and is **worse** everywhere (Illinois 92.8→92.7, Ohio State 75.6→74.0, Maryland
51.6→41.0). It does cut the dangerous error sharply (98→36 "open when closed"
on Illinois) at the cost of far more false closures. Keep the union.

### Break days, now from two published sources

`campusClosedDates` was three dates guessed from the academic calendar. It is
now the university's own staff holiday calendar
(`uhr.umd.edu/employee-resources/holiday-calendar`), read from the **observed**
column: 7 Sep, **12 Oct**, 26–27 Nov, 25 Dec, 28–31 Dec. Election Day is earned
on 3 November but observed in March 2027, and Veteran's Day and President's Day
are observed inside the December break — none of them closes anything this term.

12 October is the one that would have been got wrong: HR calls it "Indigenous
Peoples Day - Fall Break", and Stamp's own hours page independently prints that
Monday as *Closed* while showing the Tuesday open until 6pm. Two published
sources, agreeing.

`classesOutDates` is new: **13 Oct and 25 Nov**, the no-class days that are
*not* university holidays, so the offices are open and the fallback says
nothing rather than guessing shut. Derived by subtracting one published list
from the other.

### Sources checked and ruled out, second pass

- **OpenStreetMap `opening_hours`** — 111 tagged venues inside the campus box,
  every one a restaurant, café, pharmacy or charging station. The only match to
  a building we hold is Mowatt Lane Parking Garage (24/7). Not a source.
- **Occuspace** (`api.occuspace.io`) — 401. **Waitz** — 404 for Maryland,
  consistent with it being Purdue-only.
- The official app's busy meter for dining halls and rec centres has **no web
  surface at all**: no widget, no XHR, nothing on the RecWell or Dining pages.

## What is different from Columbus, in one list

- **Better:** the code→building join is fully official and complete; library
  hours come 8 weeks ahead instead of 7 days.
- **Worse than Illinois, comparable to Columbus:** no per-building hours
  document. What exists is one campus-wide rule (UMPD) that covers 43 academic
  buildings, which is a *general* statement rather than a schedule. Columbus has
  a registrar document covering 47 buildings in the same "generally" spirit.
- **New:** Testudo is HTML rather than JSON, hangs about a third of the time,
  and has a server-side gap that loses four real buildings.
- **Checked since:** RecWell publishes hours on its per-facility pages (not on
  its own "today's hours" page, which renders empty); Stamp publishes a weekly
  table plus dated break exceptions and is the best hours source on the campus;
  Dining DOES publish, as dated hours from a public sheet (an earlier version of
  this list said it did not).
- **Same trap:** off-campus teaching centres, like Wooster. Filter on the
  university's own field.


## 2026-10-19, third pass: labels, and what was missed

### Two corrections to things stated earlier

1. **Dining publishes hours.** See the Dining paragraph above. Dated, a year
   ahead, from a public Google Sheet the page itself reads.
2. **There *is* a campus-wide rule.** UMPD Building Security Services — the
   office that controls the locks ("Locking/unlocking is controlled by remote
   electronic programming") — states at
   `umpd.umd.edu/about-us/our-units/building-security-systems`:

   > Campus academic and administrative facilities are generally open to the
   > public from 7:00am to 9:00pm Monday through Friday during the academic
   > year. Unless specifically requested, these facilities are closed on
   > weekends and University holidays. Several student support facilities
   > (Recreation Center, Health Center, Libraries) maintain their own service
   > hours. [...] Regularly scheduled classes and exams [...] exterior doors to
   > the appropriate facilities will be unlocked during the scheduled period.

   I read this before relying on a search engine's summary of it. It is a
   *general* statement ("generally open"), not a per-building schedule, and the
   entries say so (`generalRule: true`, and the source name says "general
   academic building hours").

### What `build_umd_hours.py` now covers

| Source | Buildings | Shape |
|---|---|---|
| Libraries (LibCal) | McKeldin, Hornbake | dated, 10 weeks |
| Stamp | Stamp Student Union | weekly + dated break exceptions |
| RecWell | Eppley, Reckord Armory, **Ritchie Coliseum** | weekly, Fall tab |
| **Dining (public sheet)** | South Campus, 251 North (Denton), Yahentamitsi | **dated**, to 22 Jan 2027 |
| **Health Center** | University Health Center | weekly, Mon-Fri 8-5 |
| **RecWell, date ranges** | Aquatic Center (the outdoor pool) | `periods`; shut 11 Oct to 11 Dec |
| **UMPD rule** | **43 academic buildings** | Mon-Fri 7-21 plus each building's class windows |

That is **54 buildings with an hours entry, up from 5**. 11 of them have a
source of their own; 43 have the general rule.

**How the rule is applied, and what it deliberately leaves out.** The
university's own printed building directory (`scripts/build_umd_directory.py` →
`data/umd/directory.json`) files every building under "Key places of interest",
"University buildings" or "Campus housing". The rule is applied only to class
buildings in the second group. That excludes:

- **8 residence halls that host classes** (Anne Arundel, Centreville,
  Cumberland, Dorchester, LaPlata, Prince Frederick, Queen Ann's, Somerset) —
  without the directory they would read as academic buildings open to the public
  at 7am;
- the Clarice and the Golf Range Classroom (key places, own policies);
- 4 judged not to be general academic buildings (two housing community centres,
  Preinkert Field House, the Gudelsky Veterinary Center) and the Paint Branch
  Research Facility, which the directory does not list.

The Computer Science Instructional Center is the one inclusion that is not in
the directory (it opened after the directory was printed); it is plainly an
academic instruction building and is added by name with that reason.

The class windows come from `rooms.json` (exact start and end, so a 9:30 class
unlocks at 9:30, not at 9:00), because the rule says the doors unlock for "the
scheduled period".

**An inference to be aware of:** `Aquatic Center` (building 399) is taken to be
RecWell's *Outdoor* Aquatic Center. RecWell places that pool "on the west end of
Eppley Recreation Center" and the directory puts both in grid D7; there is no
other standalone aquatic building. That is reasoning, not confirmation. If it is
wrong, one building shows as closed for the rest of the term.

### Not claimed, on purpose

- **The Health Center's "limited evening services"** are by appointment only,
  so the building's public hours are 8 to 5.
- **Fall Break (12 October) at the Health Center** is left unknown: HR lists it
  as a university holiday but the Health Center never says it closes.
- **Administrative buildings with no classes** (Admissions / Mitchell Building,
  the Thomas V. Miller Jr. Administration Building) are covered by the rule in
  principle and are **not** lit up. With no class data and no busyness model,
  "open" would be drawn as an empty, green building, which for an office building
  is a claim nobody made.
- **Mulligan's Grill and the cafes** inside other buildings: tenants.

### The accuracy harness was about to mislead, and now does not

After adding the rule, `hours_accuracy.mjs --campus umd` first reported **92.2%**,
up from 51.6%. **That number is wrong and must not be quoted.** Two separate
faults, both mine:

- It filed the 43 rule buildings under "published schedule" and applied
  Illinois' assumed 93%, which belongs to a source that names each building's
  own hours. A general rule got a specific schedule's accuracy.
- The hold-out scored the fallback against each building's published hours; for
  rule buildings those "hours" are built from the same class windows plus
  7am-9pm, so it was measuring the fallback's agreement with itself.

Fixed: rule entries get their own row, `campus-wide rule`, marked **UNMEASURED —
no ground truth**, are excluded from the composite, and are skipped in the
hold-out. Current output, week of 2026-10-19:

| | share of claims | accuracy |
|---|---|---|
| campus-wide rule | 62.1% | **unmeasured** |
| class-timetable fallback | 22.7% | 52.5% measured (280 slots) |
| published schedule | 9.1% | 93% assumed |
| dated feed | 6.1% | 97% assumed |

The estimate over the rated 37.9% is 69.3%. **Nothing can be said about the
other 62.1%.** The rule is the university's own statement about its own doors,
which is better than a guess, but "generally open" has not been checked against
a single real door, and a building with card access after 6pm would be wrong
on it every evening. Student check-ins are the only available check.

### The labelling gap

Only buildings with data were named; the other ~250 of the register's 308 were
unlabelled grey blocks. `labelRegisterBuildings` (Maryland only, flag in
`CAMPUS_CONTENT`) now names them, as **quiet labels**: dimmer, shown out to
2,000 m, ranked three times worse than a labelled building so they only fill
space nothing else wants. 180 labels are added. Sheds, barns, storage, garages,
concessions, trailers and numbered placeholders ("Building 006") are left
unnamed by a keyword list. Off for Illinois and Ohio State: Columbus has 534
register records and turning it on there would change a launched map.

For a building we know only by its register entry, the panel now says what the
university's own directory files it under. A residence hall reads "Residence
hall — the university lists this as campus housing and publishes no public hours
for it". The other categories keep "no hours published", because the directory
says nothing more about them.

### Three real buildings were being dropped from the map

`offMap()` removes any building the register does not carry, on the Wooster
reasoning (Ohio State teaches some Columbus classes 60 miles away). Three
College Park class buildings are missing from MD iMAP only because they opened
after that layer was drawn: **Thurgood Marshall Hall** (one of the larger class
buildings), the **E.A. Fernandez IDEA Factory** and **Yahentamitsi Dining Hall**.
They were silently absent from the map, and Yahentamitsi's new dining hours with
them. Each was checked three ways before being allowed back: Testudo resolves its
scheduling code, the university's printed directory numbers it (433, 228, 436),
and the 3D tiles carry it by its exact class-data name inside the map area.
`CAMPUS_CONTENT.registerGaps` lists them for Maryland.

### Still open

- 4 class buildings lost to Testudo's HTTP 500 (BMS, HIL, PWS, SEN) — unchanged.
- No ground truth for the campus-wide rule.
- `/umd.html` and the picker card are still held back: nothing here is public.
