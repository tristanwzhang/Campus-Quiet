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
