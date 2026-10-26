# Analytics (PostHog) — setup notes

Tracking is already in the site ([app.js](../app.js), the `ANALYTICS` section near the top).
Project: PostHog **US region**, key `phc_pTDiskU8X4GkZisJH9byyKWbRnWv6tyLCZuJfZ6KTpQx`
(project keys are meant to be public in website code).

No cookies, no session recording, no personal data; "Do Not Track" is respected.
The script loads only after the map is up, so it can't slow the first view.

## Events the site sends

| Event | When | Properties |
|---|---|---|
| `$pageview`, `$pageleave` | Automatic | Gives visitors and time on site |
| `map_ready` | Buildings finished loading | `seconds_to_buildings`, `device`, `buildings_with_data` |
| `building_viewed` | Tooltip shown 1s (once per building per visit) | `building`, `status`, `source` |
| `building_opened` | Building clicked (check-in panel opens) | `building`, `device`, `source` |
| `checkin_submitted` | Student reports Quiet / Okay / Packed | `building`, `level`, `device` |
| `map_failed` | 3D buildings failed to load | `reason` |

## Build the KPI dashboard

**Dashboards → New dashboard → Blank**, name it "UIUC Spaces KPIs", then **Add insight**
for each row below. In the chart editor, click the event name in the series row to change
the event; "Break down by" is under the series.

| Chart | Type | Event | Settings |
|---|---|---|---|
| Visitors | Trends | `$pageview` | Measure: **Unique users**, last 30 days, grouped by day |
| Load speed | Trends | `map_ready` | Measure: **Property value → Average** of `seconds_to_buildings` |
| Most viewed buildings | Trends | `building_viewed` | Break down by `building`; chart type **Bar** |
| Check-ins | Trends | `checkin_submitted` | Break down by `level` (add a second series broken down by `building`) |
| Phone vs computer | Trends | `map_ready` | Break down by `device`; chart type **Pie** |
| Engagement funnel | Funnel | — | Steps: `map_ready` → `building_viewed` → `building_opened` → `checkin_submitted` |
| Failures | Trends | `map_failed` | None; should stay at zero |

## Filter out local testing

Project-wide (recommended):

1. **Settings → Project**
2. **"Filter out internal and test users"** → **+ Add exclusion criteria**
3. **Host** (`$host`) → **does not contain** → `localhost`
4. **Save**

Each insight then has a "Filter out internal and test users" toggle, on by default.

Just one dashboard instead: open it → **Filters** (funnel icon) → **+ Add filter** →
**Host** → **does not contain** → `localhost` → **Apply**, then save the dashboard.

## Per-school + master dashboard (multi-school expansion)

Every event carries a `school` property (`SCHOOL` constant in app.js, `"uiuc"` for now —
one line to change per deployment). One PostHog project holds every school; **not**
separate projects, which can't share funnels or combined charts.

**Status: built (2026-10-20).** PostHog project 614748 holds, per campus, an overview and a
launch-health dashboard (UIUC 2107522 / 2125754, OSU 2225117 / 2225118, Maryland 2233503 / 2233504),
plus "All schools — overview" (2225119) and "All schools — launch health" (2225120).
Maryland's launch health has one extra tile, "Hours check: was the map right?" (`hours_report`).
Four master tiles name campuses in their SQL (Visitors by campus, Daily visitors and page loads,
Check-ins per day, Where visitors come from): add a `school = '<id>'` column to each when a campus launches.
Maryland's are empty until `/umd` is public. The steps below are the manual route.

**U of T added (2026-10-25):** "UofT Spaces" (2259536) and "UofT Spaces — launch health" (2259538), made by
duplicating the Maryland pair and swapping `umd` for `utsg` in every tile. They stay empty until `/utsg` is
public. The launch-health one has an extra tile, "Find a study spot: which tab do people open?" (`hub_tab`).
The master tiles now carry a `utsg` column too: Visitors by campus, Daily visitors and page loads, Check-ins
per day, Where visitors come from, Did they leave straight away? (which also gained `umd`), and the browser-type
return-rate filter. Per-school tiles that group by `school` pick up new campuses on their own.

**Number tiles (2026-10-25):** the Active users / Sessions / Pageviews tiles were 2x2 grid cells with their long
descriptions showing, so the digits were squeezed. On the five overview dashboards (UIUC, OSU, UMD, UofT, All
schools) they are now a row of three 4x3 tiles, Active users first, descriptions hidden, with the rest of the
tiles in two columns below. Layout is set through the dashboard API (`tiles[].layouts`, `show_description`);
re-run that if a dashboard is duplicated.

