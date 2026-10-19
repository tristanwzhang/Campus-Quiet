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

### Hours — the weak spot, and it is weaker than Columbus

**Maryland does not appear to publish per-building hours.** Ohio State's
registrar classroom-pool schedule has no Maryland equivalent that I can find,
and Facilities Management publishes none. Expect the class-timetable fallback to
carry most buildings, with `classDerived: true` doing the break-day work it
already does.

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

**Dining: does not publish hours on the web.** `/hours/dining-halls` gives only
generic meal windows (breakfast to 10:30, lunch 10:30–4, dinner 4 to close) and
then says, in as many words, to download the UMD mobile app for specific times.
`/hours/open-now` renders a full venue list with every hours cell showing "—",
in a real browser, with no API call. Two independent reads agree, so this is the
page's actual state rather than a loading artifact. The venue list is still
useful as a **venue → host building** map (Footnotes in McKeldin, Creative
Commons in Tawes, Sneaker's in Eppley), but those are tenants and their hours
are not their building's hours. The three dining halls that ARE buildings
(South Campus 026, Denton Area 251, Ellicott Area 257, Yahentamitsi 436) stay on
the class fallback.

### What this does to the hours count

Buildings that these sources can actually cover, intersected with the 63 the
class sweep found: **ERC (068, Eppley)** and **ARM (078, Reckord Armory)** from
RecWell. Plus **Stamp (163)** added by hand, and Ritchie and the Aquatic Center
if they are worth carrying. With the two LibCal libraries that is **5 to 7
buildings with genuinely published hours** — the same order as Ohio State's 5,
and still a long way from Illinois' 74.

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

### Hours: the search is now exhaustive, and the answer is five buildings

Checked and ruled out, so nobody repeats it:

- **Facilities Management** — publishes no building hours.
- **The registrar** — no classroom-pool schedule, the thing that covers 47
  Columbus buildings.
- **25Live**, which the Provost's classroom search runs on — every
  `25live.collegenet.com/25live/data/umd/run/*` endpoint answers **HTTP 401**.
  Closed, like Ohio State's room-booking app. Do not retry.
- **Dining** — nothing on the web; it points at the mobile app.
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

## What is different from Columbus, in one list

- **Better:** the code→building join is fully official and complete; library
  hours come 8 weeks ahead instead of 7 days.
- **Worse:** no campus-wide building-hours publication, so after RecWell, Stamp
  and the libraries there are still ~56 buildings on the class fallback. Ohio
  State at least has a registrar document covering 47.
- **New:** Testudo is HTML rather than JSON, hangs about a third of the time,
  and has a server-side gap that loses four real buildings.
- **Checked since:** RecWell publishes hours on its per-facility pages (not on
  its own "today's hours" page, which renders empty); Stamp publishes a weekly
  table plus dated break exceptions and is the best hours source on the campus;
  Dining publishes none on the web and points at its mobile app.
- **Same trap:** off-campus teaching centres, like Wooster. Filter on the
  university's own field.
