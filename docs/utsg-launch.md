# Launching U of T

State 2026-10-21: everything is built and checked locally. Nothing is pushed.

## Two branches, on purpose

- `uoft` -- the build: data, scripts, `utsg.html`, the rooms API entry, the workflow step.
  Merging this ALONE makes `campusquiet.com/utsg` exist but unlinked (Ohio State sat like
  that for 11 days).
- `uoft-launch` -- branched from `uoft`, adds the three public edits: the picker card and
  remembered-campus redirect in `index.html`, and the `sitemap.xml` entry.
  **Launching = merging `uoft-launch` into `main` and pushing.** Both branches come with it.

## Before pushing, once

1. `python3 scripts/build_utsg_hours.py` -- the library window rolls (84 days from the
   run), so a fresh pull on launch day is free. Commit the result.
2. `app.js?v=149` is already bumped in every page.
3. Optional: retake `utsg-preview.png` at full size. The current one is upscaled from an
   800 px capture and shows Tuesday 11 am.

After the push, Vercel deploys in about a minute. Check `/utsg`, `/api/rooms?campus=utsg`,
and the picker card. The weekly workflow starts refreshing U of T hours on its own.

## Not done, on purpose
- **PostHog dashboards** (per-school, master `utsg` column): only when asked.
- A Winter 2027 sweep (session `20271`) and calendar: before January.
- Hours for Bahen, Myhal, Sidney Smith, OISE: nothing official exists; see `docs/utsg.md`.

## Draft post (r/UofT) -- yours to edit and send

> **I built a live 3D map of how busy St. George buildings are (UofT Spaces)**
>
> campusquiet.com/utsg -- pick a building, see whether it's usually quiet or packed right
> now, and what time it closes.
>
> How it works, so you know what to trust: busyness comes from the real Fall timetable
> (actual enrolment, class by class), not sensors, so it shows how much *teaching* is
> happening, not who is quietly studying. Robarts, Gerstein, the Athletic Centre and Hart
> House use their published hours; for everything else it estimates from when classes meet
> and says so ("probably closed"). Where hours are wrong or a building's missing, there's a
> "something look wrong?" button on every building -- that's how it gets better.
>
> Student project, not affiliated with U of T. Feedback welcome, especially which buildings
> you actually study in.

(Per the owner's earlier note, the Reddit post is the whole launch, and Illinois' traffic
spiked and died in a day, so post at a moment of real need: reading week is 26-30 Oct,
midterm/finals season after.)
