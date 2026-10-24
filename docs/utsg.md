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
(`node scripts/build_utsg_study_rooms.mjs`, once a term): name ("2241 Group Study Room 2A"),
floor, seats, features, building. Read from the libraries' own pages
(`libcal.library.utoronto.ca/space/<id>`); 3 listed ids are dead pages and skipped.
Availability is live: `/api/rooms` now also returns, per building, `rooms: {id: {free, until}}`
(free until when), `{free:false, next}` (booked now, free at), or `{free:false, opens}` (library not
yet taking bookings). `api/rooms.mjs` exports `roomStates` and `CAMPUSES`. In the "Study rooms"
sidebar, tapping a building with rooms opens its list (free first, longest first; "Free until
5:00 pm", "Booked . free 4:00 pm", "Opens 9:00 am") with a "Show on the map" row on top.
Other campuses' API responses gain the same `rooms` field, unused by their UI.
Classrooms remain impossible: no room numbers are published and the schedule tool needs a login.
