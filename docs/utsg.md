# Adding U of T St. George

Built 2026-10-21 on local branch `uoft`, **not pushed, not public**. The page exists
at `/utsg` locally; nothing links to it. Launch is the checklist at the bottom.

## What this campus is, in one paragraph

Better class data than any other campus (one official API, **real enrolment**),
and **thinner hours than any other**: two libraries publish dated hours, and the
other 60 buildings ride the class-timetable fallback. **There are no room numbers**,
so there is no `rooms.json` and no "find a free room".

## Sources

| What | Source | Notes |
|---|---|---|
| Classes | `POST https://api.easi.utoronto.ca/ttb/getPageableCourses` (the Timetable Builder's own API, no key) | `campuses:["St. George"]`, `sessions:["20269"]` (Fall 2026; Winter is `20271`), one call per division: APSC, ARTSC, FIS, FPEH, MUSIC, ARCLA. Page size is capped at 20 whatever you ask for, so ~320 requests. 6,460 meetings read 2026-10-20. |
| Enrolment | same API: `currentEnrolment` / `maxEnrolment` | People, not room size. `seats` in `class_activity.json` is enrolled students. |
| Rooms | **not published** | `buildingRoomNumber` is empty on every meeting. |
| Names, numbers, coordinates | `api.concept3d.com/locations/<id>?map=1809`, the backend of the university's own map (map.utoronto.ca) | Each meeting's `buildingUrl` is `map.utoronto.ca/?id=1809#!m/<id>`, so the code→record join is free. Record name is `Name \| CODE`; description carries `Building #NNN` and the address. |
| Footprints | OpenStreetMap | The map record is a POINT. The footprint is the OSM building containing it, or the nearest within 30 m. |
| Library hours | `library.utoronto.ca/library/<slug>` embeds `hoursJson`: dated, **84 days ahead**, closures explicit | Robarts and Gerstein only (see below). |
| Calendar | Engineering "Fall 2026 and Winter 2027 Key Dates" + SGS sessional dates PDF | Both on utoronto.ca. |
| Study rooms | LibCal, `libcal.library.utoronto.ca`, same key-less call as the other campuses | 65 rooms in 6 buildings. See `api/rooms.mjs`. |

## Decisions to know about

**Official names beat Wikipedia.** An earlier preview took code→name from a
community-edited Wikipedia list. The university's own map disagrees with it in four
places that matter: `SM` is the **Sigmund Samuel Library Building** (Gerstein is the
library inside it), `SK` is the **Factor-Inwentash Faculty of Social Work**, `PT` is
the **D.L. Pratt Building**, `FE` is **371 Bloor Street West**. The build uses the map's names.

**Library hours are the building's hours only where the building IS the library.**
Robarts → Robarts Library (RL); Gerstein → Sigmund Samuel Library Building (SM; the
map's address for it is "7 & 9 King's College Circle", Gerstein's is 9). A library
inside a faculty building says nothing about that building's doors, same rule as the
other campuses. Every other building: class-timetable fallback, labelled as an estimate.

**`assumeShutWithoutClasses` is on.** The timetable has no Saturday or Sunday meetings
at all, so without it the map is silent every weekend. It can only err toward
"probably closed". Same setting and same reasoning as Maryland.

**Calendar** (all from U of T): Labour Day 7 Sep and Thanksgiving 12 Oct close the
university; **Fall Study Break 26–30 Oct, no classes** (A&S and Engineering); classes
end 7 Dec; **8 Dec is "Makeup Monday"** (runs the Monday timetable, NOT modelled, so it
reads as an ordinary Tuesday); F-term exams to 22 Dec; winter break 24 Dec–5 Jan.
Finals are assumed the same as ordinary weeks, the rule the owner set 2026-10-18.

## Hours added 2026-10-21 ("fill what you can")

Searched for official hours for the biggest class buildings and the obvious study spaces.
**Found and added (4 of 63):**
- Robarts, Sigmund Samuel/Gerstein: dated, 84 days (library pages).
- **Athletic Centre** (map's `Warren Stevens Building`, WS): weekly, M-F 7-23, Sa-Su 9-17,
  from KPE's own page; address 55 Harbord St matches the map. Carries `type: 'rec'`, which
  is safe now that it has real hours. Valid 8 Sep-23 Dec; no closure is claimed for
  Thanksgiving or the study break because the page names none.
- **Hart House** (HH): "Mon-Sun 7:00 am-11:00 pm", from harthouse.ca/contact/hours. Cloudflare
  blocks scripts, so it was read in a browser. It has no classes, so it enters through the
  hours file and the map's own record (id 494521); the 3D tiles carry its name, so it draws.
  Its fitness centre and pool print separate holiday hours, so no building holiday rule.

**Searched, nothing official, so NOT filled (by the no-assumptions rule):** Bahen (a CS
department FAQ says 8am-11pm Mon-Fri and a CS labs page says 24 hours; they conflict and
neither is the building's page), Myhal (a 2018 PDF whose hours section I could not read),
Sidney Smith (only the Commons study room: Mon-Thu 10-7:30, Fri 10-5, two pages disagree),
OISE, Student Commons (a pre-opening news piece said "24 hours a day", a plan not a
schedule). **The one move that would settle these is asking Facilities / Campus Safety for the
lock schedules**, as with Maryland's UMPD and Ohio State's Lock and Key.

**The harness got worse by adding real data.** `hours_accuracy.mjs` now holds out FOUR
buildings (two libraries, a gym, Hart House) and reports 50.0%, down from 59.8%, because
all four are classless and the fallback has nothing to go on. It still is not U of T's accuracy.

## What was measured, and what the numbers mean

- 62 of 67 building codes placed. **Unplaced, no source: BY, ON, SD, TL, UP.**
- **No OSM footprint within 30 m of the map's point: Earth Sciences Centre (ES),
  Galbraith Building (GB), Sigmund Samuel (SM), Trinity College (TC).** The nearest
  candidates were 36–78 m away and Galbraith's three were equidistant, so none was
  guessed; OSM carries no address tag on any of them. **Checked in the browser
  2026-10-21: the 3D tiles carry "Galbraith Building" by name, so it IS drawn and
  coloured** (matched on name, as on every campus). The register's gap only costs the
  hand-drawn overlay and the click-to-fly outline. Trinity is labelled from the point.
  Still to look at: whether Earth Sciences and Sigmund Samuel are tile-named too.
- Terrain sampled 2026-10-21: placed buildings sit 62.6–76.4 m (ellipsoid), median 71.2;
  the grid spans 45.6–98.6. **The ground height was not flat**: it climbs about 50 m
  from the lake side to Bloor. `groundM: 71`, plus `ground.json`.
- **Do not quote the harness figure.** `node scripts/hours_accuracy.mjs --campus utsg`
  reports 59.8% for the fallback, but its hold-out is the two libraries only (112 slots,
  both 24-hour-ish and nearly classless), which is the worst case for a class proxy. It
  is not U of T's accuracy. The fallback measured 90.9% at Ohio State and 85.7% at
  Illinois on buildings that actually have classes. U of T's real number is unmeasured
  until the `hours_report` events arrive.

## Competitors (web search, 2026-10-20, not exhaustive)

**SpacePlusU** shows live traffic by building and is the direct competitor (2022
coverage; current status unconfirmed). The university's own Sync app finds free
classrooms. App Store and Reddit were not checked.

## Not done

- **Winter 2027** — sweep session `20271` before January; the calendar block is Fall only.
- **Robarts study rooms** — booking is on LibCal's newer `/r/search/robarts` with no lid
  the existing call can reach.
- **Music, University College, Graham and Pratt libraries** have LibCal lids but are left
  out until a page, not a name, confirms their building.
- Biweekly meetings (`repetitionTime`) are counted as weekly.
- Weekly refresh: the library window rolls, so `build_utsg_hours.py` belongs in the
  weekly workflow (wired, but the workflow file has not been pushed).

## The launch checklist (not done; wait to be told)

1. `utsg-preview.png` exists but is a **stopgap**: the browser pane captures at 800 px, so it
   is upscaled 1.5x to 1200x630 and a little soft, and its clock is faked to Tue 20 Oct
   11:00. Retake it at full size before launch.
2. `index.html`: a picker card `<a class="campus" href="/utsg">…UofT…</a>`, and `utsg`
   in the remembered-campus redirect.
3. `sitemap.xml`: `https://campusquiet.com/utsg`.
4. Create the PostHog dashboards (per-school + master `utsg` column) **only when asked**.
5. `logos/utsg.png` is in (the owner supplied the crest 2026-10-21, resized to 300 px). Not yet referenced by any page.

## Rebuilding

```
python3 scripts/build_utsg_class_estimates.py      # sweep (--offline reuses meetings.json)
python3 scripts/build_utsg_buildings.py            # register + rename class_activity keys
python3 scripts/build_utsg_hours.py                # weekly
python3 scripts/build_basemap.py --campus utsg
python3 scripts/build_campus_pages.py
```

Run the class sweep BEFORE the buildings script: the buildings script renames the keys
of `class_activity.json` from codes to names, and a fresh sweep writes codes again.

## Decision on the map vendor (owner, 2026-10-21: "whatever is best and free")

Keep the official names. The Concept3D backend is read **at build time only**, ~60
cached requests per rebuild, with the map site's own published key; **no visitor's
browser ever calls it** (`app.js` and `utsg.html` contain no reference). Only the
resulting names, numbers and coordinates are shipped, as facts about buildings. The
free alternative (OpenStreetMap names) was worse: it is wrong or silent on exactly the
buildings that matter. Revisit only if the vendor or the university objects.


## Full hours search, 2026-10-21 (owner: "search everything") -- 12 of 66 buildings

**Have published hours (12):**
- Dated, 84 days, one feed (`libcal.library.utoronto.ca/api_hours_grid.php?iid=478`):
  Robarts Library, **Robarts Common** (LibCal's "Robarts Common Building Hours": 24 h Mon-Thu,
  to 11pm Fri), Sigmund Samuel/Gerstein, **E.J. Pratt Library**, **John M. Kelly Library**.
  Kelly's feed never marks a closure (open on Christmas Day), so the university's own closure
  days replace its dates there. Robarts Common's "not-set" days are unknown, not closed.
- Weekly, from the building's own page: Athletic Centre (KPE), Hart House, **OISE**
  (facilities page), **Woodsworth College** (contact page, "Building Hours"), **Innis College**
  (weekdays only; closed for renovation 26-30 Oct), **Rotman** (weekdays 6:30am-9pm; weekends
  fob-only so closed to the public), **Student Commons** (UTSU contact page, weekdays 9-9;
  footer (c) 2020, so possibly dated).

**Searched, nothing usable -- these stay on the class-timetable estimate:**
| building(s) | what exists |
|---|---|
| Sidney Smith | only the Commons study room (Mon-Thu 10-7:30, Fri 10-5); OSM tag, community-edited |
| Bahen | CS labs page: "available during term time 24 hours" but only CS students by TCard after "business hours" (undefined). A second CS FAQ (8am-11pm M-F public) could not be re-found |
| Myhal | Facility Management protocol, **dated Oct 2018**: M-F 7am-10pm, Sa-Su 8am-8pm. Too old to assert (same rule as Ohio State's stale pages). The strongest candidate if someone confirms it |
| Medical Sciences | 2022 construction notice (weekdays ~7am-6:30pm, fob after) -- expired |
| Engineering (SF, GB, MC, WB, MB, HA, RS, PT) | ECF says "nightly and weekend building closures" exist; no times published |
| McLennan, Lash Miller, Ramsay Wright, Earth Sciences, Clara Benson, Astronomy, Anthropology, Bancroft, Naylor | office hours only, or third-party listings |
| University College, Victoria (VC, NF, BT, EM, LI), St. Michael's (CR, BR, TF, AH, OH), Trinity (TC, LA, GI, St. Hilda's) | office/desk hours only; residences have 24 h porters |
| New College (Wilson, Wetmore) | "after 10pm the buildings are locked externally" (residence page); no opening time |
| Daniels, Edward Johnson, Jackman Humanities, Munk, Social Work, Pharmacy, Health Sciences, Convocation Hall, Stewart, 700 University, 90 Wellesley, 371 Bloor, Borden, Koffler | nothing official |

There is **no campus-wide lock schedule** in public. The one thing that would settle the
rest is a request to Facilities & Services / Campus Safety for the programmed door schedules.


## Second push, 2026-10-21 (owner: "try your hardest") -- 22 of 69 buildings with real evidence

- **Library-inside evidence (10 buildings).** A library open to patrons means its building's
  doors are open, so `tenantLibraries` in `building_hours.json` proves "open AT LEAST now" for
  Sandford Fleming, Lash Miller, McLennan, Bahen, Sidney Smith, Edward Johnson, University
  College, Emmanuel College, Wilson Hall and Daniels. `app.js` (`tenantOpen`/`withTenant`) uses
  it only to override "probably closed", never to claim closed; the panel says which library,
  and the hours report records basis `library inside`. Each link is an address match or the
  map's own record. Earth Sciences did not match and is out. Other campuses: no such data,
  harness unchanged to the decimal.
- These 22 buildings hold ~40% of peak class load (was ~8% with own hours alone).
- **Study rooms: 69 in 9 buildings** (added Music, UC, Pratt).
- **Placed 3 more codes:** BY 255 Beverley Street, SD Sir Daniel Wilson Residence, TL Lawson
  Centre (from LSM's public classroom list). UP left out: two official sources disagree.
- **Dead ends, do not redo:** Campus Room Finder (room availability for every room) requires a
  UTORid login. LSM's public Classroom Specification app (`lsm.utoronto.ca/webapp/f?p=210`)
  lists the central classroom pool with capacities but no hours; its availability calendar
  (app 200) is retired. LSM's FAQ/policy pages state no lock rules.
- **LSM publishes `documents/Academic Calendar 2026-2027.pdf`** -- an official calendar source
  for the Winter update.


## Third push, 2026-10-21 (owner: "do anything you can", no contacting the school)

**Study rooms: 138 in 11 buildings** (was 69). LibCal's own location list
(`libcal.library.utoronto.ca/spaces`) showed lid 3446 "Robarts Library and Robarts Common"
(68 rooms) and 3348 Kelly (5). Robarts is asked per category (gid) so Robarts Common's 32
rooms land on Robarts Common. Graham (3 Devonshire Pl) and IRHR (121 St. George) are not
buildings on this map.

**Weekday campus default (`buildingDay`, U of T only).** The six U of T buildings that publish
hours AND hold classes all open by 6:30-9am and close 8-11pm on every weekday, Fridays
included -- while the class window shut every building at 5pm Friday and 8pm mid-week, which
is where all the fallback's errors were. Buildings with classes that day now read "Probably
open" 8:30am-9pm (where >= 5 of 6 agree at every hour), with the reason shown and no
busyness number. Not applied to Convocation Hall or the two theatres (venues). Weekends get
nothing: the six disagree. Harness, week of 2026-10-19: UTSG all-day 72.1% -> 76.2%,
evening 73.3% -> **81.0%**, only 5 of 416 "said open when closed". **Caveat: the hold-out
buildings are the six the rule came from**, so this gain is partly circular; the real check
is the hours_report events after launch. Other campuses unchanged to the decimal.

**Tried and failed:** Google Maps (tested against 5 known buildings: right on Robarts only;
gave office hours for OISE, library hours for Robarts Common, nothing for Hart House; says
Sidney Smith closes 6:30pm while ~1,050 students are timetabled there 6-7pm Monday). U of T
Food Services (foodservices.utoronto.ca refuses connections from this network). No official
study-space directory exists (library.utoronto.ca/space is a 404).


## Busyness, 2026-10-21 -- Google popular times for the six non-class buildings

`data/utsg/popular_times.json` (same shape the Illinois file uses; `app.js` already reads it
first, as "measured"). Robarts, Gerstein (Sigmund Samuel), E.J. Pratt, Kelly, Hart House and the
Athletic Centre -- exactly the buildings that had no classes and rode a generic type curve.
Read from Google Search's popular-times chart in the browser pane, one place at a time,
name-checked; 100 = that place's busiest hour of the week. Cross-check: the Athletic Centre's
weekend curve runs exactly 9am-5pm, its published weekend hours.

How it was read (do not re-derive): the day tabs only switch on REAL clicks while the pane is
hidden; scripted clicks silently returned one day seven times (caught by checking that days
differ). Teaching buildings (Sidney Smith, Bahen, Myhal, Medical Sciences, UC), OISE, the
Student Commons and Robarts Common have NO popular times on Google.

Static, not live: refresh once a term. Kelly's Monday and Wednesday curves are identical as
Google shows them.


## 2026-10-21: Robarts Common busyness, and a room-count bug on EVERY campus

**Bug (all campuses, live on UMD/OSU):** LibCal's grid returns `bookings: []` everywhere; a
booked slot is a `slots` entry with className `s-lc-eq-checkout` (drawn red, legend
"Unavailable/Padding" on LibCal's own page; free slots are `s-lc-eq-avail`, green).
`countFree` read only `bookings`, so every booked room counted as free. Fixed in
`api/rooms.mjs` on this branch. Live at 17:41 Wed: U of T 3 free of 88 bookable (Robarts Common
0 of 32), Maryland 13 of 86, Ohio State 2 of 7 -- the old code would have said nearly all free.
**Not deployed: the owner said not to push.**

**Robarts Common busyness** now = share of its 32 group rooms booked right now (`busyFromBookings`,
`bookingBusyness()` in app.js), labelled "N of M study rooms booked right now (live)", only for
the current hour and only when >= 8 rooms are bookable; otherwise the library curve. No past
bookings are exposed by LibCal (past dates return no slots), so there is no history to build a
typical curve from.


## 2026-10-21: flicker (Student Commons, Ramsay Wright) -- two causes, both fixed

1. **Name.** The register carried only the university's name; the 3D tiles are OpenStreetMap and
   say "Ramsay Wright Building", "North/South Borden Building", "Sanford Fleming Building" (sic),
   "E. J. Pratt Library"... so the tile was never claimed and we drew our own copy over it. The
   register now carries the footprint's OSM name as an alias, but only when it shares a
   distinctive word with the official name (the first cut gave the Lawson Centre the Gerald
   Larkin Building's name). 20 overlays became 8.
2. **Courtyards.** A tile block reports one point (its centre). For a U- or L-shaped building
   that centre is in the courtyard, outside our outline, so the existing "hide the tile under our
   own shape" rule missed it and the two shapes z-fought. `coverByHull` (U of T only) tests the
   outline's convex hull instead. Other campuses are unchanged.


## 2026-10-22: "Study rooms free now" list (owner: "still no study room tab")

The picks sheet already had the markup and CSS for a second section, "Study rooms free now"
(`#rooms-section`), but nothing in `app.js` ever filled it. `renderRoomsSection()` now does:
one row per building with rooms bookable right now, most free first ("9 of 23 free" /
"all 32 booked"), tap to fly to the building; hidden when nothing is bookable (e.g. 2am), so it
is invisible at night by design. Gated by `roomsList: true`, U of T only -- turning it on for
Maryland and Ohio State would change their launched sheets. The per-building panel line
("N of M study rooms free to book right now") was always there.

**Follow-up, same day:** the section no longer hides when nothing is bookable. At night it reads
"Study rooms" with the five buildings that have the most rooms ("35 rooms") and "Not bookable right
now -- libraries take bookings while they are open"; in the day it reads "Study rooms free now"
with live counts. Capped at 5 rows plus "+ N more buildings".


## 2026-10-24: "Study rooms" sidebar; the hours rule tested without circularity

**Sidebar.** The "Find a free room" panel (`#browse-all`) only appeared where a campus had a
classroom schedule (`rooms.json`). U of T has none (no room numbers), so with `roomsList` it now
shows a "Study rooms" button that opens the same sidebar, titled "Study rooms & buildings": every
building by library/academic, a badge of live study rooms free to book (e.g. 9/23), "Open" or
"No hours" otherwise, and the time wheels to check opening hours at another time. Tapping a
building closes the sidebar and opens it on the map (there is no per-room list to drill into). The
badge describes NOW only. Maryland and Ohio State are unchanged.

**Leave-one-out test of `buildingDay`.** The harness gain was circular (the rule came from the same
six buildings it was scored on). Re-deriving the rule from five and scoring on the sixth, for each:
weekday slot accuracy **93%**, evening (6pm-midnight) **92%** (Athletic Centre 85%, OISE 94%,
Woodsworth 94%, Innis 98%, Rotman 92%, Student Commons 96%). Caveat: these six PUBLISH their hours,
so they are probably more public-facing than Bahen, McLennan or Sandford Fleming.
**Weekends are the weak spot:** saying "closed" scores only ~71% on the four with published
weekend hours (Athletic Centre 9-17, OISE 9-21, Woodsworth 10-18 are open; Rotman is fob-only).
Blended with weekdays, about **87%** for buildings like these. NOT changed: a "probably open 10-5"
weekend default would score ~85% on those four, but it is the direction that sends someone to a
locked door (Rotman), which the owner's rule rules out. It is the owner's call.


## 2026-10-24: weekend rule ON (owner approved)

`buildingWeekend: [10, 17]` (U of T only). On Saturday and Sunday a building that holds classes in
the week reads "Probably open" 10am-5pm and "Probably closed" outside it, with the reason shown
("the U of T buildings that publish weekend hours are mostly open about 10am-5pm"). Still closed:
buildings with their own published hours (Rotman stays closed on weekends), venues
(Convocation Hall, the theatres), and holidays/breaks (Dec 26 reads closed). Harness week of
2026-10-19: UTSG all-day 76.2% -> 85.5%, evening 81.0% -> 84.4%, but "said open when closed" rose
from 5 to 13 of 416 test slots (Rotman-like fob-only buildings). The rule came from the same
four buildings it is scored on, so the gain is optimistic; the `hours_report` taps after launch
are the real check on weekends. If weekends draw reports of "it's actually closed", set
`buildingWeekend` to null in app.js to turn it off.


## 2026-10-24: per-room study room data

Every bookable study room is now individual: **139 rooms** in `data/utsg/study_rooms.json`
(`node scripts/build_study_rooms.mjs`, once a term): name ("2241 Group Study Room 2A"),
floor, seats, features, building. Read from the libraries' own pages
(`libcal.library.utoronto.ca/space/<id>`); 3 listed ids are dead pages and skipped.
Availability is live: `/api/rooms` now also returns, per building, `rooms: {id: {free, until}}`
(free until when), `{free:false, next}` (booked now, free at), or `{free:false, opens}` (library not
yet taking bookings). `api/rooms.mjs` exports `roomStates` and `CAMPUSES`. In the "Study rooms"
sidebar, tapping a building with rooms opens its list (free first, longest first; "Free until
5:00 pm", "Booked . free 4:00 pm", "Opens 9:00 am") with a "Show on the map" row on top.
Other campuses' API responses gain the same `rooms` field, unused by their UI.
Classrooms remain impossible: no room numbers are published and the schedule tool needs a login.


## 2026-10-24: live library computers (and why they are NOT busyness)

U of T's Information Commons publishes live public-computer availability for 11 St. George
libraries, no login: `cafstatus.icicle.utoronto.ca/frontend/Web/Summary/StGeorge` (found via an
archived copy of Gerstein's old "computer finder" link; the new library site dropped it). Parsed in
`api/rooms.mjs` (`parseComputers`, tested live: Robarts 183/210, Gerstein 36/41, Kelly 34/40, Pratt
36/38, OISE 16/16, Engineering 22/22, Graham 21/23, Music 2/9, Math 3/3, Emmanuel 4/4) and returned
as `computers` per building, cached with the rooms. Noranda Earth Sciences is left out (address does
not match the map's). Shown in the building panel ("36 of 41 library computers free right now ·
UTORid login") and the study-room list subtitle.
**Deliberately not used for busyness:** mid-afternoon Robarts had 28 of 210 computers in use while
Google's typical curve says it is near its weekly peak -- students study on laptops, so computer
use does not track crowding. Mixing it in would make busyness worse.


## 2026-10-24: quiet vs group, room features, late-night safety (all official U of T sources)

- **Room features and photos** (`build_study_rooms.mjs`): each LibCal location page lists its
  rooms with LibCal's own filter tags (`filterIds` -> "Power Available", "Monitor Available",
  "Whiteboard or Chalkboard Available", "Accessible Seat/Space", ...) and a photo. 126 of 139 rooms
  tagged (117 outlets, 70 whiteboard, 62 screen, 20 accessible); 113 photos (LibCal's CDN, hotlinked,
  lazy). Room list has Outlets / Whiteboard / Screen / Accessible filter chips.
- **Quiet vs group** (`build_utsg_library_spaces.py`): every `/space/` page in library.utoronto.ca's
  sitemap (213; robots.txt allows) carries "Noise Level" (Silent / Quiet / Collaborative), "Space
  features" and its library. 169 map to St. George buildings; **24 open study areas in 7 buildings**
  are kept (`area: true`) -- prayer/reflection rooms, workrooms, labs, consultation and bookable rooms
  (already in the room list), and ASSIGNED carrels are excluded. Shown in the building panel ("Study
  areas (the library's own noise levels)") and as Silent / Quiet / Group work chips in the sidebar.
  The libraries' own "Find a space" page never finishes loading (checked in a browser and by script),
  which is why the sitemap route was used. Re-run once a term (slow: ~10 min).
- **Late-night safety**: TravelSafer (Campus Safety, 24/7, any campus location or abutting TTC
  station, 416-978-7233 / UofT Safety app) shown 9pm-6am under the picks (`safetyNote`).
- **Not done, and why:** laptop/charger loans -- LibCal equipment at St. George is only the Music
  Library's AV gear. Food hours -- foodservices.utoronto.ca refuses connections from this network,
  and search snippets are not solid data; it may work from Vercel, untested.


## 2026-10-24: the study-spot hub (owner: "hard to even find those features")

The features lived behind a small "Study rooms" button and a 69-building list, and on a phone the
bottom sheet showed two picks and four room counts. U of T's picks sheet is now one **"Find a study
spot"** sheet with four tabs, on every screen size (`hubTabs`; `renderHub()`):
- **Open now** -- the existing picks, scarcity note and the late-night TravelSafer line.
- **Rooms** (badge = rooms free right now) -- buildings by free study rooms, with Outlets /
  Whiteboard / Screen / Accessible chips that recount free rooms (27 of 35 with outlets). Tap a
  building for each room (the sidebar room list, filters carried across).
- **Quiet** -- the 24 open study areas grouped Silent / Quiet / Group work, "Has outlets" chip, tap to fly there.
- **Computers** -- 406 library computers, per library, with a bar.
The tab bar stays put; the list scrolls inside (max 46vh / 380px) so the map stays visible; rows are
48px tall; desktop card widened to 336px so labels stay on one line. The separate "Study rooms free
now" box is replaced. The top "Study rooms" button still opens the full sidebar (all 69 buildings,
hours at another time, noise and outlet filters). Other campuses are unchanged.

## 2026-10-26: lighting up the map (commenter: "a ton of buildings with no hours")

Only ~22 of 69 buildings were lit during reading week. Two causes, both fixed:

1. **Study-break days went blank.** `assumedStatus` returned "unknown" for every building on a
   `classesOutDates` day. U of T's reading week is a working week (the buildings that publish hours
   list the same hours through it). **Tightened the same day at the owner's request ("don't swing too
   far the other way"):** each building gets exactly what the SAME weekday of an ordinary week gives it
   (its own class window widened to `buildingDay`; "probably closed" where nothing normally meets on
   that weekday). Checked: reading-week Tue/Fri match ordinary Tue/Fri building for building, except
   the three venues (stay unknown) and Innis (its published hours close it). Never more generous
   than a class week, which is what the harness measures (84.7%).
   Panel headline says "Probably open" for any campus-default open (it used to say "Open now").
2. **Library buildings with no classes were never on the map** (the register comes from the timetable).
   Added from map.utoronto.ca's own building records (`EXTRA_IDS` in build_utsg_buildings.py):
   - library = building, full dated LibCal hours: Thomas Fisher Rare Book Library (RB, lid 8353),
     John W. Graham Library / Trinity (MU, lid 8347; the map labels the 1 Devonshire building so;
     its feed shows Christmas open, so it follows campus closures like Kelly).
   - library inside (open at least while the library is): Dentistry Building (8434), Canadiana Gallery
     (Criminology, 8352), 121 St. George Street (Newman IR library, 8351), Knox College (Caven, 8441),
     Massey College (Robertson Davies, 8444), Jackman Law Building (Bora Laskin: LibCal defers to
     library.law.utoronto.ca, "Open Monday - Friday 9 a.m. to 5 p.m.", WEEKLY_TENANTS).
   Each link is the map's record of the library carrying the building's code. Earth Sciences Library
   -> Earth Sciences Centre added on the owner's confirmation (addresses differ).
   `codeFor()` finds these by register name (`registerByName`, U of T only).

Result (demo clock): 77 buildings; Tue Oct 27 2pm 70 lit (was ~22), Fri 3pm 65; a class weekday 2pm 74/77.
All 8 added libraries list public access (Massey, Dentistry, Law partly restricted; Fisher is a rare-book reading room).
Harness U of T 84.6% -> 84.7% all day. Other campuses unchanged by this (their small drift since
last week is data refreshes, identical with and without these edits).
Still dark, honestly: First Nations House (Borden North) publishes no hours anywhere.

**Trinity / Graham Library looked mottled (fixed 2026-10-26).** The OSM tiles name 1 Devonshire Place
"Munk School of Global Affairs & Public Policy" (the Munk School's Trinity site), which IS a known
building (register MK, 315 Bloor). So the tiles took Munk's colour while the app drew its own Graham
Library shape on the same spot: two colours z-fighting. claimTileBuildings now gives a named tile to
the drawn building it stands in when the tile's own name belongs to a building whose official point
is over 150 m away (U of T only, coverByHull). Also hand-checked aliases (MANUAL_ALIASES in
build_utsg_buildings.py): MU "Devonshire House", IR "Centre for Industrial Relations and Human Resources".

**"3D lag" check (2026-10-26, a critic said the downtown models lag and some campus buildings do not load).**
Measured on the home view against Illinois: U of T loads 17.4k buildings / 324k triangles / 28 MB across 18
tiles (Illinois 10.1k / 179k / 15 MB); 62% of U of T's loaded buildings are outside the visible area
(Illinois 15%). Frame time here is about 7 ms; a tighter visible zone did not make it faster (hidden
buildings are still processed), and dynamic/coarser detail changed nothing at this view (it is already
coarse). The tile-naming code costs 24 ms for ALL tiles. So no fix to the geometry was warranted, and the
lag could not be reproduced on a fast laptop; it may be a slower device.
What the check DID find is the "campus buildings not loaded" half: Gerstein and Trinity College had 3D
buildings (OSM names "Gerstein Science Information Centre", "Trinity College") that never joined to
the register's names, so they stayed no-data grey. Added MANUAL_ALIASES SM and TC (no outline needed),
and replaced yesterday's Munk/Graham special case with a general rule: a tile whose name belongs to a
building the register puts more than 150 m away (U of T only) falls back to the register footprint it
stands in, or is hidden under our own shape. Robarts Common is the only known building with no shape
(label only, on purpose).

**Study break no longer discounts libraries (2026-10-26, owner on the live site: "Robarts is 'empty' with 44 computers in use").**
Fall Study Break (Oct 26-30) was kind 'break', whose CALENDAR_EFFECTS multiply libraries and study spaces
by 0.3 -- a judgement call inherited from Illinois' Fall Break, when students leave town. Robarts read
10% full at Monday 8pm; Google's typical Monday 8pm is 34%. U of T's is a reading week and students stay,
so it is now kind 'studybreak': library and study = 1 (the usual curve, not boosted, since nothing
measures a boost); union/dining/rec/atrium keep the old discount, which is unchanged and still a guess.
Robarts Tue 8pm now reads 42%. Busyness is still the typical curve, not today's reality: the live
computer count (e.g. 24-44 of 210 in use) is the real-time signal and is shown beside it.

**Building panel ran off the window (2026-10-26, owner screenshot of Robarts).** The card had no height
cap, so Robarts (rooms + computers + study areas + survey + wish buttons) overflowed both edges of a
~900px window. Now: a `#panel-scroll` box inside `#panel` (close button outside it, stays put) capped
to the window (desktop: 100dvh - 96 - 56px; phone: 100dvh - 32 - 170px) and scrolling inside; room
sources shown as two names + "+N more"; at most 4 study areas listed ("+N more, see the Quiet tab").
Applies to every campus (CSS lives in the shared template); only buildings with a lot to say scroll.

**Morrison Hall and Goldring Student Centre added (2026-10-26, from the Reddit critique).** Neither has
building hours anywhere official, so each is known only through a tenant whose OWN official page
publishes hours ("open at least then", never "closed outside"; WEEKLY_TENANTS in build_utsg_hours.py):
- Morrison Hall (MO, 75 St. George, a University College residence): Howard Ferguson Dining Hall on its
  first floor (it takes cash and cards), from uc.utoronto.ca: academic year Mon-Fri 7:30am-7:30pm,
  Sat-Sun 9am-7:30pm, both closed 3-4pm; Dec 24-Jan 5 daily 9am-7:30pm.
- Goldring Student Centre (GC, 150 Charles St W, Victoria): the Cat's Eye pub on its first floor,
  thecatseye.ca: "open 9AM to 11PM Monday to Friday starting in September". A volunteer-run pub, so it
  is not offered on study-break or campus-closed days. NOT used: Apple Maps' 8am-11pm and a 2021 student
  blog (third-party, old); the Registrar's and Writing Centre hours are offices, not the building.
Outside those hours both read "No hours" (not "closed"). The panel now says what the evidence is:
"Open now - the Howard Ferguson Dining Hall inside is open" (same for the 10 library-inside buildings).
Map records: Morrison Hall 985707, Goldring Student Centre 506453. Not yet seen rendered in 3D (app window
was not visible); both have register footprints, drawn by the app's own path if the tiles do not name them.

**Goldring Centre for High Performance Sport added (2026-10-26).** The gym (GO, 100 Devonshire Pl; map record
494556), no classes. KPE posts its building hours on three official pages that DISAGREE on weekends: facility
page Mon-Fri 7am-11pm, Sat-Sun 9am-11pm; notice banner Sat-Sun 9am-7pm; contact page Mon-Fri 7am-11pm,
Sat-Sun 7am-9pm. Weekdays agree, so Mon-Fri 7am-11pm is used; weekends use only the span every page calls
open, 9am-7pm. It is "open at least then" evidence (`own: true` in tenantLibraries), so outside it the map says
"No hours", never "closed". Panel: "Open now - by the hours Kinesiology & Physical Education posts". Campus
closure days are skipped. Third-party listings (Apple Maps 7am-9pm, Waze, Fresha) ignored.

## Unmapped clicks on launch day (2026-10-26)

PostHog `unmapped_building_opened` for /utsg: Rotman (4), Gerstein (3), Soldiers' Tower (3), Central Exams Facility, Trinity College, Simcoe Hall, Royal Ontario Museum, Donnelly Centre (2 each). Gerstein and Trinity were all clicked before the 19:13 fix that aliased their tile names (none since). Rotman's tile is named "Joseph L. Rotman Faculty of Management", which never joined the register's "Rotman School of Management" (105 St. George), so it read "no data" despite having hours: alias added. The rest are research, admin, exam or museum buildings with no published public hours, so they stay unmapped.

## Royal Ontario Museum (2026-10-27)

Added at the owner's request (2 clicks on launch day). It is not a U of T building: the university's map lists it as a point of interest (record 497525, no building code), so it gets the made-up register key `RM`. Hours: rom.on.ca/operating-hours publishes the CURRENT month day by day (10:00-17:30, Mondays closed, 3rd Tuesday 10:00-20:30). `_rom()` in `build_utsg_hours.py` reads only the dates the table states; every other date has no hours (the map says "No hours", never a guess), so on launch it covers just the rest of October and the weekly refresh extends it a month at a time. Closed Mondays also read "No hours", not "Closed" (tenant evidence never causes "closed"). The page's "open today" banner is not used: it said open on a Monday the table lists as closed.

## Retention changes (2026-10-29)

Launch-week data: 183 devices, 10 (5%) returned on a second day; 74% of survey answerers said they'd return. Two changes:
- **Computers first on phones.** The Computers tab now carries the free-computer count as a green badge, and on a phone it is the tab shown first, once, while any library has a free computer (otherwise Open now stays first; a list of closed libraries is a worse first screen). Choosing a tab, or the exam banner, ends the default. Event `hub_default_computers` counts how often it applied.
- **Install tracking.** The "Got it" button on the iPhone/in-app nudge, the only button those visitors get, now fires `install_nudge_acknowledged` (only the Android prompt's "Not now" is still `install_nudge_dismissed`). Installed visits were already separable: every event carries `browser_kind: installed`, and `app_installed` fires on install.

## Check-in prompt (2026-10-31)
U of T opened a building in 33% of visits but took 3 check-ins in its first week (UIUC 10, OSU 8, UMD 8).
When a building is open and nobody has reported on it lately, the panel's question now reads "Nobody has
reported on this one lately. Are you here? How busy is it?" (otherwise the plain "How busy is it right now?").
`CAMPUS_CONTENT.checkinPrompt` turns it on, U of T only. Events: `checkin_prompt_shown` {building, device}
and `checkin_submitted` now carries `prompted`. Read it as check-ins per `checkin_prompt_shown` (and
building_opened) against the 3-per-week baseline; judge after ~2 weeks, not on a day's numbers.
