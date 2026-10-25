# The "Find a study spot" sheet, on every campus (2026-10-24)

One sheet, up to four tabs, each shown only where the campus publishes the data
(`CAMPUS_CONTENT.hubTabs` in app.js). Nothing here is inferred; every source is the
university's own.

| Campus | Tabs | Rooms | Quiet | Late-night note (9pm on) |
|---|---|---|---|---|
| Illinois | Open now, Quiet | none, by the owner's choice (Illini Spots) | 29 spaces, the Library's Study Spaces Directory, rated on its own 1-4 "Expected Volume" scale | SafeWalks, 9pm-2:30am daily, 217-333-1216 (police.illinois.edu/safewalks) |
| Ohio State | none (late-night note only) | 7 Health Sciences Library rooms (LibCal); Thompson/18th Ave book behind a login | none: no published noise ratings | Lyft Ride Smart, $4 off, 7pm-7am (ttm.osu.edu/ride-smart) |
| Maryland | Open now, Quiet | 96 rooms in 4 libraries (LibCal, with its Outlets / Accessible tags) | 23 walk-in spaces from lib.umd.edu space pages: Silent / Quiet / Collaborative + outlets | NITE Ride, 5:30pm-7:30am, Terp Ride app or 301-314-3687 (transportation.umd.edu) |
| U of T | Open now, Quiet, Computers | 139 rooms (in the Study rooms sidebar) | 24 areas | TravelSafer, 24/7 |

Computers: only U of T publishes live counts. Maryland's table (lib.umd.edu/visit/tech/computers)
is totals only; Illinois and Ohio State publish nothing live.

Data, re-run once a term:
- `node scripts/build_study_rooms.mjs osu|umd|utsg` -> `data/<campus>/study_rooms.json`
- `python3 scripts/build_library_areas.py uiuc|umd` -> `data/library_spaces.json`, `data/umd/library_spaces.json`
  (lib.umd.edu refuses requests without browser headers; the script sends them.)

Placement checks: Illinois' MPAL is in the Music Building (its page: "W. Oregon St. side of the
Music Building"), not Krannert; the Communications Library is in Gregory Hall; Oak Street (off
campus) is left out. Maryland's "Undergraduate Library" is Hornbake.

The "Not built yet" wish buttons for Quiet/group and Outlets disappear on a campus that now has them.

2026-10-25: the Rooms tab was removed on every campus at the owner's request (it overlapped the sidebar). Library room counts still show on each building's panel.
