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

## Notes

- Watch events arrive live under **Activity** in the left sidebar.
- Free plan covers 1M events/month.
- The site footer says "Anonymous usage stats help improve this map."