**Per-school dashboard** (do this one for UIUC now, if you want it before school #2):
1. Open the existing "UIUC Spaces KPIs" dashboard → **Filters** → **+ Add filter** →
   Event property → `school` → `is` → `uiuc` → Save.
2. For each new school: duplicate this dashboard (⋯ → Duplicate), change the filter
   value to that school's `SCHOOL` string. Same charts, no rebuilding.

**Master dashboard** (combined across every school):
1. New dashboard, **no** `school` filter.
2. Single numbers (total visitors, total check-ins) sum across all schools automatically
   with no filter.
3. Comparison charts: add **Breakdown by** → `school` on an insight (e.g. visitors,
   check-ins) to get one line/bar per campus instead of a blended total.

This can only be driven by Claude in the Claude Browser pane if you log into PostHog
there first (it's a separate, logged-out browser context from your normal Chrome) —
otherwise it's faster to just follow these steps yourself in your own Chrome.

## Retention tooling (2026-10-22)

Only ~5% of visitors came back on a second day, and the number understates it: the visitor id is in
localStorage (no cookies, by choice), which every in-app browser keeps separately and Safari clears after
a week unused. Every event now carries `browser_kind` = `installed` | `in-app` | `browser` so return rate
can be read per group; only `installed` (home-screen app) is a trustworthy retention figure.

New events: `spot_saved`, `spot_removed`, `myspot_opened` (the "Your spots" card and the save button in the
building panel, stored in `cq:spots:<campus>` on the device), and `install_nudge_shown` / `_clicked` /
`_dismissed` (property `kind`: prompt | ios | in-app | browser-menu) and `app_installed`. The nudge shows
once in the panel after a second building is opened, phones only, at most 3 times and 14 days apart.
Each campus has its own `manifest-<id>.webmanifest`, written by `scripts/build_campus_pages.py`.

## U of T success scorecard (2026-10-25)

Retention, not reach, is the goal now. Study demand comes in waves (midterms, finals), so success means
people coming back the next time they need to study, not daily use.

**Targets, written before looking at any data** (judge them at week 4, ~2026-11-22, and after U of T exams,
Dec 10–22):

1. **Week-1 return** for the U of T launch cohort (first seen from 2026-10-25) is above Illinois, Ohio State and
   Maryland at the same age. Only the `installed` row is a trustworthy figure; `browser` and `in-app` understate
   it because their storage is wiped or kept separately.
2. **Study-sheet users return measurably more than map-only users**: at least 1.5x the map-only return rate,
   on at least 30 sheet users.
3. **Launch-week users reappear during U of T exams in December** (Dec 10–22) without a new Reddit post:
   at least 5% of the launch-week cohort seen again in that window.
4. **Direct / no-referrer share of U of T pageviews rises week over week** after the launch week (habit
   replacing the Reddit spike).
5. **Hours reports are mostly "correct"**: at least 80% `correct` overall, and no `basis` below 60% on 10+ reports.

New events in this round:

| Event | When | Properties |
|---|---|---|
| `exam_banner_shown` / `_clicked` / `_dismissed` | Exam-season line at the top of the study sheet, 14 days before and during finals | `period`, `phase` (before / during), `days_left`, `device` |
| `lapsed_return` | A visitor back after 7+ days away (last visit from `cq:lastVisit` or PostHog's own `$sesid` timestamp) | `gap_days`, `device` |

**Exam banner:** dates live in `CAMPUS_CONTENT.<campus>.exams` in app.js, each with its official source in a
comment. Finals only: no campus publishes campus-wide midterm dates. Fall 2026: Illinois Dec 11–17, Ohio State
Dec 11–17, Maryland Dec 14–21, U of T Dec 10–22. Shown at most once a day, and never again in a period once
dismissed (`cq:exam:<campus>` in localStorage). Clicking expands the sheet on its Open now tab. **Add the Winter
2027 dates in January** or it goes quiet until then.

**Lapsed-returner survey:** surveys are on in posthog init (`disable_surveys: false`) and in the project
(`surveys_opt_in`); session recording stays off and persistence stays `localStorage`, so still no cookies (checked:
`document.cookie` empty after the survey showed; its state is `seenSurvey_<id>` / `lastSeenSurveyDate` in
localStorage). Survey `01a17694-dff2-0000-6f66-a10c8afd3527` ("Lapsed returners: what would make you use it
more?", popover, one single-choice question with an open "Other", shuffled), triggered by `lapsed_return`, once per
person, phones and desktop. The site's own return-intent prompt stands down on that visit so nobody gets two
questions. Trap: this posthog-js only fetches flags when asked, and the survey's built-in "not answered yet"
targeting flag is a flag, so app.js calls `reloadFeatureFlags()` and waits for flags + surveys before sending
`lapsed_return`; without that the survey activated and never showed. The event only starts firing 7 days after
someone's last visit, so expect the first responses around 2026-11-01, mostly from installed or Chrome visitors
(Safari wipes the storage it relies on after 7 days).

**Scorecard tiles** (all SQL tables on "UofT Spaces — launch health", 2259538, each verified to return rows on
2026-10-26):

| Tile | Insight | Answers target |
|---|---|---|
| Scorecard 1: launch-week return, week 1 and week 4, by campus and browser | `LyzfaBne` (13289070) | 1 |
| Scorecard 2: do study-sheet users come back more than map-only? | `f4xf7lt0` (13289071) | 2 |
| Scorecard 3: direct / no-referrer share of pageviews, by week | `xcucqQdj` (13289072) | 4 |
| Scorecard 4: hours reports, how often was the map right? (by basis) | `1SqBkpsk` (13289073) | 5 |
| Scorecard 5: do UofT launch-week visitors come back for December exams? | `0kluHSH9` (13289085) | 3 |

Launch days used for "same age": Illinois 2026-09-23 (ids persisted from then), Maryland 2026-10-21, U of T
2026-10-25, Ohio State 2026-10-26 (planned). Pageviews before mid-October carry no `school` and count as Illinois;
`browser_kind` only exists from 2026-10-22, so Illinois' and most of Maryland's launch cohorts read "untagged".
Days are in the project timezone (Chicago), an hour off Toronto.

## Notes

- Watch events arrive live under **Activity** in the left sidebar.
- Free plan covers 1M events/month.
- The site footer says "Anonymous usage stats help improve this map."
