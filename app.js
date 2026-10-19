// ─── UIUC Spaces ──────────────────────────────────────────────────────────────
// Busyness comes from several sources, best first:
//   1. reported  — student check-ins from the last couple of hours
//   2. measured  — Google popular times (data/popular_times.json, via SerpApi)
//   3. estimated — class schedules (data/class_activity.json, Course Explorer)
//   4. typical   — a generic pattern for the building type (libraries, gym…)
// A building with none of these stays grey and shows nothing. Never guess.

// ─── Anonymous usage stats (PostHog) ──────────────────────────────────────────
// Off until ANALYTICS.key is filled in. No personal data, no cookies, and the
// script only loads after the map is up so it can't slow the first view.
const ANALYTICS = {
  key: 'phc_pTDiskU8X4GkZisJH9byyKWbRnWv6tyLCZuJfZ6KTpQx',   // project API key (public by design)
  host: 'https://us.i.posthog.com',                          // US region
};

const analyticsQueue = [];
let analyticsReady = false;

// Visit once with ?nostats=1 (e.g. bookmark it) to exclude this browser from
// analytics from then on, even on the plain URL — handy so your own testing
// doesn't skew the data. ?nostats=0 turns tracking back on.
const NOSTATS_KEY = 'uiucSpacesNoStats';
(() => {
  const params = new URLSearchParams(location.search);
  if (!params.has('nostats')) return;
  try {
    if (params.get('nostats') === '0') localStorage.removeItem(NOSTATS_KEY);
    else localStorage.setItem(NOSTATS_KEY, '1');
  } catch (e) { /* private browsing, storage disabled, etc. */ }
})();
function analyticsExcluded() {
  try { return localStorage.getItem(NOSTATS_KEY) === '1'; } catch (e) { return false; }
}

// Which layout this page is. On every event, so "did the people who saw the
// new one come back more" and "did anyone who switched back stay there" are
// both answerable — the second needs the label to persist past the click.
const DESIGN = 'new';

// Which school an event belongs to is the campus the page is showing (CAMPUS.id,
// registered below), so one PostHog project holds every school: filter a
// dashboard to `school = osu` for one campus, or leave it unfiltered (optionally
// broken down by `school`) for a combined view. It used to be a hardcoded
// constant, which tagged every Ohio State event as Illinois.

/** Record an event, e.g. track('checkin_submitted', { building, level }). */
function track(event, properties = {}) {
  if (!ANALYTICS.key || analyticsExcluded()) return;
  if (!analyticsReady) { analyticsQueue.push([event, { design: DESIGN, ...properties }]); return; }
  try { window.posthog?.capture(event, { design: DESIGN, ...properties }); } catch (e) { /* never break the map */ }
}

function startAnalytics() {
  if (!ANALYTICS.key || analyticsReady || analyticsExcluded()) return;
  const script = document.createElement('script');
  script.async = true;
  script.src = `${ANALYTICS.host}/static/array.js`;
  script.onload = () => {
    window.posthog.init(ANALYTICS.key, {
      api_host: ANALYTICS.host,
      // A random id kept in localStorage, not a cookie — so still no cookie
      // banner, and it identifies nobody. With 'memory' the id was reborn on
      // every page load, which made one student reloading look like several
      // visitors and made return visits impossible to see at all.
      persistence: 'localStorage',
      autocapture: false,            // only the events below
      // Recording phones only, and only for now: phone visitors tap ~1.7
      // buildings per visit but check in on far fewer of them than people on
      // a computer do, and event counts can't show whether that's fumbled
      // taps or genuine browsing. Watching a few sessions can. Turn this back
      // off (or set it to true) once that question is answered.
      // Was on for phones only, to find out whether taps were missing their
      // target on the redesign. They were not -- the replays showed taps
      // landing and no rage-clicking -- so it is off again. Turning it back on
      // needs a question it can answer.
      disable_session_recording: true,
      disable_surveys: true,
      respect_dnt: true,
      capture_pageview: true,
      capture_pageleave: true,       // gives time-on-site
      person_profiles: 'never',
      // Registered so the automatic pageview and pageleave carry it too.
      loaded: ph => ph.register({ design: DESIGN, school: CAMPUS.id }),
    });
    analyticsReady = true;
    for (const [event, props] of analyticsQueue.splice(0)) track(event, props);
  };
  script.onerror = () => { analyticsQueue.length = 0; };
  document.head.append(script);
}

function deviceKind() {
  return window.matchMedia('(pointer: coarse)').matches || window.innerWidth < 700 ? 'phone' : 'computer';
}

// Cesium's servers use HTTP/2, so many requests can run at once.
Cesium.RequestScheduler.maximumRequestsPerServer = 40;

// Restricted token: only terrain + OSM buildings, only from this site.
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6InA4R09NOEdDQ19oS19qby0iLCJqdGkiOiI1Mjc5NDQ0NC05OTQyLTQ4ODUtYTNkNy1hN2M3Yzc5ODBmMjgiLCJpZCI6NDkzNDU4LCJzdWIiOiJ0cmlzdGFueiIsImlzcyI6Imh0dHBzOi8vYXBpLmNlc2l1bS5jb20iLCJhdWQiOiJVSVVDIFNwYWNlcyBTaXRlIiwiaWF0IjoxNzkxOTU4NTI2fQ.y1DL5h3YE_hi8r4N6m6r7tCMOz8tnFcxg93VON1DwHU';

// ─── Buildings we know something extra about ──────────────────────────────────
// Keyed by the building's EXACT OpenStreetMap name.
//   type          — picks the fallback busyness pattern
//   peakFullness  — how full this building gets at its busiest hour (0–1).
//                   Turns "busy for this building" into something comparable
//                   between buildings.
// Opening hours are NOT set here: they come only from official published
// hours in data/building_hours.json (scripts/build_hours.py).

// ─── Campuses ─────────────────────────────────────────────────────────────────
// Everything that differs between campuses lives here. The rest of this file
// reads the plain constants below it (AREA, CAMPUS_TZ, BUILDINGS …), which are
// resolved from the selected campus, so adding a campus never means touching
// the map, the estimates or the picks.
//
// ?campus=osu switches campus. Illinois stays the default: the link people have
// is the Illinois map, and a stray query string must never change what it shows.
const CAMPUS_SITES = {
  uiuc: {
    id: 'uiuc',
    title: 'UIUC Spaces',
    subtitle: 'University of Illinois Urbana-Champaign',
    disclaimerRest: ' · not affiliated with the University of Illinois',
    tz: 'America/Chicago',
    dataDir: 'data',
    area: { west: -88.33, south: 40.06, east: -88.16, north: 40.16 },
    center: { lon: -88.2270, lat: 40.1065, height: 220 },
    view: { pitchDeg: -25, range: 2200 },
    viewNarrow: { pitchDeg: -42, range: 1700 },
    // Ellipsoid height of the ground, sampled from Cesium's terrain at the
    // campus centre. Not sea level — Cesium works in ellipsoid heights.
    groundM: 190,
  },
  osu: {
    id: 'osu',
    title: 'Ohio State Spaces',
    subtitle: 'The Ohio State University — Columbus',
    disclaimerRest: ' · not affiliated with The Ohio State University',
    // Columbus is Eastern, Champaign is Central. Getting this wrong shifts every
    // estimate by an hour and reads as bad data rather than a config mistake.
    tz: 'America/New_York',
    dataDir: 'data/osu',
    // Centred on the median of the buildings we actually hold data for
    // (-83.0152, 40.0004 — essentially the Oval), not on a landmark picked by
    // hand. An earlier version used OpenStreetMap's "The Ohio State University"
    // relation for the bounds; that is the university's PROPERTY, including the
    // medical centre, research park and airfield, and the academic campus filled
    // only 5.5% of it, so the map was mostly grey city.
    //
    // AREA clamps the CAMERA, not the point it looks at. At HOME_VIEW's -25°
    // pitch and 2200 m range the camera sits ~0.018° of latitude behind the
    // target (0.018° of latitude, 0.023° of longitude), so the box has to reach
    // that far past the OUTERMOST buildings on every side — otherwise panning to
    // look at an edge building shoves the view back, which is what made the map
    // stop dead at the bottom of the screen.
    area: { west: -83.063, south: 39.974, east: -82.984, north: 40.025 },
    center: { lon: -83.0152, lat: 40.0004, height: 220 },
    // Steeper and closer than Illinois. Ohio State's academic core is compact
    // and sits in a dense city grid, so the Illinois angle spent the top fifth
    // of the screen on sky and the right half on blocks of Columbus that will
    // never have data. Looking down harder fills the frame with campus.
    view: { pitchDeg: -38, range: 1700 },
    viewNarrow: { pitchDeg: -50, range: 1300 },
    groundM: 196,
  },
  umd: {
    id: 'umd',
    title: 'Maryland Spaces',
    subtitle: 'University of Maryland — College Park',
    disclaimerRest: ' · not affiliated with the University of Maryland',
    tz: 'America/New_York',
    dataDir: 'data/umd',
    // Measured, not estimated. The 60 class buildings the register can place
    // span -76.9549..-76.9335 and 38.9821..39.0069, and AREA clamps the CAMERA
    // rather than its target: at -38 degrees and 1500 m the camera sits 1182 m
    // behind the point it looks at, which here is 0.0106 of latitude and
    // 0.0137 of longitude. Every side is padded by that much past the
    // outermost building, which is what stops panning to an edge building
    // shoving the view back.
    area: { west: -76.971, south: 38.970, east: -76.918, north: 39.019 },
    // Median of the buildings we hold data for, which lands on McKeldin Mall.
    center: { lon: -76.9427, lat: 38.9883, height: 220 },
    // College Park's academic core is 1.9 km by 1.3 km -- tighter than either
    // other campus -- so this sits closer than Columbus' 1700.
    view: { pitchDeg: -38, range: 1500 },
    viewNarrow: { pitchDeg: -50, range: 1200 },
    // Sampled from Cesium's terrain at all 60 placed buildings on 2026-10-19:
    // median 3.4 m, and the method checks out against the other two campuses
    // (it returns 195.9 for Columbus and 189.7 for Illinois, both configured
    // from the same sampling).
    //
    // UNLIKE the other two, this campus is NOT flat. Illinois varies by about
    // 3 m; here the 60 buildings run from -12.8 m (A. James Clark Hall) to
    // +20.7 m (the Education Building), a 33 m spread. One ground height is
    // therefore a compromise rather than a fact, and labels at the extremes
    // sit up to ~17 m off. Per-building sampling is the real fix if that ever
    // reads badly on screen.
    groundM: 3,
  },
};

// Each campus has its own page (osu.html, built by scripts/build_campus_pages.py)
// which states which one it is, so the shareable URL is /osu rather than a query
// string. ?campus= still works, for trying a campus out before it has a page.
const CAMPUS = CAMPUS_SITES[document.documentElement.dataset.campus]
  ?? CAMPUS_SITES[new URLSearchParams(location.search).get('campus')]
  ?? CAMPUS_SITES.uiuc;

// The page ships with the Illinois name in the markup so the default view and
// its search listing need no JavaScript to read correctly; only a non-default
// campus rewrites them.
// The subtitle is left alone: updateHeader() rewrites it on every refresh and
// now falls back to CAMPUS.subtitle, so setting it here would only be undone.
if (CAMPUS.id !== 'uiuc') {
  document.title = CAMPUS.title;
  const h1 = document.querySelector('#header h1');
  if (h1) h1.textContent = CAMPUS.title;
  // Naming the wrong university in a non-affiliation notice is worse than
  // having none, so this follows the campus too.
  //
  // Only the tail is written, and only into the .d-rest span. Setting
  // textContent on the whole .disclaimer used to be how this worked, which
  // silently deleted that span -- and the span is what the phone stylesheet
  // hides to stop the notice wrapping to a second line. The CSS fix was there
  // all along; this line was removing the thing it acts on, so on a phone the
  // words "not affiliated with The Ohio State University" sat underneath the
  // stats chips, which have z-index 100.
  const rest = document.querySelector('#header .disclaimer .d-rest');
  if (rest) rest.textContent = CAMPUS.disclaimerRest;


}

// Remember which campus this person uses, so campusquiet.com can send them
// straight back to it instead of showing the picker every visit. Only a page
// that is really a campus records it: ?campus= on an unfinished one should not
// become what they are sent to next time.
try {
  if (document.documentElement.dataset.campus || CAMPUS.id === 'uiuc') {
    localStorage.setItem('cq-campus', CAMPUS.id);
  }
} catch (e) { /* storage blocked: they just see the picker next time */ }

const BUILDINGS_UIUC = {
  "Main Library":                     { type: "library", peakFullness: 0.95 },
  "Grainger Engineering Library":     { type: "library", peakFullness: 0.95 },

  // Long official names crowd out their neighbours on the map, so these show a
  // shorter form of the same name. Tooltips still show the full name.
  "Steven S. Wymer Hall":                            { label: "Wymer Hall", labelPriority: 1 },
  "University of Illinois College of Law":           { label: "College of Law" },
  "Graduate School of Library and Information Science": { label: "Information Sciences" },
  "Veterinary Medicine Basic Sciences Building":     { label: "Vet Med Basic Sciences" },
  "Literatures, Cultures & Linguistics Building":    { label: "Literatures & Linguistics" },

  // BIF's atrium is a hangout spot: people stay 15 min – 2 h after class to
  // talk and study, so the building doesn't empty out when classes do. The
  // site owner's description of a typical day (which already reflects that)
  // is used instead of the class schedule.
  "Business Instructional Facility": {
    type: "atrium",
    label: "BIF",
    pattern: {
      // [from, to, level] in hours; 9.5 = 9:30am
      monday:    [[0, 9.5, "quiet"], [9.5, 10.5, "okay"], [10.5, 15.5, "busy"], [15.5, 17.5, "okay"], [17.5, 24, "quiet"]],
      tuesday:   [[0, 9.5, "quiet"], [9.5, 10.5, "okay"], [10.5, 15.5, "busy"], [15.5, 17.5, "okay"], [17.5, 24, "quiet"]],
      wednesday: [[0, 9.5, "quiet"], [9.5, 10.5, "okay"], [10.5, 15.5, "busy"], [15.5, 17.5, "okay"], [17.5, 24, "quiet"]],
      thursday:  [[0, 9.5, "quiet"], [9.5, 10.5, "okay"], [10.5, 15.5, "busy"], [15.5, 17.5, "okay"], [17.5, 24, "quiet"]],
      friday:    [[0, 24, "quiet"]],
      saturday:  [[0, 24, "quiet"]],
      sunday:    [[0, 24, "quiet"]],
    },
  },
  "Funk Library":                     { type: "library", peakFullness: 0.85 },
  "Illini Union":                     { type: "union",   peakFullness: 0.80 },
  "Illini Union Bookstore":           { type: "union",   peakFullness: 0.60 },
  "Activities and Recreation Center": { type: "rec",     peakFullness: 0.85 },
  "Campus Recreation Center East":    { type: "rec",     peakFullness: 0.80 },
  "Student Dining and Residential Programs (SDRP)": {
    type: "study",
    peakFullness: 0.80,
    // Centre of the east wing (the part not drawn as the dining hall), so the
    // label sits over SDRP's own area.
    labelAt: [-88.234758, 40.103672],
    label: "SDRP",   // the building's short name in OpenStreetMap (loc_name)
  },

  // The west part of the SDRP building, including the round section. OpenStreetMap
  // draws it as part of SDRP's outline, so we draw our own shape on top. The
  // outline follows SDRP's real edges (west, north and the curved south side)
  // and is cut straight at the east end of the curve; SDRP keeps the east wing.
  // Heights are metres above the ellipsoid, like the building tiles: SDRP's
  // roof is at ~198 m and its base ~192 m; the hall is drawn a little taller so
  // the two roofs never flicker against each other.
  "Ikenberry Dining Hall": {
    type: "dining",
    peakFullness: 0.90,
    shape: {
      baseM: 191.5,
      topM: 201,
      outline: [
      [-88.2350252, 40.1039745], [-88.2350669, 40.1039752], [-88.2357347, 40.1039715],
      [-88.235732, 40.1039442], [-88.2358503, 40.1039448], [-88.2358496, 40.1038348],
      [-88.2358031, 40.103831], [-88.2358045, 40.1037131], [-88.2358052, 40.1036972],
      [-88.2359167, 40.1036843], [-88.2359144, 40.103506], [-88.2358571, 40.1035159],
      [-88.2358395, 40.1034737], [-88.2358174, 40.1034347], [-88.2357851, 40.1033973],
      [-88.235731, 40.1033505], [-88.2356871, 40.1033228], [-88.2356398, 40.1032978],
      [-88.2355965, 40.1032814], [-88.2355494, 40.1032698], [-88.2355357, 40.103303],
      [-88.2355195, 40.1032977], [-88.2354684, 40.1032901], [-88.2354121, 40.1032857],
      [-88.2353625, 40.1032869], [-88.2353206, 40.1032905], [-88.2352855, 40.1032974],
      [-88.235242, 40.103309], [-88.2352097, 40.1033211], [-88.2351761, 40.1033343],
      [-88.2351419, 40.1033525], [-88.2351153, 40.1033709], [-88.2350979, 40.1033882],
      [-88.2350808, 40.103401], [-88.2351109, 40.103425], [-88.2351023, 40.1034305],
      [-88.2350929, 40.1034376], [-88.2350705, 40.1034654], [-88.2350508, 40.1034949],
      [-88.2350358, 40.1035273], [-88.2350284, 40.1035498], [-88.2350232, 40.1035704],
      ],
    },
  },

  // Cesium's building tileset is missing Morrill Hall entirely — its neighbours
  // and the corridor to Burrill Hall are there, then a hole — so we draw it.
  // The outline is the real footprint from OpenStreetMap (way 137759342), the
  // same source as the rest of the buildings. Neither OSM nor Wikidata records
  // a height, so the box is sized off the ground and its attached neighbour:
  // terrain here is ~187.5–188.8 m and Burrill Hall's roof ~206 m, so this sits
  // a little lower, as a four-storey building next to a taller one. No `type`,
  // so it shows as "no data" rather than inventing a busyness pattern.
  "Morrill Hall": {
    shape: {
      baseM: 187,
      topM: 203,
      outline: [
      [-88.2245567, 40.109095], [-88.2245539, 40.1089519], [-88.2245527, 40.1088938],
      [-88.2241221, 40.1089004], [-88.2241179, 40.1086524], [-88.2246221, 40.1086475],
      [-88.2246221, 40.1086296], [-88.2246219, 40.1085198], [-88.2246218, 40.1084202],
      [-88.2246573, 40.1084201], [-88.2246594, 40.1085193], [-88.2246617, 40.108629],
      [-88.2246621, 40.1086484], [-88.2249353, 40.108645], [-88.2249369, 40.1087223],
      [-88.2250002, 40.1087215], [-88.2250012, 40.1087632], [-88.2249383, 40.108764],
      [-88.22494, 40.1088452], [-88.2246752, 40.1088513], [-88.2246743, 40.1088901],
      [-88.2246502, 40.1088908], [-88.2246501, 40.1089505], [-88.2246558, 40.1090943],
      ],
    },
  },

  // A building can also be split into spaces without drawing anything, e.g.
  //   "Illini Union": { spaces: { "Food court": { type: "dining" }, ... } },
  // Each space gets its own estimate, hours and check-ins, listed in the tooltip.
};

// How full each described level is (same scale as the tooltip's status words).
const PATTERN_LEVELS = { quiet: 0.2, okay: 0.5, busy: 0.72, packed: 0.9 };
const PATTERN_RAMP_H = 0.25;   // ease between levels over ~15 minutes

const DEFAULT_PEAK_FULLNESS = {
  library: 0.95, union: 0.80, rec: 0.85, dining: 0.90, study: 0.80, academic: 0.70,
};

// Spaces are addressed as "Building › Space"; plain buildings by their name.
const SPACE_SEP = ' › ';
const spaceId = (building, space) => building + SPACE_SEP + space;

function configFor(id) {
  if (BUILDINGS[id]) return BUILDINGS[id];
  const i = id.indexOf(SPACE_SEP);
  if (i < 0) return undefined;
  return BUILDINGS[id.slice(0, i)]?.spaces?.[id.slice(i + SPACE_SEP.length)];
}

function spacesOf(building) {
  return Object.keys(BUILDINGS[building]?.spaces || {});
}

// Typical share-of-peak by hour for buildings with no class or Google data.
// Rough shapes, clearly labelled as estimates in the UI.
const TYPE_PROFILES = {
  library: {
    // overnight values only matter for libraries that stay open (24/5)
    weekday:  [.25,.18,.12,.08,.05,.05,.05,.15,.3,.5,.65,.75,.8,.85,.9,.95,.9,.85,.8,.85,.9,.85,.6,.3],
    saturday: [0,0,0,0,0,0,0,.05,.15,.3,.45,.55,.6,.65,.65,.6,.55,.5,.5,.55,.6,.55,.4,.2],
    sunday:   [0,0,0,0,0,0,0,.05,.1,.2,.35,.5,.6,.7,.8,.85,.85,.85,.85,.9,.95,.9,.65,.35],
  },
  rec: {
    weekday:  [0,0,0,0,0,.1,.35,.5,.45,.4,.4,.45,.5,.5,.5,.55,.7,.9,1,.95,.8,.6,.3,.1],
    saturday: [0,0,0,0,0,0,.1,.2,.35,.5,.6,.65,.6,.5,.45,.4,.4,.45,.5,.45,.35,.2,.1,0],
    sunday:   [0,0,0,0,0,0,.05,.15,.25,.4,.5,.55,.55,.5,.5,.55,.65,.75,.8,.75,.6,.4,.2,.05],
  },
  // Meal rushes, with people staying to study in between and after dinner
  dining: {
    weekday:  [0,0,0,0,0,0,0,.35,.45,.3,.35,.8,1,.75,.4,.35,.45,.85,.95,.6,.45,.4,.25,0],
    saturday: [0,0,0,0,0,0,0,0,.15,.3,.45,.7,.8,.6,.35,.3,.4,.7,.75,.45,.3,.25,.15,0],
    sunday:   [0,0,0,0,0,0,0,0,.15,.35,.55,.8,.85,.6,.35,.35,.45,.8,.9,.6,.45,.4,.25,0],
  },
  // Study lounges: steady through the day, busiest in the evening
  study: {
    weekday:  [.15,.1,.05,0,0,0,0,.1,.2,.3,.4,.45,.45,.5,.55,.55,.55,.6,.7,.85,1,.95,.7,.35],
    saturday: [.1,.05,0,0,0,0,0,0,.1,.15,.25,.3,.35,.35,.35,.35,.35,.35,.35,.4,.4,.35,.25,.15],
    sunday:   [.1,.05,0,0,0,0,0,0,.1,.15,.25,.35,.45,.5,.55,.6,.65,.7,.75,.85,.95,.9,.7,.35],
  },
  union: {
    weekday:  [0,0,0,0,0,0,.05,.2,.4,.55,.7,.85,1,.95,.85,.8,.75,.65,.55,.5,.4,.3,.15,.05],
    saturday: [0,0,0,0,0,0,0,.1,.2,.3,.4,.55,.6,.6,.55,.5,.45,.4,.35,.3,.25,.2,.1,0],
    sunday:   [0,0,0,0,0,0,0,.1,.2,.3,.4,.5,.55,.55,.5,.5,.45,.45,.4,.35,.3,.2,.1,0],
  },
};

// ─── Student check-ins ────────────────────────────────────────────────────────
// Reports are shared through Supabase once CHECKINS is filled in (see
// scripts/supabase_setup.sql). Until then — or whenever the network fails —
// they fall back to this browser only.
const CHECKINS = {
  url: 'https://iyupkweuluwewsfbnizj.supabase.co',
  anonKey: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Iml5dXBrd2V1bHV3ZXdzZmJuaXpqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk3NTQ2ODIsImV4cCI6MjEwNTMzMDY4Mn0.mzQO19Xr6qpoi6ab363nPtqh_ctIrdOOS6J5MlGIlr8',
};
const CHECKINS_POLL_MS = 60 * 1000;   // pick up other people's reports
const CHECKIN_LEVELS = { quiet: 0.2, okay: 0.55, packed: 0.9 };
const CHECKIN_FRESH_MIN = 30;   // full weight up to here
const CHECKIN_MAX_MIN   = 120;  // ignored after this
const CHECKIN_TRUST_HALF = 2;   // fresh reports needed before they outweigh the estimate
const CHECKIN_SURPRISE_SPAN = 0.35;     // deviation from the usual value that maxes out the discount
const CHECKIN_SURPRISE_STRENGTH = 2.5;  // how hard a lone report against the usual pattern gets discounted

// ─── Academic calendar ────────────────────────────────────────────────────────
// From https://registrar.illinois.edu/fall-2026-academic-calendar/
// Class-schedule estimates only apply on instruction days. On other days the
// building-type patterns (and Google data) are scaled by CALENDAR_EFFECTS.
const ACADEMIC_CALENDAR_UIUC = {
  term: 'Fall 2026',
  classesStart: '2026-08-24',
  classesEnd:   '2026-12-09',
  termEnd:      '2026-12-17',   // last day of final exams
  periods: [
    { start: '2026-09-07', end: '2026-09-07', kind: 'holiday', label: 'Labor Day — no classes' },
    { start: '2026-11-21', end: '2026-11-29', kind: 'break',   label: 'Fall Break — no classes' },
    { start: '2026-12-10', end: '2026-12-10', kind: 'reading', label: 'Reading day — no classes' },
    { start: '2026-12-11', end: '2026-12-17', kind: 'finals',  label: 'Finals week' },
  ],
};

// How busy each kind of place is compared to a normal class day.
// These are rough judgement calls, not measurements. Classroom buildings aren't
// listed: their estimate comes from the class schedule, which is simply zero
// on days without classes.
const CALENDAR_EFFECTS = {
  normal:  { library: 1,   study: 1,   union: 1,   dining: 1,   rec: 1,   atrium: 1 },
  holiday: { library: 0.8, study: 0.9, union: 0.6, dining: 0.8, rec: 1,   atrium: 0.3 },
  break:   { library: 0.3, study: 0.3, union: 0.3, dining: 0.3, rec: 0.4, atrium: 0.1 },
  reading: { library: 1.2, study: 1.2, union: 1,   dining: 1,   rec: 0.8, atrium: 1.1 },
  finals:  { library: 1.3, study: 1.3, union: 1,   dining: 1,   rec: 0.7, atrium: 1.1 },
  offterm: { library: 0.2, study: 0.2, union: 0.2, dining: 0.2, rec: 0.3, atrium: 0.1 },
};

const CAMPUS_TZ = CAMPUS.tz;
const DAY_NAMES = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'];

// ─── Data loading ─────────────────────────────────────────────────────────────
const data = { classActivity: null, popularTimes: null, hours: null, gis: null, checkins: loadLocalCheckins() };

// Bookable study rooms, from the libraries' own systems via /api/rooms.
// Not part of `data` above: everything there is a file shipped with the site,
// while this is live and allowed to be missing. A campus with no configured
// library simply never fills it, which is why Illinois shows nothing.
let roomAvailability = null;

async function loadRoomAvailability() {
  try {
    const res = await fetch(`/api/rooms?campus=${encodeURIComponent(CAMPUS.id)}`);
    if (!res.ok) return;                       // 404 = campus not configured
    const body = await res.json();
    roomAvailability = body?.buildings ?? null;
    if (panelBuilding) openPanel(panelBuilding, true);   // a panel is already open
  } catch (e) { /* never let a live feed break the map */ }
}

async function loadJson(path) {
  try {
    const res = await fetch(path, { cache: 'no-cache' });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

const sharedCheckins = () => Boolean(CHECKINS.url && CHECKINS.anonKey);

function checkinsEndpoint(query = '') {
  return `${CHECKINS.url.replace(/\/$/, '')}/rest/v1/checkins${query}`;
}

function checkinsHeaders(extra = {}) {
  return { apikey: CHECKINS.anonKey, Authorization: `Bearer ${CHECKINS.anonKey}`, ...extra };
}

/** A random id for this browser, used only to rate-limit reports. */
function browserId() {
  try {
    let id = localStorage.getItem('browser-id');
    if (!id) {
      id = (crypto.randomUUID?.() || String(Math.random()).slice(2) + Date.now().toString(36)).slice(0, 36);
      localStorage.setItem('browser-id', id);
    }
    return id;
  } catch (e) {
    return 'anonymous-' + Math.random().toString(36).slice(2, 10);
  }
}

/** Everyone's reports from the last couple of hours. */
async function fetchSharedCheckins() {
  if (!sharedCheckins()) return;
  const since = new Date(Date.now() - CHECKIN_MAX_MIN * 60000).toISOString();
  try {
    const res = await fetch(
      checkinsEndpoint(`?select=building,level,created_at&created_at=gte.${since}&order=created_at.desc&limit=500`),
      { headers: checkinsHeaders() });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    const rows = await res.json();

    // Server is the source of truth; keep only local reports it hasn't stored
    // yet (just sent, or sent while offline).
    const server = rows.map(r => ({ building: r.building, level: r.level, at: Date.parse(r.created_at) }));
    const seen = new Set(server.map(r => `${r.building}|${r.level}|${Math.round(r.at / 10000)}`));
    const localOnly = data.checkins.filter(r =>
      r.mine && !seen.has(`${r.building}|${r.level}|${Math.round(r.at / 10000)}`));
    data.checkins = [...server, ...localOnly];
    saveLocalCheckins();
    refresh({ keepThanks: true });   // don't wipe a "thanks" message mid-flight
  } catch (e) {
    console.warn('Could not load shared check-ins:', e);
  }
}

/** Send one report. Returns 'ok', 'rate-limited', or 'offline'. */
async function sendCheckin(report) {
  if (!sharedCheckins()) return 'offline';
  try {
    const res = await fetch(checkinsEndpoint(), {
      method: 'POST',
      headers: checkinsHeaders({ 'Content-Type': 'application/json', Prefer: 'return=minimal' }),
      body: JSON.stringify({ building: report.building, level: report.level, browser_id: browserId() }),
    });
    if (res.ok) return 'ok';
    const text = await res.text();
    return /rate limited/i.test(text) ? 'rate-limited' : 'offline';
  } catch (e) {
    return 'offline';
  }
}

function loadLocalCheckins() {
  try {
    return JSON.parse(localStorage.getItem('checkins') || '[]');
  } catch (e) {
    return [];
  }
}

function saveLocalCheckins() {
  try {
    localStorage.setItem('checkins', JSON.stringify(data.checkins.slice(-200)));
  } catch (e) { /* private browsing — reports just won't persist */ }
}

// ─── Time helpers (campus time, not the viewer's) ─────────────────────────────
function campusNow() {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: CAMPUS_TZ, weekday: 'short', hour: 'numeric', minute: 'numeric', hour12: false,
  }).formatToParts(new Date());
  const get = type => parts.find(p => p.type === type)?.value;
  const weekdayIndex = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].indexOf(get('weekday'));
  const hour = Number(get('hour')) % 24;
  return {
    day: DAY_NAMES[weekdayIndex < 0 ? new Date().getDay() : weekdayIndex],
    hour,
    time: hour + Number(get('minute')) / 60,   // e.g. 14.5 = 2:30pm
    // YYYY-MM-DD in campus time
    date: new Intl.DateTimeFormat('en-CA', { timeZone: CAMPUS_TZ }).format(new Date()),
  };
}

/** { kind, label, classesMeet } for a YYYY-MM-DD date. */
function calendarPeriod(date) {
  const cal = ACADEMIC_CALENDAR;
  const special = cal.periods.find(p => date >= p.start && date <= p.end);
  if (special) return { kind: special.kind, label: special.label, classesMeet: false };
  if (date < cal.classesStart || date > cal.termEnd) {
    return { kind: 'offterm', label: `Outside the ${cal.term} semester`, classesMeet: false };
  }
  if (date > cal.classesEnd) return { kind: 'finals', label: 'Finals week', classesMeet: false };
  return { kind: 'normal', label: '', classesMeet: true };
}

function calendarEffect(period, id) {
  const effects = CALENDAR_EFFECTS[period.kind] || CALENDAR_EFFECTS.normal;
  return effects[buildingType(id)] ?? 1;
}

function dayKind(day) {
  if (day === 'saturday') return 'saturday';
  if (day === 'sunday') return 'sunday';
  return 'weekday';
}

// ─── Working out how busy a building is ───────────────────────────────────────
function buildingType(id) {
  return configFor(id)?.type || 'academic';
}

function peakFullness(id) {
  const cfg = configFor(id);
  if (cfg?.peakFullness != null) return cfg.peakFullness;
  return DEFAULT_PEAK_FULLNESS[buildingType(id)] ?? 0.7;
}

// ─── Opening hours (official sources only) ────────────────────────────────────
// Each building in data/building_hours.json has some of:
//   dates    — exact hours for specific days (library/dining seven-day feeds)
//   periods  — hours for a date range (e.g. Fall Break)
//   weekly   — the usual week, used between valid[0] and valid[1]
// Hours are [open, close] pairs in hours of that day; close > 24 runs past
// midnight (2am = 26). Anything not covered is "unknown", never guessed.

function weekdayOf(date) {
  return DAY_NAMES[new Date(date + 'T12:00:00Z').getUTCDay()];
}

function shiftDate(date, days) {
  const d = new Date(date + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Published hours for one building on one date, or null if unknown. */
function publishedRanges(entry, date) {
  if (entry.dates && date in entry.dates) return entry.dates[date];

  const campusClosed = entry.followsCampusClosures
    && (data.hours.campusClosedDates || []).includes(date)
    && !(entry.openDates || []).includes(date);
  if (campusClosed) return [];

  // Days this building alone is shut -- Ohio State's music buildings lock for
  // home football Saturdays, which closes nothing else on campus.
  if ((entry.closedDates || []).includes(date)) return [];

  if ((entry.unknownDuring || []).some(([a, b]) => date >= a && date <= b)) return null;

  const period = (entry.periods || []).find(p => date >= p.start && date <= p.end);
  if (period) return period.weekly[weekdayOf(date)] ?? null;

  if (!entry.valid || date < entry.valid[0]) return null;
  // Published hours stop at the last day of classes, but the term does not: the
  // buildings are open through finals, which is when people most want to know.
  // extendedThrough carries the weekly pattern across that gap rather than
  // going quiet -- see extendedHours() for how it is labelled.
  if (date > entry.valid[1] && !(entry.extendedThrough && date <= entry.extendedThrough)) {
    return null;
  }
  return entry.weekly?.[weekdayOf(date)] ?? null;
}

/** True when this date is past what the source publishes and is being assumed. */
function extendedHours(entry, date) {
  return !!entry.extendedThrough
    && !!entry.valid
    && date > entry.valid[1]
    && date <= entry.extendedThrough
    && !(entry.dates && date in entry.dates);   // real dated hours are not assumed
}

/** { state: 'open' | 'closed' | 'unknown', source } */
// When nobody publishes a building's hours, its own class schedule still says
// something: a room in it is timetabled from 8am to 6pm on a Monday, so on a
// Monday the building is open across that window and almost certainly shut
// outside it. That is the registrar's own schedule rather than a guess about
// this building, and it is the safe direction to be wrong in — it can make the
// map miss somewhere that is quietly open, but it will not send anyone to a
// locked door. It is labelled `assumed` everywhere it shows, and published
// hours always win.
//
// A building's own window is only as wide as the classes the sample happens to
// catch in it: Lincoln Tower shows a single class at 2pm, which made it read
// "probably closed" all morning on a weekday. So the window is never narrower
// than the hours the campus itself is in session (campusClassWindow), which is
// measured from the data rather than set by hand.
const campusWindowCache = {};
function campusClassWindow(day) {
  if (day in campusWindowCache) return campusWindowCache[day];
  // Only buildings with a substantial timetable, and only on days with enough
  // of them to mean "the campus": weekends have a handful, so they get nothing.
  const big = Object.values(data.classActivity?.buildings ?? {})
    .filter(e => e.peak >= 20 && e.hours?.[day]);
  let win = null;
  if (big.length >= 10) {
    // An hour counts when at least half of those buildings have a class in it.
    const active = h => big.filter(e => e.hours[day][h] > 0).length / big.length >= 0.5;
    let first = -1, last = -1;
    for (let h = 0; h < 24; h++) if (active(h)) { if (first < 0) first = h; last = h; }
    if (first >= 0) win = [first, last + 1];
  }
  return (campusWindowCache[day] = win);
}

function assumedHours(id, day) {
  const grid = data.classActivity?.buildings?.[id]?.hours?.[day];
  if (!grid) return null;
  let first = -1, last = -1;
  for (let h = 0; h < grid.length; h++) {
    if (grid[h] > 0) { if (first < 0) first = h; last = h; }
  }
  if (first < 0) return null;         // nothing timetabled: say nothing
  const campus = campusClassWindow(day);
  if (campus) { first = Math.min(first, campus[0]); last = Math.max(last, campus[1] - 1); }
  return [first, last + 1];           // the last class runs to the end of its hour
}

function assumedStatus(id, date, time) {
  const window = assumedHours(id, weekdayOf(date));
  if (!window) return { state: 'unknown' };
  // assumedHours is keyed by weekday, so on a Thursday in a break week it
  // still returns the hours of an ordinary Thursday. The whole basis of this
  // estimate is that classes are meeting; on a day the university says they
  // are not, it cannot be read as open.
  //
  // But "not open" and "closed" are different claims. Where the campus itself
  // publishes a day as no classes with offices open, the doors are very likely
  // unlocked and it is only this estimate that has run out of ground to stand
  // on -- so it says nothing instead of guessing shut. Campuses that publish no
  // such list are unaffected and still read closed, as they did before.
  if ((data.hours?.classesOutDates || []).includes(date)) {
    return { state: 'unknown' };
  }
  // Finals and the reading day before them are the exception that proves the
  // point: no classes meet, and the buildings are at their fullest all term.
  // Until somebody publishes finals-week hours, the ordinary weekday window is
  // the working assumption -- a library reading "probably closed" during finals
  // is the worst answer the map can give.
  const period = calendarPeriod(date);
  const finalsWeek = period.kind === 'finals' || period.kind === 'reading';
  if (!period.classesMeet && !finalsWeek) {
    return { state: 'closed', source: 'assumed from the class timetable', assumed: true };
  }
  const [open, close] = window;
  return {
    state: time >= open && time < close ? 'open' : 'closed',
    source: 'assumed from the class timetable',
    assumed: true,
  };
}

function hoursStatus(id, date, time) {
  const entry = data.hours?.buildings?.[id];
  if (!entry) return assumedStatus(id, date, time);

  // A day with no classes is not a day with locked doors, and the two campuses
  // publish the difference themselves. Ohio State's registrar prints both lists
  // at the top of the hours page -- "University Holidays (no classes, offices
  // closed)" and "Academic Holidays (no classes, offices open)" -- and only the
  // first belongs in campusClosedDates, which publishedRanges applies below.
  // So nothing is decided here from whether classes meet: a building open until
  // 8pm on an ordinary Thursday is open until 8pm on Autumn Break too.

  // Still open from yesterday's late hours (e.g. until 2am)?
  const yesterday = publishedRanges(entry, shiftDate(date, -1));
  if (yesterday && yesterday.some(([, close]) => close > 24 && time < close - 24)) {
    return { state: 'open', source: entry.source };
  }

  const today = publishedRanges(entry, date);
  if (today == null) return assumedStatus(id, date, time);
  const open = today.some(([o, c]) => time >= o && time < c);
  // Past the end of the published schedule the same hours are assumed to hold,
  // but they are no longer a published fact, so they stop being labelled as one.
  const extended = extendedHours(entry, date);
  return {
    state: open ? 'open' : 'closed',
    source: entry.source,
    official: !!entry.sourceUrl && !extended,
    assumed: extended,
    closedNote: extended
      ? 'Probably closed \u00b7 its published hours stop before finals week'
      : undefined,
    cardAccess: !extended && !!entry.cardAccess,
  };
}

/**
 * Summarises recent reports for a building.
 *   value      — age-weighted average of the reports (0–1)
 *   trust      — how much the reports should override the estimate (0–1).
 *                Grows with the number of fresh reports, shrinks when they
 *                disagree, fades as they age, and shrinks when they contradict
 *                the usual pattern for this building/time unless enough
 *                people corroborate the surprise.
 * `base` is the estimate's value (0–1), or null if there is no estimate to
 * compare against.
 */
function freshCheckin(name, base, now = Date.now()) {
  const recent = data.checkins
    .filter(c => c.building === name && (now - c.at) / 60000 < CHECKIN_MAX_MIN)
    .sort((a, b) => b.at - a.at);
  if (!recent.length) return null;

  let total = 0, weightSum = 0;
  const weighted = [];
  for (const report of recent) {
    const ageMin = (now - report.at) / 60000;
    const weight = ageMin <= CHECKIN_FRESH_MIN
      ? 1
      : 1 - (ageMin - CHECKIN_FRESH_MIN) / (CHECKIN_MAX_MIN - CHECKIN_FRESH_MIN);
    const level = CHECKIN_LEVELS[report.level] ?? 0.55;
    total += level * weight;
    weightSum += weight;
    weighted.push([level, weight]);
  }
  const value = total / weightSum;

  // Few reports → low trust: 1 fresh report ≈ 33%, 2 ≈ 50%, 4 ≈ 67%, 8 ≈ 80%.
  // A report (or a few) that goes against the usual pattern for this spot
  // needs more corroboration before it earns the same trust — treat it as
  // if fewer reports had come in, in proportion to how big the surprise is.
  const surprise = base == null ? 0 : Math.min(Math.abs(value - base) / CHECKIN_SURPRISE_SPAN, 1);
  const effectiveWeight = weightSum / (1 + surprise * CHECKIN_SURPRISE_STRENGTH);
  const countTrust = effectiveWeight / (effectiveWeight + CHECKIN_TRUST_HALF);

  // Reports that disagree (some "quiet", some "packed") count for less.
  const variance = weighted.reduce((sum, [level, w]) => sum + w * (level - value) ** 2, 0) / weightSum;
  const spread = Math.sqrt(variance);                 // 0 when all agree, ~0.35 when split
  const agreement = 1 - Math.min(spread / 0.35, 1) * 0.6;

  return {
    value,
    trust: countTrust * agreement,
    ageMin: (now - recent[0].at) / 60000,
    count: recent.length,
    disagree: spread > 0.2,
  };
}

function googleBusyness(name, day, hour) {
  const place = data.popularTimes?.places?.[name];
  const entry = place?.weekly?.[day]?.find(h => h.hour === hour);
  return entry ? entry.busyness / 100 : null;
}

function classBusyness(name, day, hour) {
  const building = data.classActivity?.buildings?.[name];
  if (!building) return null;
  // Seats scheduled, where the campus publishes room capacity. A full lecture
  // hall and a seminar room are not the same amount of building in use, and a
  // count of meetings can't tell them apart. Illinois' course explorer carries
  // no capacity, so it falls back to the meeting count.
  const grid = building.seats ?? building.hours;
  const peak = building.seats ? building.seatsPeak : building.peak;
  if (!peak) return null;
  const value = grid?.[day]?.[hour];
  return value == null ? null : value / peak;
}

// A described pattern ("quiet 6–9:30, busy 10:30–3:30, …") as a fullness value,
// easing between levels.
function patternBusyness(name, day, time) {
  const segments = configFor(name)?.pattern?.[day];
  if (!segments) return null;
  const levelAt = t => {
    const seg = segments.find(([from, to]) => t >= from && t < to);
    return seg ? PATTERN_LEVELS[seg[2]] : null;
  };
  const here = levelAt(time);
  if (here == null) return null;
  const before = levelAt(time - PATTERN_RAMP_H) ?? here;
  const after = levelAt(time + PATTERN_RAMP_H) ?? here;
  return (before + 2 * here + after) / 4;
}

function profileBusyness(name, day, hour) {
  const profile = TYPE_PROFILES[buildingType(name)];
  return profile ? profile[dayKind(day)][hour] : null;
}

/**
 * Returns { value, source, note } or null when we know nothing about it.
 * value is 0–1 fullness; source drives the label shown to the user.
 */
function occupancyFor(name) {
  const estimate = estimateFor(name);
  // With no estimate at all, reports are all we have, so there's nothing to
  // weigh them against. A closed building still gives us a signal though —
  // expected occupancy ~0 — so a report claiming otherwise gets the same
  // outlier scrutiny as any other surprising report, instead of automatically
  // overriding "closed" outright.
  const base = !estimate || estimate.source === 'unknown' ? null : estimate.source === 'closed' ? 0 : estimate.value;
  const checkin = freshCheckin(name, base);
  if (!checkin) return estimate;

  // Blend reports with the estimate.
  const trust = base == null ? 1 : checkin.trust;
  const value = base == null ? checkin.value : base * (1 - trust) + checkin.value * trust;

  const mins = Math.round(checkin.ageMin);
  const reports = checkin.count > 1
    ? `${checkin.count} student reports, newest ${mins} min ago`
    : `1 student report, ${mins} min ago`;
  const detail = checkin.disagree ? ' · reports disagree' : '';

  // Only call it "student reported" once reports outweigh the estimate.
  if (trust >= 0.5) {
    return { value, source: 'reported', note: reports + detail };
  }
  return { value, source: estimate.source, note: `${estimate.note} + ${reports}${detail}` };
}

/**
 * What the map shows for a whole building. For buildings split into spaces,
 * the colour is the average of the spaces that are open, and `spaces` lists
 * each one for the tooltip.
 */
function buildingOccupancy(name) {
  const spaces = spacesOf(name);
  if (!spaces.length) return occupancyFor(name);

  const parts = spaces.map(space => ({ space, occ: occupancyFor(spaceId(name, space)) }));
  const open = parts.filter(p => p.occ && !['closed', 'unknown'].includes(p.occ.source));

  if (!open.length) {
    const allClosed = parts.every(p => p.occ?.source === 'closed');
    return allClosed
      ? { value: 0, source: 'closed', note: 'All spaces closed right now', spaces: parts }
      : { value: 0, source: 'unknown', note: 'Hours not published for these spaces', spaces: parts };
  }

  const value = open.reduce((sum, p) => sum + p.occ.value, 0) / open.length;
  const sources = new Set(open.map(p => p.occ.source));
  const source = sources.size === 1 ? [...sources][0] : 'estimated';
  const note = open.length === parts.length
    ? 'Average of the spaces below'
    : `${open.length} of ${parts.length} spaces open`;
  return { value, source, note, spaces: parts };
}

/** The best estimate without student reports, or null. */
function estimateFor(name) {
  const { day, hour, time, date } = campusNow();
  const peak = peakFullness(name);
  const period = calendarPeriod(date);
  const effect = calendarEffect(period, name);
  const withPeriod = note => period.label ? `${note} · ${period.label}` : note;

  const hours = hoursStatus(name, date, time);
  if (hours.state === 'closed') {
    const from = hours.official ? ` · hours from ${hours.source}` : '';
    // Never let an assumption read like a published fact. "Closed right now"
    // is a claim; "probably closed" with the reason attached is what we can
    // actually support.
    if (hours.assumed) {
      return {
        value: 0,
        source: 'closed',
        assumed: true,
        note: hours.closedNote
          ?? 'Probably closed · nobody publishes hours for it and no classes are scheduled now',
      };
    }
    return {
      value: 0,
      source: 'closed',
      cardAccess: hours.cardAccess,
      note: hours.cardAccess
        ? `Public doors locked · i-card access may still work${from}`
        : `Closed right now${from}`,
    };
  }
  const estimate = estimateWhileOpen(name, day, hour, peak, period, effect, withPeriod, time);

  // A building the university says is OPEN must never read as "no data". It
  // used to: estimateWhileOpen returns null when nothing is timetabled and the
  // building has no type profile, and that null went straight to the map as
  // plain grey. On a Sunday that hid most of the campus -- 10 of the 14
  // buildings open at 7pm on 2026-10-18 were drawn as if nothing were known
  // about them, including Enarson and Hitchcock, which the registrar publishes
  // as open 7am-11pm every day of the week.
  //
  // Nothing timetabled is not nothing known. It is the single most useful
  // thing this map can say: the doors are open and no class is in there. The
  // value is 0 because that is what an empty room is, and the note says
  // exactly where that comes from so it cannot read as a measurement.
  if (hours.state === 'open') {
    if (estimate) return estimate;
    const from = hours.official ? ` · hours from ${hours.source}` : '';
    return {
      value: 0,
      source: 'open',
      note: `Open · nothing timetabled here right now${from}`,
    };
  }
  if (!estimate) return estimate;

  // Hours not published for today: only show a number when classes are
  // actually scheduled there right now (so the building must be open). Typical
  // patterns are guesses and would imply the building is open, so they don't count.
  if (estimate.source === 'estimated' && estimate.value >= 0.03) {
    return { ...estimate, note: `${estimate.note} · building hours not published` };
  }
  // Open only because its own timetable says a class runs through now.
  if (hours.assumed) {
    return estimate
      ? { ...estimate, assumed: true, note: `${estimate.note} · hours assumed from the class timetable` }
      : { value: 0, source: 'unknown', note: 'Opening hours not published for today' };
  }
  return { value: 0, source: 'unknown', note: 'Opening hours not published for today' };
}

function estimateWhileOpen(name, day, hour, peak, period, effect, withPeriod, time = hour) {
  const google = googleBusyness(name, day, hour);
  if (google != null) {
    return {
      value: Math.min(google * peak * effect, 1),
      source: 'measured',
      note: withPeriod('Google popular times · typical for this hour'),
    };
  }

  // No classes meet on breaks, holidays, reading day or during finals.
  // A typical day described by the site owner is first-hand, so it takes
  // priority over the class schedule for that building.
  const described = patternBusyness(name, day, time);
  if (described != null) {
    return {
      value: Math.min(described * effect, 1),
      source: 'typical',
      note: withPeriod('Based on typical activity for this building'),
    };
  }

  const scheduled = classBusyness(name, day, hour);
  const classes = scheduled == null ? null : (period.classesMeet ? scheduled : 0);

  const rawProfile = configFor(name) ? profileBusyness(name, day, hour) : null;
  const profile = rawProfile == null ? null : Math.min(rawProfile * effect, 1);

  // Libraries, the Union and the gyms stay busy outside class hours, so their
  // own pattern wins whenever it says busier than the class schedule does.
  if (classes != null || profile != null) {
    const useProfile = profile != null && (classes == null || profile > classes);
    if (useProfile) {
      return {
        value: Math.min(profile * peak, 1),
        source: 'typical',
        note: withPeriod('Typical pattern for this kind of building'),
      };
    }
    return {
      value: classes * peak,
      source: 'estimated',
      note: period.classesMeet
        ? 'Estimated from class schedules'
        : `No classes scheduled · ${period.label}`,
    };
  }

  return null;
}

function knownBuildings() {
  const names = new Set(Object.keys(BUILDINGS));
  for (const name of Object.keys(data.classActivity?.buildings || {})) names.add(name);
  for (const name of Object.keys(data.popularTimes?.places || {})) names.add(name);
  const away = offMap(names);
  return away.size ? [...names].filter(name => !away.has(name)) : [...names];
}

// Buildings the university's own register places outside the area this map
// covers: Ohio State's airport terminal, a research lab out on west campus, a
// clinic three miles east. They can't be drawn or flown to, so counting them in
// the legend claims the map knows about places it never shows. A building the
// register doesn't carry is left alone — not in the register is not evidence.
const NONE = new Set();
let offMapNames = null;
function offMap(names) {
  if (offMapNames) return offMapNames;
  if (!data.gis) return NONE;          // decide once the register has loaded
  offMapNames = new Set();
  for (const name of names) {
    const b = gisFor(name);
    // Not in the university's own register of this campus at all. The class
    // schedule lists a few buildings that are not here — Ohio State teaches
    // some Columbus-administered classes sixty miles away at Wooster — and
    // without a register entry there is no sourced location to put them at.
    // Showing them anyway risks a tile with a similar name claiming the label,
    // which is a wrong location rather than a missing one.
    if (!b) { offMapNames.add(name); continue; }
    if (b.lon < AREA.west || b.lon > AREA.east || b.lat < AREA.south || b.lat > AREA.north) {
      offMapNames.add(name);
    }
  }
  return offMapNames;
}

// ─── Study picks ──────────────────────────────────────────────────────────────
// Which places a student can actually sit and work in. This list is written out
// by hand on purpose, because ranking the whole map by "least busy" does not
// answer the question: at a Wednesday 2:30pm it returns the Stock Pavilion,
// Spurlock Museum and the National Soybean Research Center, all at 0%. A 0%
// estimate there only means no classes are scheduled in the building — not that
// it's somewhere you can study.
//
// ARC and Ikenberry Dining Hall were considered and cut by the site owner as
// gym and food only. Extend this list rather than trying to infer membership;
// leaving a real study spot out is better than recommending somewhere useless.
// How well-suited each place is to actually sitting and working — purpose-built
// study space, then study-friendly common space, then buildings with lounges
// and empty classrooms. Deliberately NOT how popular or well-known it is: the
// whole value of a recommendation is surfacing somewhere you hadn't thought of,
// and nobody needs an app to be told about Grainger.
//
// The spread is kept narrow (1 / 0.75 / 0.5) so being quiet right now matters
// more than the tier does. A wider spread buries the smaller places entirely,
// which defeats the point. It still has to be a spread rather than nothing: a
// flat weight ranks purely on emptiness, and the type profiles put the
// libraries at 62-86% all day against 0-46% for classroom buildings, so a
// library could then never be recommended at any hour.
const STUDY_SPOTS_UIUC = {
  'Grainger Engineering Library': 1,
  'Main Library': 1,
  'Funk Library': 1,
  'Illini Union': 0.75,
  'Business Instructional Facility': 0.75,
  'Campus Instructional Facility': 0.75,
  'Beckman Institute': 0.75,
  'Smith Memorial Hall': 0.5,
  'Electrical and Computer Engineering Building': 0.5,
  'University of Illinois College of Law': 0.5,
  'Armory': 0.5,
  'Student Dining and Residential Programs (SDRP)': 0.5,
};

// The list scrolls, so this can be generous. More slots is what lets the
// quieter, less obvious places show up alongside the ones everyone knows.
const PICK_COUNT = 6;

// Shorter names for the card only — the map keeps the full ones. Three names
// wrap to three lines each in a column this narrow, which made six picks taller
// than the whole card was before. These are the forms already in use on campus
// and in this file (BIF, SDRP), not invented abbreviations.
const PICK_LABELS_UIUC = {
  'Grainger Engineering Library': 'Grainger Library',
  'Campus Instructional Facility': 'CIF',
  'Electrical and Computer Engineering Building': 'ECEB',
  'University of Illinois College of Law': 'College of Law',
};

// ─── Ohio State content ───────────────────────────────────────────────────────
// Deliberately thin. Illinois' lists were built from local knowledge — which
// buildings are really study spots, which names to shorten — and the same pass
// has to happen for Columbus before the picks card can say anything useful.
// Leaving these empty makes the card show nothing, which is the right answer
// until someone who knows the campus fills them in. Guessing would put students
// in front of a locked door.
// Only the two libraries that are buildings in their own right and publish
// their own hours. Calling a library a library is not a judgement call; which
// classroom buildings students treat as study spots is, and that still needs
// someone who knows the campus.
// Keyed on the name Ohio State's class data uses, because that is what the
// scheduling code joins to; the label is what students call it.
const BUILDINGS_OSU = {
  'Library, Wm Oxley Thompson':    { type: 'library', label: 'Thompson Library' },
  '18th Avenue Library':           { type: 'library', label: '18th Ave Library' },
  'Ohio Union, New':               { type: 'union',   label: 'Ohio Union' },
  // The register and the students call these something shorter than the class
  // data does.
  'Knowlton Architecture Building': { label: 'Knowlton Hall' },
  'Drinko Hall, John Deaver':       { label: 'Drinko Hall' },
  'Ag. Admin.':                     { label: 'Ag Admin' },

  // The two rec centres have no classes in them ever, so without a type they
  // would now read "open, nothing timetabled" -- i.e. empty -- at 7pm on a
  // Sunday, which is the exact hour they are full. A type gives them the rec
  // profile instead, the same one Illinois' ARC and CRCE use.
  'Recreation & Phys Activ Ctr':    { type: 'rec', label: 'RPAC' },
  'Adventure Recreation Center':    { type: 'rec', label: 'ARC' },
};

// Every entry here traces to Ohio State's own list of library locations
// (library.osu.edu/locations), matched to a building through the register's
// addresses — not to a guess about where people like to sit. The tiers mirror
// Illinois: a library is a 1, the union and buildings that contain a library
// are 0.75, and a building whose library we can't yet get hours for is a 0.5.
//
// This is still short. Illinois has twelve, and the rest of that list came from
// knowing the campus — a sourced list can say where the libraries are, but not
// which atrium people actually work in. That part needs an Ohio State student.
const STUDY_SPOTS_OSU = {
  // Libraries first, as at Illinois.
  'Library, Wm Oxley Thompson': 1,     // Thompson, the main library
  '18th Avenue Library': 1,            // also holds the Music & Dance Library
  'Ohio Union, New': 0.75,             // same tier Illinois gives the Illini Union
  'Knowlton Architecture Building': 0.75,  // Architecture Library
  'Orton Hall': 0.75,                  // Geology Library
  'Ag. Admin.': 0.75,                  // FAES Library & Student Success Center
  'Drinko Hall, John Deaver': 0.5,     // Law Library -- no published building hours yet

  // Everything below was chosen from the registrar's published hours, not from
  // a guess about where people like to sit. The rule: at least 60 open hours a
  // week, and then either open all seven days (0.75) or carrying at least 30
  // timetabled seats at peak (0.5).
  //
  // The old list was libraries only, which is why this campus went nearly dark
  // at weekends -- Enarson is open 7am to 11pm every day of the week with more
  // classrooms than any other building on campus, and could never appear.
  // Illinois' list has always included instructional buildings on the same
  // reasoning (CIF, BIF, the Armory, the ECE building), and its own comment
  // says to be generous here, because the list scrolls and more slots is what
  // lets the quieter, less obvious places show up.
  'Enarson Classroom': 0.75,                    // 112 hrs/week, peak 178, open 7 days
  'Timashev Family Music Building': 0.75,       // 91 hrs/week, peak 54, open 7 days
  'Sullivant Hall': 0.75,                       // 71 hrs/week, peak 34, open 7 days
  'Hitchcock Hall': 0.75,                       // 112 hrs/week, peak 33, open 7 days
  'Weigel Hall': 0.75,                          // 91 hrs/week, peak 18, open 7 days
  'Independence Hall': 0.75,                    // 112 hrs/week, peak 6, open 7 days
  'Smith Lab': 0.5,                             // 68 hrs/week, peak 112
  'Journalism Building': 0.5,                   // 80 hrs/week, peak 111
  'Hagerty Hall': 0.5,                          // 66 hrs/week, peak 98
  'Denney Hall': 0.5,                           // 60 hrs/week, peak 91
  'Baker Systems Engineering': 0.5,             // 62 hrs/week, peak 85
  'Schoenbaum Hall': 0.5,                       // 69 hrs/week, peak 78
  'Jennings Hall': 0.5,                         // 72 hrs/week, peak 72
  'McPherson Lab': 0.5,                         // 62 hrs/week, peak 71
  'Derby Hall': 0.5,                            // 61 hrs/week, peak 54
  'Bolz Hall': 0.5,                             // 62 hrs/week, peak 48
  'Caldwell Lab': 0.5,                          // 84 hrs/week, peak 47
  'Dreese Lab': 0.5,                            // 66 hrs/week, peak 46
  'Campbell Hall': 0.5,                         // 62 hrs/week, peak 45
  'Kottman Hall': 0.5,                          // 63 hrs/week, peak 42
  'Hayes Hall': 0.5,                            // 64 hrs/week, peak 36
  'Pomerene Hall': 0.5,                         // 78 hrs/week, peak 33
  'Stillman Hall': 0.5,                         // 70 hrs/week, peak 30
};

const PICK_LABELS_OSU = {};

// Ohio State's class schedule and its building register disagree on codes for
// a handful of buildings: the schedule appends a wing letter (RP -> RPB,
// TMV -> TMVN, HG -> HGG, PE -> PEA), and the Waterman complex has no code in
// the register at all. The register's sparse codes are why — only 144 of its
// 534 records carry one.
//
// Each of these was looked up by hand and matched on the register's own name,
// keyed by its building number, rather than by a rule that strips a trailing
// letter. A near-miss on a code is exactly how a building gets drawn in the
// wrong place, and a wrong location is worse than no location.
const GIS_ALIASES_OSU = {
  'Howlett Greenhouses':            '0297',   // register: Howlett Greenhouses
  'Phys Activ & Educ Srvs Bldg':    '0245',   // Physical Activity and Education Services - PAES
  'Recreation & Phys Activ Ctr':    '0246',   // Recreation and Physical Activity Center
  'Timashev Family Music Building': '1064',   // Timashev Family Music Building
  'Waterman- Multispecies Animal':  '1321',   // Waterman - Multispecies Animal Learning Complex
};

const GIS_ALIASES_UIUC = {};   // Illinois publishes no register, so nothing to join

// From the registrar's own five-year calendar:
// https://registrar.osu.edu/academic-calendar/academic-calendar-5-year-view-2023-2028/
// The term dates match what Ohio State's class API reports for every Autumn 2026
// meeting (2026-08-25 to 2026-12-09), so the two sources agree.
//
// Each period is exactly what the calendar names, not a day longer. The
// weekends either side of Autumn and Thanksgiving break are left as ordinary
// weekends: the registrar doesn't call them break days, and the weekend
// profiles already make Saturday and Sunday quieter.
//
// December 10 needs no entry — it falls between the last class and the first
// exam, and calendarPeriod() already treats anything after classesEnd as finals.
const ACADEMIC_CALENDAR_OSU = {
  term: 'Autumn 2026',
  classesStart: '2026-08-25',
  classesEnd:   '2026-12-09',
  termEnd:      '2026-12-17',   // last day of final examinations
  periods: [
    { start: '2026-09-07', end: '2026-09-07', kind: 'holiday', label: 'Labor Day — no classes' },
    { start: '2026-10-15', end: '2026-10-16', kind: 'break',   label: 'Autumn Break — no classes' },
    { start: '2026-11-11', end: '2026-11-11', kind: 'holiday', label: 'Veterans Day — no classes' },
    { start: '2026-11-25', end: '2026-11-27', kind: 'break',   label: 'Thanksgiving Break — no classes' },
  ],
};

// ─── Maryland content ─────────────────────────────────────────────────────────
// Same discipline as Columbus: shortened labels only where the short form is
// plainly the same name, and study spots only where a published source says a
// library is there. Which classroom buildings students actually treat as study
// spots is local knowledge this file does not have, and guessing it would put
// someone in front of a locked door.
//
// Keyed on the name Testudo's class data uses, because that is what the hours
// and room files join to. Several of those names are the registrar's rather
// than anyone's: HBK is officially the "Undergraduate Library" and everybody
// calls it Hornbake, and Testudo misspells Eppley as "Epply". The label fixes
// what is shown; renaming in the data would break the join.
const BUILDINGS_UMD = {
  'McKeldin Library':      { type: 'library' },
  'Undergraduate Library': { type: 'library', label: 'Hornbake Library' },
  'Stamp Student Union':   { type: 'union',   label: 'Stamp Student Union' },
  // "Epply" is Testudo's typo; MD iMAP and the university's own printed
  // directory both write Eppley.
  'Eppely Recreation Center': { type: 'rec', label: 'Eppley Recreation Center' },
  'Armory (Reckord)':         { type: 'rec', label: 'Reckord Armory' },
  'Yahentamitsi Dining Hall': { type: 'dining', label: 'Yahentamitsi' },

  // Long official names crowd out their neighbours on the map, so these show a
  // shorter form of the SAME name. Tooltips still show the full one.
  'Edward St. John Learning and Teaching Center': { label: 'Edward St. John', labelPriority: 1 },
  'Institute for Physical Sciences & Technology': { label: 'Physical Sciences & Tech' },
  'Parren J. Mitchell Art-Sociology Bldg.':       { label: 'Art-Sociology' },
  'Computer Science Instructional Center':        { label: 'CSIC' },
  // Buildings 088 and 089. The printed campus directory calls 088 "MARTIN
  // HALL", which is what everyone calls the pair.
  'Engineering Classroom Bldg. (Martin)':         { label: 'Martin Hall' },
  'Engineering Laboratory Bldg. (Martin)':        { label: 'Engineering Lab' },
  'Clarice Smith Performing Arts Center':         { label: 'The Clarice' },
  'Jeong H. Kim Engineering Building':            { label: 'Kim Engineering' },
  'Jimenez Bldg. (World Languages)':              { label: 'Jimenez Hall' },
  'John S. Toll Physics Building':                { label: 'Toll Physics' },
  'LeFrak Hall (Social Sciences)':                { label: 'LeFrak Hall' },
  'Avrum Gudelsky Veterinary Center':             { label: 'Gudelsky Vet Center' },
  'Biosciences Research Building':                { label: 'Biosciences Research' },
  'Chemistry-Biochemistry Bldg.':                 { label: 'Chemistry' },
  'Tawes Fine Arts Bldg.':                        { label: 'Tawes Hall' },
  'William E. Kirwan Hall':                       { label: 'Kirwan Hall' },
  'Architecture Bldg.':                           { label: 'Architecture' },
  'School of Public Health':                      { label: 'Public Health' },
};

// Every entry traces to the Libraries' own location pages, which state the
// building each library sits in, or to the union being the union. The tiers
// mirror the other two campuses: a library is a 1, the union and a building
// that CONTAINS a library are 0.75.
//
// Still short, and deliberately so. Illinois has twelve, and the rest of that
// list came from knowing the campus. A sourced list can say where the
// libraries are; it cannot say which atrium people actually work in.
const STUDY_SPOTS_UMD = {
  'McKeldin Library': 1,                            // the main library
  'Undergraduate Library': 1,                       // Hornbake
  'Stamp Student Union': 0.75,                      // same tier as the Illini and Ohio Unions
  'William E. Kirwan Hall': 0.75,                   // STEM Library, room 1403
  'Parren J. Mitchell Art-Sociology Bldg.': 0.75,   // Art Library
  'Architecture Bldg.': 0.75,                       // Architecture Library
  'Clarice Smith Performing Arts Center': 0.75,     // Michelle Smith Performing Arts Library
};

// Shorter still for the picks card, where three names wrap to three lines each.
// These are the forms already in use on campus, not invented abbreviations.
const PICK_LABELS_UMD = {
  'Undergraduate Library': 'Hornbake',
  'Clarice Smith Performing Arts Center': 'The Clarice',
  'Parren J. Mitchell Art-Sociology Bldg.': 'Art-Sociology',
  'Edward St. John Learning and Teaching Center': 'ESJ',
  'Eppely Recreation Center': 'Eppley Rec',
};

// Stamp has no classes, so Testudo gives it no scheduling code and the register
// join by code cannot reach it. MD iMAP puts the Stamp Student Union at
// building 163, so the name is pointed straight at that record — the same
// hand-checked, sourced route GIS_ALIASES_OSU uses, and for the same reason: a
// near-miss on a code is how a building gets drawn where it isn't.
const GIS_ALIASES_UMD = {
  'Stamp Student Union': '163',
};

// From the university's own semester calendar:
// https://academiccatalog.umd.edu/about-university/academic-calendar/semester-calendar/
// Read on 2026-10-19. Worth noting against an earlier draft of this work: the
// LibCal feed labels 11 October "Fall Break", a day before the registrar's
// break starts, because that is when the LIBRARY closed. The registrar's dates
// are the ones that say whether classes meet.
const ACADEMIC_CALENDAR_UMD = {
  term: 'Fall 2026',
  classesStart: '2026-08-31',
  classesEnd:   '2026-12-11',
  termEnd:      '2026-12-21',   // last day of final examinations
  periods: [
    { start: '2026-09-07', end: '2026-09-07', kind: 'holiday', label: 'Labor Day — no classes' },
    { start: '2026-10-12', end: '2026-10-13', kind: 'break',   label: 'Fall Break — no classes' },
    { start: '2026-11-25', end: '2026-11-29', kind: 'break',   label: 'Thanksgiving Recess — no classes' },
  ],
};

// Resolve the campus-specific content. Everything below this point uses the
// plain names, exactly as it did when there was only one campus.
const CAMPUS_CONTENT = {
  // sayWhenShut: tell people when most of campus is closed. Ohio State shuts
  // earlier and harder than Illinois -- 11pm leaves 5 of its 86 buildings open
  // against 11 of Illinois' 74 -- so a late visitor there meets a mostly dark
  // map and needs telling that is the answer, not a failure. Illinois is left
  // as it is; switch this on there only if the same question comes up.
  uiuc: { buildings: BUILDINGS_UIUC, studySpots: STUDY_SPOTS_UIUC,
          pickLabels: PICK_LABELS_UIUC, calendar: ACADEMIC_CALENDAR_UIUC,
          gisAliases: GIS_ALIASES_UIUC, sayWhenShut: false },
  osu:  { buildings: BUILDINGS_OSU,  studySpots: STUDY_SPOTS_OSU,
          pickLabels: PICK_LABELS_OSU,  calendar: ACADEMIC_CALENDAR_OSU,
          gisAliases: GIS_ALIASES_OSU, sayWhenShut: true },
  umd:  { buildings: BUILDINGS_UMD,  studySpots: STUDY_SPOTS_UMD,
          pickLabels: PICK_LABELS_UMD,  calendar: ACADEMIC_CALENDAR_UMD,
          // Maryland publishes no campus-wide building hours at all -- five
          // buildings have a published source and the rest ride the class
          // timetable -- so an empty-looking evening map needs the same
          // explanation Columbus gets.
          gisAliases: GIS_ALIASES_UMD, sayWhenShut: true },
}[CAMPUS.id];

const BUILDINGS = CAMPUS_CONTENT.buildings;
const STUDY_SPOTS = CAMPUS_CONTENT.studySpots;
const PICK_LABELS = CAMPUS_CONTENT.pickLabels;
const ACADEMIC_CALENDAR = CAMPUS_CONTENT.calendar;
const GIS_ALIASES = CAMPUS_CONTENT.gisAliases;


/**
 * The reason half of an assumed-closure note, for showing under a heading that
 * already says "Probably closed" — otherwise the panel says it twice.
 */
/**
 * Bookable study rooms in this building, when its library publishes them.
 *
 * Says "free to book" rather than "free", on purpose. The feed reports rooms
 * nobody has RESERVED, which is not the same as rooms nobody is sitting in —
 * blurring the two would be exactly the kind of confident-but-wrong claim the
 * rest of this map works to avoid. Hidden entirely when the library has no
 * bookable rooms today, because "0 of 0" reads as breakage rather than as a
 * closed Saturday.
 */
// ─── Browse: the campus as a list ─────────────────────────────────────────────
// Rooms a class is scheduled in, per weekday, from data/<campus>/rooms.json.
// Present only where the class sweep was rerun to keep room detail.
let roomSchedule = null;

async function loadRoomSchedule() {
  try {
    const r = await fetch(`${CAMPUS.dataDir}/rooms.json`);
    if (!r.ok) return;
    roomSchedule = (await r.json()).buildings ?? null;
    const entry = document.getElementById('browse-all');
    if (entry && roomSchedule) entry.hidden = false;
  } catch (e) { /* no room data for this campus */ }
}

/**
 * How long until a class takes this room, in hours, or null if one is in it now.
 * Infinity means nothing else is scheduled in it today.
 */
function roomFreeFor(room, day, time) {
  const spans = room?.busy?.[day] ?? [];
  for (const [a, b] of spans) if (time >= a && time < b) return null;
  const next = spans.map(([a]) => a).filter(a => a > time).sort((x, y) => x - y)[0];
  return next === undefined ? Infinity : next - time;
}

/** { free, total } rooms with no class scheduled in them right now. */
function roomsFreeIn(building, when) {
  const entry = roomSchedule?.[building];
  if (!entry) return null;
  const { day, time } = when ?? campusNow();
  const rooms = Object.values(entry.rooms ?? {});
  const free = rooms.filter(r => roomFreeFor(r, day, time) !== null).length;
  return { free, total: rooms.length };
}

function shortFor(hours) {
  if (hours === Infinity) return 'rest of the day';
  const m = Math.round(hours * 60);
  return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m` : `${m} min`;
}

// Looking at a time other than now. null = now.
let browseAt = null;

/** The moment the browse panel is describing — the chosen one, or now. */
function browseWhen() {
  if (!browseAt) return campusNow();
  const [y, mo, d] = browseAt.date.split('-').map(Number);
  const weekday = DAY_NAMES[new Date(y, mo - 1, d).getDay()];
  return { date: browseAt.date, day: weekday, hour: Math.floor(browseAt.time), time: browseAt.time };
}

/**
 * The span of dates there is anything to say about: today through the last day
 * of class. Beyond that the schedule is empty, and before today the answer is
 * only of historical interest.
 */
function browseDateRange() {
  const today = campusNow().date;
  const last = ACADEMIC_CALENDAR.classesEnd;
  return { min: today, max: last > today ? last : today };
}

const WHEEL_ROW = 34;          // must match .wheel-item in the stylesheet

const WHEELS = {
  hour: () => Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: String(i + 1) })),
  min:  () => [0, 15, 30, 45].map(m => ({ value: m, label: String(m).padStart(2, '0') })),
  ampm: () => [{ value: 0, label: 'AM' }, { value: 1, label: 'PM' }],
};

let wheelSettle = null;        // debounce, so a flick is read once it stops
// Setting scrollTop fires 'scroll' just like a finger does, so seating the
// wheels would otherwise read itself back as a change — which left the "Now"
// button on screen immediately after it had been used.
//
// A boolean cleared on a zero timeout is not enough: the browser dispatches
// those scroll events asynchronously, and some land after the flag has gone.
// A timestamp covers the whole dispatch, and nobody flicks a wheel within a
// quarter second of the panel drawing itself.
let seatedAt = 0;
const SEAT_QUIET_MS = 250;

function markAllWheels() {
  for (const id of ['wheel-hour', 'wheel-min', 'wheel-ampm']) {
    const el = document.getElementById(id);
    if (el) markWheel(el, wheelIndex(el));
  }
}

function fillWheel(el, items, selectedIndex) {
  if (el.dataset.filled !== String(items.length)) {
    el.innerHTML = '<div class="wheel-pad"></div>'
      + items.map((it, i) => `<div class="wheel-item" role="option" data-i="${i}">${it.label}</div>`).join('')
      + '<div class="wheel-pad"></div>';
    el.dataset.filled = String(items.length);
  }
  el.scrollTop = selectedIndex * WHEEL_ROW;
  markWheel(el, selectedIndex);
}

function markWheel(el, index) {
  el.querySelectorAll('.wheel-item').forEach((n, i) => n.classList.toggle('is-sel', i === index));
}

/** Which item is sitting under the band. */
function wheelIndex(el) {
  return Math.max(0, Math.round(el.scrollTop / WHEEL_ROW));
}

function readWheels() {
  const { min, max } = browseDateRange();
  const picked = document.getElementById('browse-date')?.value || min;
  const date = picked < min ? min : picked > max ? max : picked;
  const h12 = WHEELS.hour()[Math.min(wheelIndex(document.getElementById('wheel-hour')), 11)].value;
  const mins = WHEELS.min()[Math.min(wheelIndex(document.getElementById('wheel-min')), 3)].value;
  const pm = wheelIndex(document.getElementById('wheel-ampm')) === 1;
  const hour24 = (h12 % 12) + (pm ? 12 : 0);
  return { date, time: hour24 + mins / 60 };
}

function applyBrowseWhen(seatWheels = true) {
  const wrap = document.getElementById('browse-when');
  const nowBtn = document.getElementById('browse-now');
  if (!wrap) return;
  const w = browseWhen();
  const hh = Math.floor(w.time) % 24;
  const h12 = hh % 12 === 0 ? 12 : hh % 12;
  // Snap to the nearest quarter the wheel can actually show.
  const quarter = Math.min(3, Math.round(((w.time - Math.floor(w.time)) * 60) / 15) % 4);

  const dateEl = document.getElementById('browse-date');
  if (dateEl) {
    const { min, max } = browseDateRange();
    dateEl.min = min; dateEl.max = max; dateEl.value = w.date;
  }
  if (seatWheels) {
    seatedAt = Date.now();
    fillWheel(document.getElementById('wheel-hour'), WHEELS.hour(), h12 - 1);
    fillWheel(document.getElementById('wheel-min'), WHEELS.min(), quarter);
    fillWheel(document.getElementById('wheel-ampm'), WHEELS.ampm(), hh >= 12 ? 1 : 0);
  } else {
    // Only the wheel being touched updates itself; keep the others honest.
    markAllWheels();
  }

  if (nowBtn) nowBtn.hidden = !browseAt;
  wrap.hidden = false;

  const chip = document.getElementById('browse-when-label');
  if (chip) {
    const [, mo, d] = w.date.split('-').map(Number);
    chip.textContent = browseAt
      ? `${MONTH_SHORT[mo - 1]} ${d}, ${h12}:${String(quarter * 15).padStart(2, '0')} ${hh >= 12 ? 'PM' : 'AM'}`
      : 'Now';
    document.getElementById('browse-when-toggle')?.classList.toggle('is-custom', !!browseAt);
  }
}

/**
 * Why a chosen date might show less than today does.
 *
 * Two different gaps, worth naming rather than letting someone conclude the
 * campus is shut. A no-class day has no timetable to read at all, and the
 * libraries and rec centres publish only a rolling week, so past that the map
 * genuinely does not know their hours.
 */
function browseNote(date) {
  const period = calendarPeriod(date);
  if (!period.classesMeet) {
    // The calendar's own label usually already ends "— no classes", so this
    // adds the consequence rather than a second dash and a repeat.
    const label = (period.label || 'No classes this day').replace(/\s*—\s*no classes$/i, '');
    return `${label}: nothing is timetabled, so there are no room counts.`;
  }
  const dated = Object.values(data.hours?.buildings ?? {}).filter(v => v.dates);
  if (dated.length && !dated.some(v => date in v.dates)) {
    return 'Libraries and rec centres publish about a week ahead, so their hours are unknown this far out. Classrooms are unaffected.';
  }
  return null;
}

function applyBrowseNote(date) {
  const el = document.getElementById('browse-note');
  if (!el) return;
  const msg = browseNote(date);
  el.textContent = msg ?? '';
  el.hidden = !msg;
}

function setBrowseAt(date, time, fromWheel = false) {
  const { min, max } = browseDateRange();
  const clamped = date < min ? min : date > max ? max : date;
  browseAt = { date: clamped, time };
  // Re-seating a wheel the user is still touching would yank it mid-flick, so
  // a change that came from a wheel re-renders the list but leaves them be.
  renderBrowse({ seatWheels: !fromWheel });
}

let browseBuilding = null;   // null = the list, otherwise the building drilled into
const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
let browseQuery = '';        // what the search box is filtering the list by
const escapeHtml = s => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function renderBrowse({ seatWheels = true } = {}) {
  const body = document.getElementById('browse-body');
  const title = document.getElementById('browse-title');
  const sub = document.getElementById('browse-sub');
  const back = document.getElementById('browse-back');
  if (!body) return;

  const search = document.getElementById('browse-search');
  if (search) search.hidden = !!browseBuilding;
  if (browseBuilding) return renderBrowseRooms(body, title, sub, back, seatWheels);
  back.hidden = true;
  title.textContent = 'Buildings';

  applyBrowseWhen(seatWheels);
  const { date, time } = browseWhen();
  applyBrowseNote(date);
  const all = knownBuildings().sort((a, b) => pickLabel(a).localeCompare(pickLabel(b)));
  const q = browseQuery.trim().toLowerCase();
  const names = q ? all.filter(n => pickLabel(n).toLowerCase().includes(q) || n.toLowerCase().includes(q)) : all;
  const groups = { Library: [], Academic: [] };
  for (const n of names) {
    (BUILDINGS[n]?.type === 'library' || /librar/i.test(pickLabel(n)) ? groups.Library : groups.Academic).push(n);
  }
  // Campus time, not the reader's — someone checking Ohio State from a
  // different timezone is asking about Columbus.
  const hh = Math.floor(time), mm = Math.round((time - hh) * 60);
  const am = hh < 12 || hh >= 24;
  const h12 = hh % 12 === 0 ? 12 : hh % 12;
  sub.textContent = `${q ? `${names.length} of ${all.length}` : names.length} buildings · ${h12}:${String(mm).padStart(2, '0')} ${am ? 'am' : 'pm'}`;

  let html = '';
  if (q && !names.length) html = `<div class="browse-foot">No building matches \u201c${escapeHtml(browseQuery.trim())}\u201d.</div>`;
  for (const [label, list] of Object.entries(groups)) {
    if (!list.length) continue;
    html += `<div class="browse-group">${label}</div>`;
    for (const n of list) {
      // "Closed" is a claim; "no hours" is the absence of one. A library whose
      // published week has rolled past is not shut, we just don't know — and
      // saying Closed there would send someone away from an open library.
      const st = hoursStatus(n, date, time);
      const rooms = st.state === 'open' ? roomsFreeIn(n, browseWhen()) : null;
      let badge;
      if (st.state === 'unknown') badge = '<span class="badge badge-closed">No hours</span>';
      else if (st.state !== 'open') badge = `<span class="badge badge-closed">${st.assumed ? 'Probably closed' : 'Closed'}</span>`;
      else if (rooms && rooms.total) badge = `<span class="badge ${rooms.free ? 'badge-open' : 'badge-none'}">${rooms.free}/${rooms.total}</span>`;
      else badge = '<span class="badge badge-open">Open</span>';
      html += `<button class="browse-row" data-building="${encodeURIComponent(n)}">`
            + `<span class="browse-name">${pickLabel(n)}</span>${badge}</button>`;
    }
  }
  html += '<div class="browse-foot">A count shows rooms with no class scheduled right now. '
        + 'That is not the same as unlocked — many classrooms are locked outside class.</div>';
  body.innerHTML = html;
  body.scrollTop = 0;
}

function renderBrowseRooms(body, title, sub, back, seatWheels = true) {
  const n = browseBuilding;
  applyBrowseWhen(seatWheels);
  const { day, time } = browseWhen();
  const entry = roomSchedule?.[n];
  back.hidden = false;
  title.textContent = pickLabel(n);

  const rooms = Object.entries(entry?.rooms ?? {})
    .map(([fid, r]) => ({ fid, cap: r.capacity, free: roomFreeFor(r, day, time) }))
    .sort((a, b) => (b.free ?? -1) - (a.free ?? -1));
  const freeCount = rooms.filter(r => r.free !== null).length;
  sub.textContent = rooms.length
    ? `${freeCount} of ${rooms.length} with no class scheduled`
    : 'No classroom schedule for this building';

  let html = rooms.map(r => {
    const id = r.fid.replace(entry.code, '').replace(/^0+/, '') || r.fid;
    return `<div class="room-row"><span><span class="room-id">${id}</span>`
      + `<span class="room-for">${r.free === null ? 'Class in progress'
          : `No class for ${shortFor(r.free)}`}${r.cap ? ` · seats ${r.cap}` : ''}</span></span>`
      + `<span class="badge ${r.free === null ? 'badge-closed' : 'badge-open'}">`
      + `${r.free === null ? 'In use' : 'Free'}</span></div>`;
  }).join('');
  if (!rooms.length) html = '<div class="browse-foot">Nothing scheduled here, so there is no room list to show.</div>';
  else html += '<div class="browse-foot">From the registrar\'s class schedule. A room with no class '
             + 'may still be locked — this says nobody is timetabled in it.</div>';
  body.innerHTML = html;
  body.scrollTop = 0;
}

function openBrowse() {
  browseBuilding = null;
  browseQuery = '';
  document.getElementById('browse-when')?.classList.add('is-collapsed');
  document.getElementById('browse-when-toggle')?.setAttribute('aria-expanded', 'false');
  const box = document.getElementById('browse-search');
  if (box) box.value = '';
  browseAt = null;          // always open on now, not on whatever was last picked
  renderBrowse();
  document.getElementById('browse')?.classList.add('is-open');
  document.getElementById('browse-backdrop')?.classList.add('is-open');
  // Move focus into the panel so a keyboard or screen reader follows it, and
  // so Escape has somewhere sensible to come from.
  document.getElementById('browse-close')?.focus({ preventScroll: true });
  track('browse_opened', { device: deviceKind() });
}
function closeBrowse() {
  document.getElementById('browse')?.classList.remove('is-open');
  document.getElementById('browse-backdrop')?.classList.remove('is-open');
}
function browseIsOpen() {
  return !!document.getElementById('browse')?.classList.contains('is-open');
}

function renderRooms(name) {
  const box = document.getElementById('panel-rooms');
  if (!box) return;
  const entry = roomAvailability?.[name];
  if (!entry || !entry.total) { box.hidden = true; return; }
  const { free, total, bookable, sources = [] } = entry;
  const word = total === 1 ? 'room' : 'rooms';
  // No slot covers this instant, so the library is not taking bookings now.
  // Saying "0 of 7 free" here would read as "all seven are taken".
  const body = bookable === 0
    ? `<span class="rooms-none">Not bookable now</span> · ${total} study ${word} here`
    : `<span class="${free ? 'rooms-count' : 'rooms-none'}">${free} of ${total}</span>`
      + ` study ${word} free to book right now`;
  box.innerHTML = body
    + (sources.length ? `<span class="rooms-where">${sources.join(' · ')}</span>` : '');
  box.hidden = false;
}

function closureReason(note) {
  const reason = note.replace(/^Probably closed\s*·\s*/, '');
  return reason.charAt(0).toUpperCase() + reason.slice(1) + '.';
}

function pickLabel(name) {
  return PICK_LABELS[name] ?? BUILDINGS[name]?.label ?? name;
}

/**
 * The hour a building closes, in campus time, or null when today's hours aren't
 * published or it isn't open right now. Can exceed 24 before wrapping — a
 * library open "until 2am" closes at 26 on the previous day's row.
 */
function closingHour(name, date, time) {
  const entry = data.hours?.buildings?.[name];
  if (!entry) return null;

  // Still open from yesterday's late hours, same case hoursStatus() handles.
  const yesterday = publishedRanges(entry, shiftDate(date, -1)) || [];
  const late = yesterday.find(([, close]) => close > 24 && time < close - 24);
  if (late) return late[1];

  const today = publishedRanges(entry, date);
  if (!today) return null;
  const open = today.find(([from, close]) => time >= from && time < close);
  if (!open) return null;

  // A range covering the whole day (Grainger publishes [0, 24]) has no closing
  // time worth printing: "until 12am" reads as a time that already passed, when
  // it actually means ~22 hours from now. Say nothing rather than mislead.
  return open[0] <= 0 && open[1] >= 24 ? null : open[1];
}

function fmtHour(h) {
  const wrapped = ((h % 24) + 24) % 24;
  const hour = Math.floor(wrapped);
  const min = Math.round((wrapped - hour) * 60);
  if (!min && hour === 0)  return 'midnight';
  if (!min && hour === 12) return 'noon';
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  const suffix = hour < 12 ? 'am' : 'pm';
  return min ? `${h12}:${String(min).padStart(2, '0')}${suffix}` : `${h12}${suffix}`;
}

/**
 * How busy a pick is, in words rather than a percentage. Only `reported` is
 * about right now; the rest are predictions, and `typical` is a generic curve
 * for the building's type, so printing "36% full" next to it would be inventing
 * precision the number doesn't have. The wording also says where it came from,
 * so a guess never reads like a measurement.
 */
function busyWord(occ) {
  const level = occ.value < 0.3 ? 'quiet' : occ.value < 0.55 ? 'fairly busy' : 'busy';
  // Only a student report describes right now; everything else is a prediction,
  // and "usually" is the word that carries that. Which *kind* of prediction —
  // class timetable, Google, or the building-type profile — is a distinction
  // that matters to us, not to someone deciding where to walk, and spelling it
  // out here wrapped every row onto a third line. The panel still names the
  // exact source when they tap through.
  return occ.source === 'reported'
    ? `students say it's ${level}`
    : `usually ${level} now`;
}

// classBusyness() divides by each building's OWN peak, which is right for
// colouring the map but wrong for ranking buildings against each other: a
// building the timetable barely covers reads "0% — quiet" when it really means
// "no classes here, and nothing else is known". Beckman peaks at 9 class-hours
// against CIF's 143 — it's a drop-in research building whose occupancy simply
// isn't explained by its timetable, so a class estimate there is noise, and
// ranking on it put Beckman top at both 10:30am and 2:30pm.
//
// So a class estimate only earns a ranking when the building is genuinely
// class-driven. The two groups are far apart (3-9 class-hours for the
// libraries, the Union and Law; 68-143 for CIF, BIF, ECEB, Armory and Smith),
// so any cutoff from roughly 20 to 60 splits them identically — the exact
// number here is not load-bearing. Buildings that fail it keep their own
// typical-pattern estimate if they have one, and are left out entirely if they
// don't, rather than being recommended on a number that means nothing.
//
// The cutoff is the campus's own MEDIAN peak rather than a fixed count, because
// the scale is campus-specific: Illinois peaks run to 143.5 with a median of
// 28.5, Ohio State's run to 32.8 with a median of 5. The old fixed 30 happened
// to sit near the Illinois median, but on Ohio State it would have passed 1
// building in 101 and silently emptied the picks card. Taking the median keeps
// the Illinois behaviour and carries to any campus.
let classCoverageMin = null;

function classCoverageThreshold() {
  if (classCoverageMin !== null) return classCoverageMin;
  const peaks = Object.values(data.classActivity?.buildings || {})
    .map(b => b.peak)
    .filter(p => typeof p === 'number' && p > 0)
    .sort((a, b) => a - b);
  if (!peaks.length) return (classCoverageMin = Infinity);   // no data: trust nothing
  const mid = Math.floor(peaks.length / 2);
  classCoverageMin = peaks.length % 2 ? peaks[mid] : (peaks[mid - 1] + peaks[mid]) / 2;
  return classCoverageMin;
}

function classDriven(name) {
  return (data.classActivity?.buildings?.[name]?.peak ?? 0) >= classCoverageThreshold();
}

/**
 * Open study spots we can actually say something about, best first.
 *
 * Ranked on how good an option each one is right now — how much people want to
 * be there, discounted by how full it is — rather than on emptiness. Because
 * it's a product, somewhere people want badly still wins while it has room, and
 * drops away as it fills: a library at 60% beats a lecture building at 25%, but
 * the same library at 90% doesn't. That matches what someone opening the site
 * is actually asking, which is "where should I go", not "what is emptiest".
 */
function studyPicks(limit = PICK_COUNT) {
  const { date, time } = campusNow();
  return Object.keys(STUDY_SPOTS)
    .map(name => ({ name, occ: buildingOccupancy(name) }))
    .filter(({ name, occ }) =>
      occ
      // 'open' carries no busyness to rank on -- it means only that the doors
      // are open and nothing is scheduled. It belongs on the map and in the
      // counts, but a list headed "good for studying" should not be sorted by
      // a zero nobody measured.
      && !['closed', 'unknown', 'open'].includes(occ.source)
      && (occ.source !== 'estimated' || classDriven(name)))
    .map(pick => ({ ...pick, appeal: STUDY_SPOTS[pick.name] * (1 - pick.occ.value) }))
    .sort((a, b) => b.appeal - a.appeal)
    .slice(0, limit)
    .map(pick => ({ ...pick, until: closingHour(pick.name, date, time) }));
}

// ─── Colours and labels ───────────────────────────────────────────────────────
function occToColor(t) {
  let r, g, b;
  if (t < 0.5) {
    const s = t * 2;
    r = Math.round(34  + s * (234 - 34));
    g = Math.round(197 + s * (179 - 197));
    b = Math.round(94  + s * (8   - 94));
  } else {
    const s = (t - 0.5) * 2;
    r = Math.round(234 + s * (239 - 234));
    g = Math.round(179 + s * (68  - 179));
    b = Math.round(8   + s * (68  - 8));
  }
  return '#' + [r, g, b].map(v => v.toString(16).padStart(2, '0')).join('');
}

function cssColor(t) {
  if (t < 0.4) return '#22c55e';
  if (t < 0.7) return '#eab308';
  return '#ef4444';
}

function statusLabel(t) {
  if (t < 0.35) return 'Quiet';
  if (t < 0.6)  return 'Moderate';
  if (t < 0.8)  return 'Busy';
  return 'Very busy';
}

const SOURCE_LABELS = {
  reported:  'Student reported',
  measured:  'Google data',
  estimated: 'Estimated',
  typical:   'Estimated',
  closed:    'Closed',
  unknown:   'No data right now',
};

// ─── Map area: Champaign–Urbana only ──────────────────────────────────────────
const AREA = CAMPUS.area;
const AREA_RECT = Cesium.Rectangle.fromDegrees(AREA.west, AREA.south, AREA.east, AREA.north);

// ─── Basemap: drawn in the browser from OpenStreetMap data ─────────────────────
// data/basemap.json (scripts/build_basemap.py) holds roads, paths, lawns, water
// and rail. Each map tile is drawn on a canvas in these colours, so the look is
// fully ours — no satellite photos and no third-party tile service.
const MAP_STYLE = {
  background: '#3d4151',
  farm:    { fill: '#434852' },
  wood:    { fill: '#485a4d' },
  green:   { fill: '#53684f' },
  parking: { fill: '#464a5b' },
  water:   { fill: '#3d5877' },
  stream:  { stroke: '#4a6a8e', widthM: 3,   minPx: 0.8 },
  path:    { stroke: '#666b82', widthM: 1.6, minPx: 1,   minLevel: 15 },
  service: { stroke: '#70758d', widthM: 4,   minPx: 0.6, minLevel: 14 },
  minor:   { stroke: '#858aa3', widthM: 8,   minPx: 0.7, minLevel: 12 },
  major:   { stroke: '#9ea3bc', widthM: 13,  minPx: 1.2 },
  rail:    { stroke: '#5b6073', widthM: 2.5, minPx: 0.8, dash: [6, 5] },
};

// Tiles are drawn by basemap-worker.js in the background, so dragging the map
// never waits on them. Browsers without OffscreenCanvas draw on the page.
class VectorBasemapProvider {
  constructor(drawTile) {
    this.tilingScheme = new Cesium.WebMercatorTilingScheme();
    this.tileWidth = BasemapRender.TILE_SIZE;
    this.tileHeight = BasemapRender.TILE_SIZE;
    this.minimumLevel = 0;
    this.maximumLevel = 19;
    this.rectangle = AREA_RECT;
    this.tileDiscardPolicy = undefined;
    this.errorEvent = new Cesium.Event();
    this.credit = new Cesium.Credit(
      '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors', true);
    this.proxy = undefined;
    this.hasAlphaChannel = false;
    this.ready = true;
    this.readyPromise = Promise.resolve(true);
    this._drawTile = drawTile;
  }

  getTileCredits() { return undefined; }
  pickFeatures() { return undefined; }

  requestImage(x, y, level) {
    const r = this.tilingScheme.tileXYToNativeRectangle(x, y, level);
    return this._drawTile({ west: r.west, south: r.south, east: r.east, north: r.north }, level);
  }
}

const BASEMAP_URL = `${CAMPUS.dataDir}/basemap.json`;
// Version tag so browsers pick up new worker code (matches the ?v= in index.html)
const BASEMAP_VERSION = new URL(document.querySelector('script[src*="basemap-render.js"]').src).search;

/** Resolves to a function (tile, level) => Promise<image>, or null if there's no basemap. */
async function startBasemap() {
  if (window.Worker && typeof OffscreenCanvas !== 'undefined') {
    try {
      return await startWorkerBasemap();
    } catch (e) {
      console.warn('Background map drawing unavailable, drawing on the page instead:', e);
    }
  }
  const basemap = await loadJson(BASEMAP_URL);
  if (!basemap) return null;
  const index = BasemapRender.buildIndex(basemap, AREA);
  return (tile, level) => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = BasemapRender.TILE_SIZE;
    BasemapRender.drawTile(canvas.getContext('2d'), index, MAP_STYLE, tile, level);
    return Promise.resolve(canvas);
  };
}

function startWorkerBasemap() {
  return new Promise((resolve, reject) => {
    const worker = new Worker(`basemap-worker.js${BASEMAP_VERSION}`);
    const pending = new Map();
    let nextId = 1;

    worker.onmessage = ({ data }) => {
      if (data.type === 'ready') {
        resolve((tile, level) => new Promise((ok, fail) => {
          const id = nextId++;
          pending.set(id, { ok, fail });
          worker.postMessage({ type: 'tile', id, tile, level });
        }));
      } else if (data.type === 'failed') {
        worker.terminate();
        reject(new Error(data.message));
      } else {
        const job = pending.get(data.id);
        if (!job) return;
        pending.delete(data.id);
        if (data.type === 'tile') job.ok(data.bitmap); else job.fail(new Error(data.message));
      }
    };
    worker.onerror = (e) => { worker.terminate(); reject(e); };
    worker.postMessage({
      type: 'init',
      url: new URL(BASEMAP_URL, location.href).href,
      style: MAP_STYLE,
      area: AREA,
    });
  });
}

// ─── Viewer setup ─────────────────────────────────────────────────────────────
const viewer = new Cesium.Viewer('cesiumContainer', {
  terrain: Cesium.Terrain.fromWorldTerrain(),
  baseLayer: false,   // the drawn basemap is added once its data has loaded
  useBrowserRecommendedResolution: false,   // see RENDER_PIXEL_RATIO below
  // Only redraw when something changes, instead of 60 times a second
  requestRenderMode: true,
  maximumRenderTimeChange: Infinity,
  timeline: false,
  animation: false,
  baseLayerPicker: false,
  geocoder: false,
  homeButton: false,
  sceneModePicker: false,
  navigationHelpButton: false,
  fullscreenButton: false,
  infoBox: false,
  selectionIndicator: false,
});

const scene = viewer.scene;
scene.globe.maximumScreenSpaceError = 2;   // default detail; the drawn basemap stays crisp
scene.globe.tileCacheSize = 1000;
scene.globe.baseColor = Cesium.Color.fromCssColorString(MAP_STYLE.background);
scene.globe.enableLighting = false;
scene.skyAtmosphere.show = true;
scene.fog.enabled = true;
scene.fog.density = 0.0002;
scene.postProcessStages.fxaa.enabled = true;
// The map is almost entirely flat colour meeting flat colour, and it renders
// below native resolution (see RENDER_PIXEL_RATIO), so every building edge is a
// hard staircase that FXAA alone doesn't clear up. MSAA does. Phones get half
// the samples, on the same reasoning that dropped their resolution: this is the
// kind of work they have least of. (WebGL2 only; ignored where it's missing.)
scene.msaaSamples = deviceKind() === 'phone' ? 2 : 4;

viewer.clock.currentTime = Cesium.JulianDate.fromIso8601('2026-09-15T19:00:00Z');
viewer.clock.shouldAnimate = false;

// ─── Performance: one steady resolution ───────────────────────────────────────
// Switching resolution at the start/end of every drag made the map flash, so
// render at a fixed ratio instead: close to Retina sharpness, much less work.
// Building names are page text, so they're always full sharpness anyway.
// 1 = one map pixel per screen pixel (fastest), 2 = full Retina (sharpest).
// Rendering cost scales with the square of this, so it's the biggest lever on
// how smooth dragging and zooming feel. Override with ?sharpness=1.5 to compare.
const RENDER_PIXEL_RATIO = Number(new URLSearchParams(location.search).get('sharpness')) || 1.25;
function applyPixelRatio() {
  viewer.resolutionScale = Math.min(1, RENDER_PIXEL_RATIO / (window.devicePixelRatio || 1));
}
applyPixelRatio();
window.addEventListener('resize', applyPixelRatio);

// ─── Camera ───────────────────────────────────────────────────────────────────
const CAMPUS_CENTER = Cesium.Cartesian3.fromDegrees(
  CAMPUS.center.lon, CAMPUS.center.lat, CAMPUS.center.height);
// A phone held upright sees a tall, narrow slice of the map, and at a shallow
// angle most of that slice is sky and distant town. Looking down more steeply
// and standing closer puts campus itself in the part of the screen the picks
// sheet doesn't cover. Each campus gives its own pair, because how much of a
// campus fits on a phone depends on how spread out it is.
const NARROW = window.matchMedia('(max-width: 640px)').matches;
const HOME_SHOT = (NARROW && CAMPUS.viewNarrow) || CAMPUS.view;
const HOME_VIEW = new Cesium.HeadingPitchRange(
  0,
  Cesium.Math.toRadians(HOME_SHOT.pitchDeg),
  HOME_SHOT.range
);

function goHome() {
  viewer.camera.lookAt(CAMPUS_CENTER, HOME_VIEW);
  viewer.camera.lookAtTransform(Cesium.Matrix4.IDENTITY);
}
goHome();

const controller = scene.screenSpaceCameraController;
controller.minimumZoomDistance = 60;
controller.maximumZoomDistance = 6000;

// Just short of straight down: at exactly -90° the heading has nothing left to
// swing around, so a small drag (a thumb on a phone especially) sends the view
// spinning. Half a degree off is indistinguishable and stays stable.
const MIN_PITCH = Cesium.Math.toRadians(-89.5);
const MAX_PITCH = Cesium.Math.toRadians(-15);

scene.preRender.addEventListener(() => {
  const cam = viewer.camera;
  const pos = cam.positionCartographic;
  const lon = Cesium.Math.toDegrees(pos.longitude);
  const lat = Cesium.Math.toDegrees(pos.latitude);
  const clampedLon = Cesium.Math.clamp(lon, AREA.west, AREA.east);
  const clampedLat = Cesium.Math.clamp(lat, AREA.south, AREA.north);
  const clampedPitch = Cesium.Math.clamp(cam.pitch, MIN_PITCH, MAX_PITCH);

  if (clampedLon !== lon || clampedLat !== lat || clampedPitch !== cam.pitch) {
    cam.setView({
      destination: Cesium.Cartesian3.fromDegrees(clampedLon, clampedLat, pos.height),
      orientation: { heading: cam.heading, pitch: clampedPitch, roll: 0 },
    });
  }
});

// Trackpad pinch arrives as a ctrl+wheel event, which Cesium ignores and Chrome
// would use to zoom the page. Turn it into a normal, amplified wheel event.
const PINCH_SPEED = 6;
document.addEventListener('wheel', (e) => {
  if (!e.ctrlKey || e.target !== scene.canvas) return;
  e.preventDefault();
  e.stopPropagation();
  scene.canvas.dispatchEvent(new WheelEvent('wheel', {
    deltaY: e.deltaY * PINCH_SPEED,
    deltaMode: 0,
    clientX: e.clientX,
    clientY: e.clientY,
    bubbles: true,
    cancelable: true,
  }));
}, { capture: true, passive: false });

/** The default view, used by the H key and by zooming a study pick back out. */
function flyHome(duration = 1.2) {
  viewer.camera.flyToBoundingSphere(new Cesium.BoundingSphere(CAMPUS_CENTER, 1), {
    offset: HOME_VIEW,
    duration,
  });
}

// How far from a building to sit once zoomed in. Comfortably inside the
// controller's 60–6000 m range, and close enough to read its neighbours.
const PICK_ZOOM_RANGE = 320;

/**
 * Fly to one building, keeping the heading and pitch the view already has.
 * Letting Cesium choose its own orientation would undo the 2D/3D toggle and can
 * land exactly straight down — the angle MIN_PITCH exists to stay away from,
 * because heading has nothing to swing around there and a drag sends it
 * spinning. Returns false when the building was never drawn.
 */
function flyToBuilding(name, duration = 1.2) {
  const label = labels.find(l => l.name === name);
  if (!label) return false;
  const cam = viewer.camera;
  cam.flyToBoundingSphere(new Cesium.BoundingSphere(label.position, 60), {
    offset: new Cesium.HeadingPitchRange(cam.heading, cam.pitch, PICK_ZOOM_RANGE),
    duration,
  });
  return true;
}

document.addEventListener('keydown', (e) => {
  if (e.key !== 'h' && e.key !== 'H') return;
  zoomedPick = null;
  markZoomedPick();
  flyHome();
});

// ─── 2D / 3D toggle ───────────────────────────────────────────────────────────
// Straightening the view out by hand is fiddly, so this does it in one step:
// whatever is in the middle of the screen stays there, seen from above with
// north at the top. Pressing it again tilts back to the usual angled view.
// (Top-down isn't literally 2D — the buildings are still extruded — but "2D"
// is what people expect this button to be called.)
const compass = document.getElementById('compass');
const compassLabel = document.getElementById('compass-label');

// Anything this steep counts as "looking down", so the button tilts back out
// of a top-down view the user dragged into by hand, not just one it set.
const LOOKING_DOWN_PITCH = Cesium.Math.toRadians(-80);

compass.addEventListener('click', () => {
  const cam = viewer.camera;
  const middle = new Cesium.Cartesian2(scene.canvas.clientWidth / 2, scene.canvas.clientHeight / 2);
  const ray = cam.getPickRay(middle);
  const target = (ray && scene.globe.pick(ray, scene)) || CAMPUS_CENTER;
  const range = Cesium.Math.clamp(
    Cesium.Cartesian3.distance(cam.positionWC, target),
    controller.minimumZoomDistance,
    controller.maximumZoomDistance,
  );
  const pitch = cam.pitch <= LOOKING_DOWN_PITCH ? HOME_VIEW.pitch : MIN_PITCH;
  cam.flyToBoundingSphere(new Cesium.BoundingSphere(target, 1), {
    offset: new Cesium.HeadingPitchRange(0, pitch, range),
    duration: 0.8,
  });
});

let shownDown = null;
scene.postRender.addEventListener(() => {
  const down = viewer.camera.pitch <= LOOKING_DOWN_PITCH;
  if (down === shownDown) return;
  shownDown = down;
  compassLabel.textContent = down ? '3D' : '2D';
  compass.classList.toggle('looking-down', down);
  const label = down
    ? 'Switch back to the angled 3D view'
    : 'Switch to a top-down view, north at the top';
  compass.title = label;
  compass.setAttribute('aria-label', label);
});

// ─── Buildings ────────────────────────────────────────────────────────────────
let buildingsTileset = null;

// Cesium's defaults load campus fastest. (Tested: skipping detail levels made
// first load ~5x slower.) The two settings below trade a little building
// detail for speed on laptops.
const BUILDING_TILESET_OPTIONS = {
  maximumScreenSpaceError: 24,   // default 16: fewer, coarser building tiles
  cacheBytes: 256 * 1024 * 1024, // default 512MB: lighter on memory
};

async function loadBuildings() {
  try {
    buildingsTileset = scene.primitives.add(await Cesium.createOsmBuildingsAsync(BUILDING_TILESET_OPTIONS));
    performance.mark('buildings-tileset-ready');
    buildingsTileset.tileLoad.addEventListener(claimTileBuildings);
    // Waiting for every tile in view before admitting the map is here costs
    // about a second of staring at a loading chip over a map that is already
    // drawn: the basemap lands first, and buildings arrive roughly half way
    // through. Clear it on the first tile and let the rest fill in, which is
    // what the map does anyway as you pan.
    buildingsTileset.tileLoad.addEventListener(() => {
      if (performance.getEntriesByName('buildings-first-tile').length) return;
      performance.mark('buildings-first-tile');
      document.getElementById('loading')?.classList.add('done');
    });
    buildingsTileset.initialTilesLoaded.addEventListener(() => {
      performance.mark('buildings-all-in-view');
      // Once the tiles have had their go at naming buildings, fill the gaps
      // from the university's own coordinates.
      placeMissingBuildings();
      document.getElementById('loading')?.classList.add('done');   // nothing loaded: still clear it
      startAnalytics();
      track('map_ready', {
        seconds_to_buildings: +(performance.now() / 1000).toFixed(1),
        device: deviceKind(),
        buildings_with_data: knownBuildings().length,
      });
      maybeShowSurvey();
    });
    applyStyle();
  } catch (e) {
    console.error('OSM Buildings failed to load:', e);
    document.getElementById('loading')?.classList.add('done');
    startAnalytics();
    const cause = mapFailureCause(e);
    track('map_failed', { reason: String(e).slice(0, 120), cause, device: deviceKind() });
    showMapWarning(cause);
  }
}

/**
 * Why the building tiles didn't arrive, in the only two flavours that have
 * ever actually shown up in the analytics.
 *
 * Cesium ion answers 403 when the token is real but the request isn't allowed
 * from where it came — in practice a browser that sent no Referer at all, so
 * ion can't match it against the token's URL list. Verified by hand: every
 * legitimate origin returns 200, and the identical request with the header
 * removed returns 403.
 *
 * A 401 means ion rejected the token itself. That happens to someone running a
 * cached copy of an older app.js whose token has since been regenerated, which
 * is why the advice is to reload rather than to change a setting.
 */
function mapFailureCause(e) {
  const msg = String(e);
  if (msg.includes('403')) return 'blocked';
  if (msg.includes('401')) return 'stale';
  return 'other';
}

const MAP_WARNING_TEXT = {
  blocked: 'A privacy setting in this browser is hiding which site made the request, '
         + 'so the map service turned it down. Allowing this site in your tracking '
         + 'protection, or opening it in a different browser, will bring the map back.',
  stale:   'This page is running a cached copy of the site that\u2019s out of date. '
         + 'A refresh should fix it.',
  other:   'The map service didn\u2019t answer.',
};

function showMapWarning(cause) {
  const box = document.getElementById('map-warning');
  const why = document.getElementById('map-warning-why');
  if (!box || !why) return;
  why.textContent = MAP_WARNING_TEXT[cause] ?? MAP_WARNING_TEXT.other;
  box.hidden = false;
  document.getElementById('map-warning-close')?.addEventListener('click', () => {
    box.hidden = true;
  }, { once: true });
}

// Places drawn by us rather than coming from the building tiles.
const overlays = new Map();
// Solid, muted building colours in the style of a clean vector map.
const NO_DATA_HEX = '#6f5c63';
const CLOSED_HEX  = '#3a3f4f';

function colorFor(occ) {
  if (!occ) return { hex: NO_DATA_HEX, alpha: 1 };
  if (occ.source === 'closed') return { hex: CLOSED_HEX, alpha: 1 };
  if (occ.source === 'unknown') return { hex: NO_DATA_HEX, alpha: 1 };
  return { hex: occToColor(occ.value), alpha: 1 };
}

function createOverlays() {
  for (const [name, cfg] of Object.entries(BUILDINGS)) {
    const shape = cfg.shape;
    if (!shape) continue;
    overlays.set(name, { outline: shape.outline, baseM: shape.baseM, topM: shape.topM });
  }
  drawOverlays();
}

// All of our shapes live in one primitive with a flat per-instance colour.
// Entity polygons would be simpler, but Cesium lights and shades them, which
// leaves them visibly darker than the building tiles standing next to them —
// the tiles are styled flat. Flat here means our shapes and the tiles read as
// the same colour, which is the whole point of colouring them.
let overlayPrimitive = null;
const overlayColors = new Map();

function overlayInstance(name, shape) {
  const { hex } = colorFor(buildingOccupancy(name));
  overlayColors.set(name, hex);
  return new Cesium.GeometryInstance({
    id: name,
    geometry: new Cesium.PolygonGeometry({
      polygonHierarchy: new Cesium.PolygonHierarchy(Cesium.Cartesian3.fromDegreesArray(shape.outline.flat())),
      height: shape.baseM,
      extrudedHeight: shape.topM,
      vertexFormat: Cesium.PerInstanceColorAppearance.FLAT_VERTEX_FORMAT,
    }),
    attributes: { color: Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.fromCssColorString(hex)) },
  });
}

// Rebuilt whenever the set of shapes changes, which happens at most twice: once
// at startup, once when the tiles have shown us what they don't carry.
function drawOverlays() {
  if (overlayPrimitive) scene.primitives.remove(overlayPrimitive);
  overlayPrimitive = null;
  overlayColors.clear();
  if (!overlays.size) return;
  const instances = [];
  for (const [name, shape] of overlays) instances.push(overlayInstance(name, shape));
  overlayPrimitive = scene.primitives.add(new Cesium.Primitive({
    geometryInstances: instances,
    appearance: new Cesium.PerInstanceColorAppearance({ flat: true, closed: true, translucent: false }),
    asynchronous: false,
  }));
  scene.requestRender();
}

function applyOverlayColors() {
  // Before it is ready the colours set at build time still stand, and the next
  // refresh picks up anything that changed since.
  if (!overlayPrimitive?.ready) return;
  let changed = false;
  for (const name of overlays.keys()) {
    const { hex } = colorFor(buildingOccupancy(name));
    if (overlayColors.get(name) === hex) continue;
    const attrs = overlayPrimitive.getGeometryInstanceAttributes(name);
    if (!attrs) continue;
    attrs.color = Cesium.ColorGeometryInstanceAttribute.toValue(Cesium.Color.fromCssColorString(hex));
    overlayColors.set(name, hex);
    changed = true;
  }
  if (changed) scene.requestRender();
}

let lastStyleSignature = null;

function applyStyle() {
  applyOverlayColors();
  if (!buildingsTileset) return;

  const conditions = [];
  for (const name of knownBuildings()) {
    if (overlays.has(name)) continue;
    const occ = buildingOccupancy(name);
    if (!occ) continue;
    const safe = name.replace(/'/g, "\\'");
    const { hex, alpha } = colorFor(occ);
    conditions.push([`\${name} === '${safe}'`, `color('${hex}', ${alpha})`]);
  }
  conditions.push(['true', `color('${NO_DATA_HEX}', 1)`]);

  // Rebuilding the style makes every building re-evaluate, so only do it when
  // the colours actually changed.
  const signature = conditions.join('|');
  if (signature === lastStyleSignature) return;
  lastStyleSignature = signature;

  const inArea =
    `\${feature['cesium#longitude']} > ${AREA.west} && \${feature['cesium#longitude']} < ${AREA.east} && ` +
    `\${feature['cesium#latitude']} > ${AREA.south} && \${feature['cesium#latitude']} < ${AREA.north}`;

  // `hidden` is set on blocks standing where we draw our own (see claimTileBuildings).
  buildingsTileset.style = new Cesium.Cesium3DTileStyle({
    color: { conditions },
    show: `(${inArea}) && \${hidden} !== 1`,
  });
  scene.requestRender();
}

// ─── Building labels ──────────────────────────────────────────────────────────
// Floating names for the buildings we have data on. Positions come from the
// building tiles as they load (each building knows its own centre and height).
// Drawn as regular page text on top of the map (not inside it), so the names
// stay sharp even while the map drops resolution during a drag.
const labelled = new Set();
const labels = [];
const LABEL_RANGE_M = 2600;
// Ellipsoid height of the ground on campus. Campus is flat (±3 m), so labels use
// this instead of looking up terrain under every label (that cost dozens of
// extra terrain downloads on page load).
const APPROX_GROUND_M = CAMPUS.groundM;
const labelLayer = document.getElementById('labels');

// Places students go to study or hang out get their labels first.
const STUDY_TYPES = new Set(['library', 'study', 'atrium', 'union', 'dining', 'rec']);
function labelPriority(name) {
  const cfg = configFor(name);
  return cfg?.labelPriority ?? (STUDY_TYPES.has(cfg?.type) ? 1 : 0);
}

function wrapName(name, max = 22) {
  const lines = [''];
  for (const word of name.split(' ')) {
    const line = lines[lines.length - 1];
    if (line && (line + ' ' + word).length > max) lines.push(word);
    else lines[lines.length - 1] = line ? line + ' ' + word : word;
  }
  return lines;
}

function addLabel(name, lon, lat, aboveGroundM, absoluteM) {
  if (labelled.has(name)) return;
  labelled.add(name);

  const el = document.createElement('div');
  el.className = 'map-label';
  const text = document.createElement('div');
  text.className = 'map-label-text';
  const lines = wrapName(BUILDINGS[name]?.label ?? name);
  text.textContent = lines.join('\n');
  const dot = document.createElement('div');
  dot.className = 'map-label-dot';
  el.append(text, dot);
  el.classList.add('is-hidden');
  labelLayer.append(el);

  const label = {
    name, el, lines, visible: false,
    position: Cesium.Cartesian3.fromDegrees(lon, lat, absoluteM ?? APPROX_GROUND_M + aboveGroundM),
  };
  labels.push(label);
  scene.requestRender();
}

// Position every label for the current view, hiding ones that are far away,
// off screen, or would overlap a nearer label.
const scratchWindow = new Cesium.Cartesian2();
function placeLabels() {
  const camera = viewer.camera.positionWC;
  const width = scene.canvas.clientWidth, height = scene.canvas.clientHeight;
  // Nearest labels win, with two adjustments: study spots (libraries, the
  // Union, dining, gyms, BIF…) count as nearer so they survive crowding, and a
  // label already on screen gets a 15% head start so labels don't flicker.
  const items = labels
    .map(label => {
      const distance = Cesium.Cartesian3.distance(camera, label.position);
      const priority = labelPriority(label.name);
      return { label, distance, rank: distance * (priority ? 0.65 : 1) * (label.visible ? 0.85 : 1) };
    })
    .sort((a, b) => a.rank - b.rank);

  const taken = [];
  for (const { label, distance } of items) {
    let win = null;
    if (distance < LABEL_RANGE_M) {
      win = Cesium.SceneTransforms.wgs84ToWindowCoordinates(scene, label.position, scratchWindow);
    }
    let show = !!win && win.x > -100 && win.x < width + 100 && win.y > -50 && win.y < height + 100;
    let scale = 1;
    if (show) {
      scale = distance < 400 ? 1.05 : 1.05 - 0.3 * (distance - 400) / (LABEL_RANGE_M - 400);
      const w = Math.max(...label.lines.map(l => l.length)) * 7.2 * scale + 10;
      const h = label.lines.length * 16 * scale + 14;
      const box = [win.x - w / 2, win.y - h, win.x + w / 2, win.y + 4];
      // A name sliced by the edge of the screen reads as a different building
      // ("Astronomy B", "Campus Recreation Cent"), which is worse than no name
      // at all. It can't be nudged inwards either, because the dot under it is
      // what says which building this is.
      show = box[0] > 2 && box[2] < width - 2;
      show = show && !taken.some(b => box[0] < b[2] && box[2] > b[0] && box[1] < b[3] && box[3] > b[1]);
      if (show) taken.push(box);
    }
    if (show) {
      label.el.style.transform =
        `translate(${win.x.toFixed(1)}px, ${win.y.toFixed(1)}px) translate(-50%, -100%) scale(${scale.toFixed(3)})`;
    }
    if (label.visible !== show) {
      label.visible = show;
      label.el.classList.toggle('is-hidden', !show);
    }
  }
}

scene.postRender.addEventListener(placeLabels);

// ─── Buildings OpenStreetMap never named ──────────────────────────────────────
// The 3D buildings are OSM data matched by name, and on this campus that misses
// a lot: Thompson Library, the main library, has no name in OSM at all, so it
// could never be labelled or flown to. Where the university's own register
// (data/<campus>/buildings.json) knows a building we have data for, its
// coordinates place a label even when no tile feature carries the name.
//
// Joined on the scheduling code, not the name — the name is exactly what the
// two sources disagree about.
function gisByCode() {
  const out = new Map();
  for (const b of Object.values(data.gis?.buildings || {})) {
    if (b.code && b.lat != null) out.set(b.code, b);
  }
  return out;
}

function codeFor(name) {
  return data.hours?.buildings?.[name]?.code
      ?? data.classActivity?.buildings?.[name]?.code
      ?? null;
}

/** The register's record for one of our buildings, or null if it has none. */
function gisFor(name) {
  const alias = GIS_ALIASES[name];
  if (alias) return data.gis?.buildings?.[alias] ?? null;
  return gisByCode().get(codeFor(name)) ?? null;
}

// Draw a building the tiles don't carry, from the university's own footprint.
// Same treatment Illinois gives Morrill Hall, just sourced rather than typed.
function addGisOverlay(name, b) {
  const base = CAMPUS.groundM;
  overlays.set(name, {
    outline: b.outline,
    baseM: base,
    fromGis: true,            // unlike the hand-drawn shapes, droppable
    // No height is published for any Ohio State building, so heightM is storeys
    // inferred from gross floor area over footprint area. It decides how tall
    // the block looks and nothing else — never a number we show.
    topM: base + (b.heightM ?? 12),
  });
}

function placeMissingBuildings() {
  if (!data.gis) return 0;
  let drawn = 0, labelledNow = 0;
  for (const name of knownBuildings()) {
    if (labelled.has(name)) continue;          // the tiles already named it
    const b = gisFor(name);
    if (!b) continue;
    if (b.outline && !overlays.has(name)) { addGisOverlay(name, b); drawn++; }
    addLabel(name, b.lon, b.lat, 10);
    labelledNow++;
  }
  if (drawn) {
    drawOverlays();
    applyStyle();
    // The tiles loaded before we knew which shapes we'd be drawing, so give
    // them a second pass to stand down where we now stand.
    claimLoadedTiles();
  }
  return { drawn, labelled: labelledNow };
}

// The tiles and the university rarely agree on a name: "Knowlton Hall" in the
// tiles, "Knowlton Architecture Building" in the class schedule. The register
// publishes both, so join through it rather than guessing at the names.
let registerNameIndex = null;
function registerNames() {
  if (registerNameIndex) return registerNameIndex;
  registerNameIndex = new Map();
  const ambiguous = new Set();
  const byCode = new Map();
  for (const name of knownBuildings()) {
    const code = codeFor(name);
    if (code) byCode.set(code, name);
  }
  for (const b of Object.values(data.gis?.buildings || {})) {
    const ours = byCode.get(b.code);
    if (!ours) continue;
    for (const alias of [b.name, ...(b.aliases || [])]) {
      const key = normaliseName(alias);
      if (!key || ambiguous.has(key)) continue;
      // Some aliases cover a whole complex ("COB" is four business-school
      // buildings). A name that means more than one building means nothing.
      if (registerNameIndex.has(key) && registerNameIndex.get(key) !== ours) {
        registerNameIndex.delete(key);
        ambiguous.add(key);
        continue;
      }
      registerNameIndex.set(key, ours);
    }
  }
  return registerNameIndex;
}

function normaliseName(name) {
  return String(name)
    .toLowerCase()
    .replace(/\s*\(\d+\)\s*$/, '')   // the register suffixes its own file number
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

// The published footprints of the buildings we have data on, with a bounding
// box each so a point test doesn't walk every outline.
let footprintIndex = null;
function knownFootprints() {
  if (footprintIndex) return footprintIndex;
  footprintIndex = [];
  const byCode = gisByCode();
  for (const name of knownBuildings()) {
    const b = byCode.get(codeFor(name));
    if (!b?.outline?.length) continue;
    footprintIndex.push({ name, outline: b.outline, box: boundingBox(b.outline) });
  }
  return footprintIndex;
}

function footprintAt(lon, lat) {
  for (const { name, outline, box } of knownFootprints()) {
    if (lon < box.west || lon > box.east || lat < box.south || lat > box.north) continue;
    if (pointInOutline(lon, lat, outline)) return name;
  }
  return null;
}

// Work out what each block in a tile is, and get out of our own way. Giving a
// block the name the university uses lets the ordinary style colour it, which
// is better than drawing a second block on top of it: the tiles' shapes are
// more detailed than the footprints we extrude, and two blocks in one place
// fight over every pixel they share.
function claimTileBuildings(tile) {
  if (!data.classActivity && !data.hours) {   // data not here yet — do it later
    pendingTiles.push(tile);
    return;
  }
  const content = tile.content;
  if (!content?.featuresLength) return;
  const known = new Set(knownBuildings());
  const join = registerNames();
  let restyle = false, dropped = false;

  for (let i = 0; i < content.featuresLength; i++) {
    const feature = content.getFeature(i);
    const lon = feature.getProperty('cesium#longitude');
    const lat = feature.getProperty('cesium#latitude');
    const tileName = feature.getProperty('name');

    let name = tileName && known.has(tileName) ? tileName : null;
    if (!name && tileName) name = join.get(normaliseName(tileName)) ?? null;
    // A block carrying no name of its own can't contradict one: if it stands
    // inside a footprint the university publishes, that is what it is.
    if (!name && !tileName && lon != null) name = footprintAt(lon, lat);

    if (!name) {
      // Still nothing, and it stands where we are drawing our own shape. Hide
      // it rather than let the two fight over the same space.
      if (lon != null && overlayCovering(lon, lat)) {
        feature.setProperty('hidden', 1);
        restyle = true;
      }
      continue;
    }
    if (name !== tileName) { feature.setProperty('name', name); restyle = true; }
    // The tiles carry it after all, so our own shape is the duplicate.
    if (overlays.get(name)?.fromGis) { overlays.delete(name); dropped = true; }
    if (labelled.has(name)) continue;
    const [labelLon, labelLat] = BUILDINGS[name]?.labelAt ?? [lon, lat];
    addLabel(name, labelLon, labelLat, feature.getProperty('cesium#estimatedHeight') || 10);
  }

  if (dropped) drawOverlays();
  if (restyle) { buildingsTileset.makeStyleDirty(); scene.requestRender(); }
}

function claimLoadedTiles() {
  (function walk(tile) {
    if (!tile) return;
    if (tile.content?.featuresLength) claimTileBuildings(tile);
    for (const child of tile.children || []) walk(child);
  })(buildingsTileset?.root);
}

// Centre of a polygon's area (not the average of its points, which leans
// toward curved edges that have many points).
function areaCentre(outline) {
  const [ox, oy] = outline[0];   // work relative to the first point for precision
  let area = 0, cx = 0, cy = 0;
  for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
    const xa = outline[j][0] - ox, ya = outline[j][1] - oy;
    const xb = outline[i][0] - ox, yb = outline[i][1] - oy;
    const cross = xa * yb - xb * ya;
    area += cross; cx += (xa + xb) * cross; cy += (ya + yb) * cross;
  }
  area /= 2;
  return [ox + cx / (6 * area), oy + cy / (6 * area)];
}

const pendingTiles = [];
function claimPendingTiles() {
  while (pendingTiles.length) claimTileBuildings(pendingTiles.pop());
}

function labelOverlays() {
  for (const [name, cfg] of Object.entries(BUILDINGS)) {
    const outline = cfg.shape?.outline;
    if (!outline) continue;
    const [lon, lat] = cfg.labelAt ?? areaCentre(outline);
    addLabel(name, lon, lat, 0, cfg.shape.topM + 2);
  }
}

// The picks sheet covers the bottom of a phone screen, including where the map
// credits sit. They have to stay visible, so its height is published to CSS
// rather than guessed at — it changes when the list does and when it collapses.
let publishSheetHeight = () => {};
(function trackSheetHeight() {
  const sheet = document.getElementById('pick');
  if (!sheet) return;
  const publish = () => document.documentElement.style.setProperty(
    '--sheet-h', `${Math.round(sheet.getBoundingClientRect().height)}px`);
  // A ResizeObserver alone reported 0 forever: it starts on a sheet that is
  // still `hidden`, and the first real layout didn't reach it. The explicit
  // triggers are the ones that actually change the height.
  if (window.ResizeObserver) new ResizeObserver(publish).observe(sheet);
  window.addEventListener('resize', publish);
  publishSheetHeight = publish;
  publish();
})();

document.getElementById('old-look')?.addEventListener('click', () => {
  track('design_switched', { to: 'classic', device: deviceKind() });
});

// ─── Tooltip ──────────────────────────────────────────────────────────────────
const tooltip  = document.getElementById('tooltip');
const ttName   = document.getElementById('tt-name');
const ttOcc    = document.getElementById('tt-occ');
const ttStatus = document.getElementById('tt-status');
const ttSource = document.getElementById('tt-source');
const ttNote   = document.getElementById('tt-note');
const ttFill   = document.getElementById('tt-fill');
const ttSpaces = document.getElementById('tt-spaces');

function occText(occ) {
  if (!occ) return { text: 'No data', color: '#5a6478' };
  if (occ.source === 'closed') return { text: occ.cardAccess ? 'Closed*' : 'Closed', color: '#5a6478' };
  if (occ.source === 'unknown') return { text: 'Hours unknown', color: '#5a6478' };
  // Open with nothing scheduled is a real answer, but it is not a measurement,
  // so it does not get a percentage.
  if (occ.source === 'open') return { text: 'Open · no classes', color: cssColor(0) };
  return { text: `${statusLabel(occ.value)} · ${Math.round(occ.value * 100)}%`, color: cssColor(occ.value) };
}

function renderSpaces(container, spaces) {
  container.replaceChildren();
  for (const { space, occ } of spaces || []) {
    const row = document.createElement('div');
    row.className = 'tt-row';
    const label = document.createElement('span');
    label.textContent = space;
    const value = document.createElement('span');
    const { text, color } = occText(occ);
    value.textContent = text;
    value.style.color = color;
    row.append(label, value);
    container.append(row);
  }
  container.hidden = !(spaces && spaces.length);
}

// For a building the map draws but has no hours or classes for: say so, rather
// than show a percentage we don't have.
function showBareTooltip(x, y, name) {
  ttName.textContent = name;
  ttOcc.textContent = '—';
  ttStatus.textContent = 'No data';
  ttStatus.style.color = '#5a6478';
  ttSource.textContent = '';
  ttNote.textContent = 'No hours published for this building';
  renderSpaces(ttSpaces, null);
  ttFill.style.width = '0%';
  placeTooltip(x, y);
}

function showTooltip(x, y, name, occ) {
  ttName.textContent = BUILDINGS[name]?.label ?? name;
  ttOcc.textContent = Math.round(occ.value * 100) + '%';
  const inactive = occ.source === 'closed' || occ.source === 'unknown';
  ttStatus.textContent = occ.source === 'closed' ? (occ.cardAccess ? 'Closed*' : 'Closed')
    : occ.source === 'unknown' ? 'Hours unknown'
    : statusLabel(occ.value);
  ttStatus.style.color = inactive ? '#5a6478' : cssColor(occ.value);
  ttSource.textContent = SOURCE_LABELS[occ.source] || '';
  ttNote.textContent = occ.note || '';
  renderSpaces(ttSpaces, occ.spaces);
  ttFill.style.width = (occ.value * 100) + '%';
  ttFill.style.background = cssColor(occ.value);

  placeTooltip(x, y);
}

function placeTooltip(x, y) {
  let tx = x + 18, ty = y - 20;
  if (tx + 250 > window.innerWidth)  tx = x - 268;
  const height = tooltip.offsetHeight || 200;
  if (ty + height > window.innerHeight) ty = y - height - 10;
  tooltip.style.left = tx + 'px';
  tooltip.style.top  = ty + 'px';
  tooltip.classList.add('show');
}

function hideTooltip() {
  tooltip.classList.remove('show');
}

// Which of our own shapes (if any) contains the point under the cursor.
function overlayAt(position) {
  if (!overlays.size) return null;
  let point = scene.pickPositionSupported ? scene.pickPosition(position) : undefined;
  if (!Cesium.defined(point)) {
    const ray = viewer.camera.getPickRay(position);
    point = ray && scene.globe.pick(ray, scene);
  }
  if (!Cesium.defined(point)) return null;

  const carto = Cesium.Cartographic.fromCartesian(point);
  const lon = Cesium.Math.toDegrees(carto.longitude);
  const lat = Cesium.Math.toDegrees(carto.latitude);
  return overlayCovering(lon, lat);
}

// Which of our own shapes, if any, stands over this point on the ground. Asked
// once per block in the tiles, so each shape keeps a box to be ruled out by.
function overlayCovering(lon, lat) {
  for (const [name, shape] of overlays) {
    const box = shape.box ?? (shape.box = boundingBox(shape.outline));
    if (lon < box.west || lon > box.east || lat < box.south || lat > box.north) continue;
    if (pointInOutline(lon, lat, shape.outline)) return name;
  }
  return null;
}

function boundingBox(outline) {
  let west = 180, east = -180, south = 90, north = -90;
  for (const [lon, lat] of outline) {
    if (lon < west) west = lon;
    if (lon > east) east = lon;
    if (lat < south) south = lat;
    if (lat > north) north = lat;
  }
  return { west, east, south, north };
}

function pointInOutline(lon, lat, outline) {
  let inside = false;
  for (let i = 0, j = outline.length - 1; i < outline.length; j = i++) {
    const [xi, yi] = outline[i], [xj, yj] = outline[j];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function buildingNameAt(position) {
  const overlay = overlayAt(position);
  if (overlay) return overlay;

  const picked = scene.pick(position);
  if (!Cesium.defined(picked)) return null;

  // Our own shapes (e.g. the dining hall) come back carrying their name.
  if (typeof picked.id === 'string') return overlays.has(picked.id) ? picked.id : null;

  if (!picked.getProperty) return null;
  const name = picked.getProperty('name');
  if (!name) return null;
  // A building we have no data for used to come back as null, so tapping it did
  // nothing at all. Someone on Reddit looked straight at Sherman Hall and asked
  // where it was: it is drawn, it just never answered. Give the name back and
  // let the caller say "no hours published" rather than ignoring the tap.
  const trimmed = String(name).trim();
  return knownBuildings().find(known => known === trimmed) || trimmed;
}

// Picking is expensive: at most once per frame, and never while dragging.
let dragging = false;
let pendingPick = null;

scene.canvas.addEventListener('pointerdown', () => { dragging = true; hideTooltip(); });
window.addEventListener('pointerup', () => { dragging = false; });

// A building counts as "looked at" after the tooltip has been up for a second,
// once per building per visit.
const viewedBuildings = new Set();
let hoverTimer = null;
let hoverName = null;

function noteHover(name, occ) {
  if (name === hoverName) return;
  hoverName = name;
  clearTimeout(hoverTimer);
  if (!name || viewedBuildings.has(name)) return;
  hoverTimer = setTimeout(() => {
    viewedBuildings.add(name);
    track('building_viewed', {
      building: name,
      status: occ.source === 'closed' ? 'closed' : occ.source === 'unknown' ? 'no data' : statusLabel(occ.value),
      source: SOURCE_LABELS[occ.source] || occ.source,
    });
  }, 1000);
}

function pickUnderMouse() {
  const position = pendingPick;
  pendingPick = null;
  const name = buildingNameAt(position);
  const occ = name ? buildingOccupancy(name) : null;
  if (name && !occ) {
    showBareTooltip(position.x, position.y, name);
    scene.canvas.style.cursor = 'pointer';
    noteHover(null);
  } else if (name && occ) {
    showTooltip(position.x, position.y, name, occ);
    // Closed buildings still show their tooltip on hover, but there's
    // nothing to click through to — no pointer cursor, no panel.
    scene.canvas.style.cursor = occ.source === 'closed' ? 'default' : 'pointer';
    noteHover(name, occ);
  } else {
    hideTooltip();
    scene.canvas.style.cursor = 'default';
    noteHover(null);
  }
}

const handler = new Cesium.ScreenSpaceEventHandler(scene.canvas);

handler.setInputAction((movement) => {
  if (dragging) return;
  if (!pendingPick) requestAnimationFrame(pickUnderMouse);
  pendingPick = Cesium.Cartesian2.clone(movement.endPosition);
}, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

// ─── Check-in panel ───────────────────────────────────────────────────────────
const panel      = document.getElementById('panel');
const panelName  = document.getElementById('panel-name');
const panelNow   = document.getElementById('panel-now');
const panelNote  = document.getElementById('panel-note');
const panelThanks = document.getElementById('panel-thanks');
const panelSpaces = document.getElementById('panel-spaces');
const panelQ      = document.getElementById('panel-q');
const checkinRow  = document.getElementById('checkin-row');
const wishThanks  = document.getElementById('wish-thanks');
let panelBuilding = null;
let panelSpace = null;

// The id check-ins are stored under: the space if one is picked, else the building.
function panelTarget() {
  return panelSpace ? spaceId(panelBuilding, panelSpace) : panelBuilding;
}

function renderSpacePicker(name) {
  const spaces = spacesOf(name);
  panelSpaces.replaceChildren();
  panelSpaces.hidden = !spaces.length;
  for (const space of spaces) {
    const button = document.createElement('button');
    button.className = 'space-btn' + (space === panelSpace ? ' selected' : '');
    button.textContent = space;
    button.addEventListener('click', () => {
      panelSpace = space;
      openPanel(name);
    });
    panelSpaces.append(button);
  }
}

// How long the panel stays untappable after it appears. Long enough to swallow
// the click belonging to the tap that opened it, short enough that a deliberate
// second tap never waits.
const PANEL_ARM_MS = 350;
let armTimer = null;

function armPanelLater() {
  panel.classList.remove('armed');
  clearTimeout(armTimer);
  armTimer = setTimeout(() => panel.classList.add('armed'), PANEL_ARM_MS);
}

function openPanel(name, keepThanks = false) {
  // Only re-arm when the panel is actually appearing or switching building —
  // not on the background check-in poll, which would keep going inert mid-tap.
  const freshOpen = !panel.classList.contains('show') || name !== panelBuilding;
  if (name !== panelBuilding) {
    panelBuilding = name;
    panelSpace = spacesOf(name)[0] || null;
  }
  renderSpacePicker(name);
  const occ = occupancyFor(panelTarget());
  const closed = occ?.source === 'closed';
  // Nothing published for this one at all. Say that plainly and don't ask how
  // busy it is — a report on a building with no hours has nothing to attach to.
  const unmapped = !occ && !knownBuildings().includes(name);
  panelName.textContent = name;
  panelNow.textContent = unmapped ? 'No hours published for this building'
    : !occ ? 'No data yet'
    : closed ? (occ.cardAccess ? 'Public doors locked · i-card may work'
                : occ.assumed ? 'Probably closed' : 'Closed right now')
    : occ.source === 'unknown' ? 'Hours not published — no estimate right now'
    : `${SOURCE_LABELS[occ.source]} · ${Math.round(occ.value * 100)}% full`;
  panelQ.hidden = closed || unmapped;
  checkinRow.hidden = closed || unmapped;
  renderRooms(name);
  panelNote.textContent = unmapped
    ? "On the map, but nobody publishes hours for it — so there's nothing to show."
    : closed
    // An assumed closure has to show its working — otherwise "probably closed"
    // is just as unexplained as the claim it replaced.
    ? (occ.assumed && occ.note ? closureReason(occ.note) : "Check-ins are off while it's closed.")
    : sharedCheckins()
    ? 'Shared with everyone using the map.'
    : 'Saved on this device only — no server yet.';
  if (!keepThanks) {
    panelThanks.textContent = '';
    clearWishlist();
  }
  if (freshOpen) armPanelLater();
  if (freshOpen) noteBuildingOpened();
  panel.classList.add('show');
  // Lets the stylesheet clear the legend out of the panel's way on a phone.
  document.body.classList.add('panel-open');
}

function closePanel() {
  panel.classList.remove('show', 'armed');
  document.body.classList.remove('panel-open');
  clearTimeout(armTimer);
  panelBuilding = null;
  panelSpace = null;
}

async function submitCheckin(level) {
  if (!panelBuilding) return;
  if (occupancyFor(panelTarget())?.source === 'closed') return;
  const report = { building: panelTarget(), level, at: Date.now(), mine: true };
  data.checkins.push(report);
  saveLocalCheckins();

  refresh({ keepThanks: true });
  panelThanks.textContent = sharedCheckins() ? 'Thanks — sharing…' : 'Thanks — the map has been updated.';

  const result = await sendCheckin(report);
  if (result === 'rate-limited') {
    // Already reported this building in the last minute — drop the duplicate,
    // and don't count it: a repeat tap isn't a new report. (Tracking this
    // before the server's answer used to record every tap of a rapid retry —
    // one visitor's 54 taps in 31 seconds looked like 54 check-ins.)
    data.checkins = data.checkins.filter(r => r !== report);
    saveLocalCheckins();
    refresh({ keepThanks: true });
    panelThanks.textContent = 'You just reported this one — try again in a minute.';
    return;
  }
  track('checkin_submitted', { building: report.building, level, device: deviceKind(), shared: result === 'ok' });
  panelThanks.textContent = result === 'ok' ? 'Thanks — everyone sees this now.'
    : sharedCheckins() ? 'Thanks — saved here (could not reach the server).'
    : 'Thanks — the map has been updated.';
  if (result === 'ok') fetchSharedCheckins();
}

document.querySelectorAll('#panel .checkin-btn').forEach(button => {
  button.addEventListener('click', () => submitCheckin(button.dataset.level));
});

// ─── Which features to build next ─────────────────────────────────────────────
// None of these exist. Tapping one records that somebody wanted it and says so
// plainly, so nobody is left waiting for a filter that isn't there. Compare the
// counts against `building_opened` to see what share of people asked for each.
const WISHES = {
  outlets:        'power outlets',
  quiet_vs_group: 'quiet vs group space',
  free_alert:     'an alert when a spot frees up',
  // Added 2026-10-15 to test a PM's hypothesis that people want more than
  // "what's generally busy" — specifically what's nearby and where their
  // friends are. Phrased as questions this map can't answer today.
  near_me:        'the closest open spot to me',
  friends:        'where friends are studying',
};

// Order is shuffled on every page load. With five buttons in a wrapping row,
// whichever sits first gets clicked more regardless of what it says, and the
// three originals would otherwise have a permanent head start over the two
// added later — which would make the comparison measure position, not want.
// Each click records where the button actually sat, so the bias can be checked
// rather than assumed away.
(function shuffleWishes() {
  const row = document.getElementById('wish-row');
  if (!row) return;
  const buttons = [...row.children];
  for (let i = buttons.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [buttons[i], buttons[j]] = [buttons[j], buttons[i]];
  }
  buttons.forEach(b => row.appendChild(b));
})();

function clearWishlist() {
  document.querySelectorAll('#wishlist .wish-btn.picked').forEach(b => b.classList.remove('picked'));
  wishThanks.textContent = '';
}

document.querySelectorAll('#wishlist .wish-btn').forEach(button => {
  button.addEventListener('click', () => {
    const feature = button.dataset.feature;
    const position = [...button.parentElement.children].indexOf(button) + 1;
    track('feature_interest', { feature, position, building: panelTarget(), device: deviceKind() });
    button.classList.add('picked');
    wishThanks.textContent = `Noted: ${WISHES[feature]}. Not built yet — this just tells me to.`;
  });
});
document.getElementById('panel-close').addEventListener('click', closePanel);

// ─── Return-intent prompt ───────────────────────────────────────────
// What this replaced and why: the first version asked *returning* visitors
// "did this help you find a study spot?" — Yes / Not really, no text box. That
// asks the people who did not churn, in a form that cannot produce a reason,
// and three weeks of it yielded 8 answers, 6 of them a dismissal. Nobody on
// the site can tell you why they stopped coming, because they are here. So
// first-timers get the forward-looking version instead — would you open this
// again, and if not, what is the actual reason — and the people who did come
// back get asked what nearly stopped them.
//
// "Returning" is judged the same way the shared check-in id and the ?nostats
// flag already are: a value kept in this browser's localStorage, never sent
// anywhere. No accounts, no cookies, so a different day on the same browser is
// the only signal available — good enough for "have they been here before?"
const SURVEY_FIRST_SEEN_KEY = 'uiucSpacesFirstSeen';
const SURVEY_DONE_KEY = 'uiucSpacesSurveyDone';   // the old Yes / Not really survey
const ASK_DONE_KEY = 'uiucSpacesAskDone';
const ASK_IDLE_MS = 30000;        // opened nothing: ask before they leave
const ASK_AFTER_OPEN_MS = 2500;   // found something: let them read it first

// Each reason is a hypothesis someone has actually argued for, so even a dozen
// taps separates them: habit (the map is a modest improvement over walking to
// your usual spot), credibility (the estimates are wrong), or scope (busyness
// was never the thing they wanted to know). "Other" is appended last on
// purpose — it is an escape hatch, not a competing explanation.
const ASK_REASONS = {
  probably_not: [
    ['habit', 'I already know my spots'],
    ['distrust', "Don't trust the numbers"],
    ['scope', 'Missing what I need'],
  ],
  yeah: [
    ['late_night', 'Late at night'],
    ['finals', 'Finals week'],
    ['friends', 'Studying with friends'],
  ],
};

const ASK_COPY = {
  probably_not: { reason: "Fair enough — what's the main reason?", text: 'What would have to change?' },
  yeah:         { reason: 'When would you reach for it?', text: 'What would make it worth opening?' },
  returned:     { reason: null, text: 'You came back — what nearly stopped you?' },
};

try {
  if (!localStorage.getItem(SURVEY_FIRST_SEEN_KEY)) {
    localStorage.setItem(SURVEY_FIRST_SEEN_KEY, new Date().toDateString());
  }
} catch (e) { /* private browsing, storage disabled, etc. */ }

function isReturningVisitor() {
  try {
    const firstSeen = localStorage.getItem(SURVEY_FIRST_SEEN_KEY);
    return !!firstSeen && firstSeen !== new Date().toDateString();
  } catch (e) { return false; }
}

// Anyone who answered or dismissed the old survey counts as asked. They already
// told us to leave them alone once; a new question is not a reason to re-ask.
function askDone() {
  try {
    return localStorage.getItem(ASK_DONE_KEY) === '1'
        || localStorage.getItem(SURVEY_DONE_KEY) === '1';
  } catch (e) { return false; }
}

function markAskDone() {
  try { localStorage.setItem(ASK_DONE_KEY, '1'); } catch (e) {}
}

const survey = document.getElementById('survey');
const askReasonRow = document.getElementById('survey-reasons');
const askTextBox = document.getElementById('survey-text');
let askIntent = null;        // 'yeah' | 'probably_not' | 'returned'
let askReason = null;
let askStage = 'intent';
let askVisitor = 'first';    // 'first' | 'returning'
let askShown = false;
let askTimer = null;

function askTrack(stage, extra = {}) {
  track('return_intent', {
    stage,
    intent: askIntent,
    reason: askReason,
    visitor: askVisitor,
    device: deviceKind(),
    ...extra,
  });
}

function askStep(id) {
  survey.querySelectorAll('.survey-step').forEach((step) => {
    step.hidden = step.id !== id;
  });
}

function dismissSurvey() {
  survey.classList.remove('show');
  document.body.classList.remove('survey-open');
}

function renderAskReasons(intent) {
  const options = [...ASK_REASONS[intent]];
  // Shuffled for the same reason the wishlist row is: four chips wrap to two
  // rows on a phone, so a fixed order would measure which chip sits first
  // rather than which reason is true. Each chip reports where it was drawn.
  for (let i = options.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [options[i], options[j]] = [options[j], options[i]];
  }
  options.push(['other', 'Other…']);
  askReasonRow.replaceChildren(...options.map(([value, label], index) => {
    const chip = document.createElement('button');
    chip.className = 'survey-chip';
    chip.textContent = label;
    chip.dataset.reason = value;
    chip.dataset.position = String(index + 1);
    return chip;
  }));
}

// The panel hides the prompt in CSS, so showing it over an open building would
// burn the one question we get on something nobody can see. Wait it out.
function showAskWhenFree() {
  if (askDone()) return;
  if (panelBuilding) {
    askTimer = setTimeout(showAskWhenFree, 1500);
    return;
  }
  askShown = true;
  survey.classList.add('show');
  // On a narrow screen the prompt and the legend want the same corner —
  // lets the stylesheet clear the legend out of its way, same as the panel.
  document.body.classList.add('survey-open');
  askTrack('shown');
}

function scheduleAsk(delay) {
  if (askShown || askDone()) return;
  clearTimeout(askTimer);
  askTimer = setTimeout(showAskWhenFree, delay);
}

function maybeShowSurvey() {
  // Opting out of stats means opting out of this too — same signal either way.
  if (analyticsExcluded() || askDone()) return;
  if (isReturningVisitor()) {
    // They are the proof that coming back is possible, so skip the intent
    // question and ask straight out what almost cost us the visit.
    askVisitor = 'returning';
    askIntent = 'returned';
    askStage = 'text';
    document.getElementById('survey-text-q').textContent = ASK_COPY.returned.text;
    askTextBox.placeholder = 'A sentence is plenty';
    askStep('survey-step-text');
    scheduleAsk(8000);
    return;
  }
  askStep('survey-step-intent');
  scheduleAsk(ASK_IDLE_MS);
}

// Opening a building is this product working. Asking then beats asking at a
// fixed 30 seconds, which on a phone at 11pm interrupts someone mid-search.
function noteBuildingOpened() {
  if (askVisitor !== 'first' || askShown || askDone()) return;
  scheduleAsk(ASK_AFTER_OPEN_MS);
}

survey.querySelectorAll('[data-intent]').forEach((button) => {
  button.addEventListener('click', () => {
    askIntent = button.dataset.intent;
    askStage = 'reason';
    askTrack('intent');
    document.getElementById('survey-reason-q').textContent = ASK_COPY[askIntent].reason;
    renderAskReasons(askIntent);
    askStep('survey-step-reason');
  });
});

askReasonRow.addEventListener('click', (event) => {
  const chip = event.target.closest('.survey-chip');
  if (!chip) return;
  askReason = chip.dataset.reason;
  askStage = 'text';
  askTrack('reason', { position: Number(chip.dataset.position) });
  // The box follows every chip, not just "Other": the chip says which
  // hypothesis, a sentence says why, and whoever types is worth reading.
  const other = askReason === 'other';
  document.getElementById('survey-text-q').textContent =
    other ? ASK_COPY[askIntent].text : 'Anything you want to add?';
  askTextBox.placeholder = other ? 'A sentence is plenty' : 'Optional';
  askStep('survey-step-text');
  // Only "Other" owes us typing, so only "Other" is worth throwing a phone
  // keyboard over the map for.
  if (other) askTextBox.focus();
});

document.getElementById('survey-send').addEventListener('click', () => {
  const text = askTextBox.value.trim().slice(0, 280);
  if (text) askTrack('text', { text });
  markAskDone();
  askStep('survey-step-done');
  setTimeout(dismissSurvey, 1500);
});

document.getElementById('survey-close').addEventListener('click', () => {
  // Kept as an answer rather than silence: a dismissal at the first question
  // means something different from one after three, and the old survey's 6
  // dismissals out of 8 were the most informative thing it ever produced.
  askTrack('dismissed', { at_stage: askStage });
  markAskDone();
  dismissSurvey();
});

// ─── Report a problem ─────────────────────────────────────────────────────────
// A box rather than a mailto. An email client is a wall: it exposes the
// reporter's address, takes them off the page, and most people on a phone
// never finish. This sends the text straight to the analytics the rest of the
// site already uses, so a correction costs one sentence and a tap.
//
// It is the only way to find out whether the published hours are right.
// scripts/hours_accuracy.mjs assumes 93% for them because nobody has checked a
// schedule against a real door -- "Thompson shows closed and I am sitting in
// it" IS that check, and it arrives here.
const reportCard = document.getElementById('report');
const reportText = document.getElementById('report-text');

function openReport(from) {
  if (!reportCard) return;
  reportCard.hidden = false;
  // Force a reflow so the transition starts from the hidden state. A
  // requestAnimationFrame would be the usual way, but it does not fire in a
  // backgrounded tab -- which left the box present, focusable and completely
  // invisible, because `hidden` had already been cleared.
  void reportCard.offsetHeight;
  reportCard.classList.add('show');
  document.getElementById('report-step-ask').hidden = false;
  document.getElementById('report-step-done').hidden = true;
  reportText.value = '';
  reportText.focus();
  track('report_opened', { from, device: deviceKind() });
}

function closeReport() {
  if (!reportCard) return;
  reportCard.classList.remove('show');
  setTimeout(() => { reportCard.hidden = true; }, 220);
}

document.getElementById('report-link')?.addEventListener('click', () => openReport('hint'));
document.getElementById('report-link-sheet')?.addEventListener('click', () => openReport('sheet'));
document.getElementById('report-close')?.addEventListener('click', closeReport);

document.getElementById('report-send')?.addEventListener('click', () => {
  const text = reportText.value.trim().slice(0, 400);
  if (!text) { reportText.focus(); return; }
  // Whatever building is open travels with it: most reports will be about the
  // one they are looking at, and it saves them naming it.
  track('report_sent', {
    text,
    building: panelTarget(),
    device: deviceKind(),
    at: `${campusNow().date} ${Math.floor(campusNow().time)}:00`,
  });
  document.getElementById('report-step-ask').hidden = true;
  document.getElementById('report-step-done').hidden = false;
  setTimeout(closeReport, 1800);
});

// Escape closes it, like every other panel here.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && reportCard && !reportCard.hidden) closeReport();
});


handler.setInputAction((click) => {
  const name = buildingNameAt(click.position);
  const occ = name ? buildingOccupancy(name) : null;
  // Closed buildings have nothing to check in on — skip the panel entirely
  // so people aren't clicking through a popup that can't do anything.
  if (name && occ?.source !== 'closed') {
    openPanel(name);
    // Kept as its own event so "most-opened buildings" stays a list of places
    // we actually cover — and so this becomes the list of buildings worth
    // finding hours for next, the way Beckman was.
    if (!occ && !knownBuildings().includes(name)) {
      track('unmapped_building_opened', { building: name, device: deviceKind() });
    } else {
      track('building_opened', { building: name, device: deviceKind(), source: SOURCE_LABELS[occ?.source] || 'none' });
    }
  } else {
    closePanel();
  }
}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

// ─── Summary chips ────────────────────────────────────────────────────────────
function updateStats() {
  let quiet = 0, moderate = 0, busy = 0;
  for (const name of knownBuildings()) {
    const occ = buildingOccupancy(name);
    if (!occ || occ.source === 'closed' || occ.source === 'unknown') continue;
    if (occ.value < 0.4) quiet++;
    else if (occ.value < 0.7) moderate++;
    else busy++;
  }
  document.getElementById('s-quiet').textContent = quiet;
  document.getElementById('s-mod').textContent   = moderate;
  document.getElementById('s-busy').textContent  = busy;
}

function updateHeader() {
  const sources = [];
  if (data.popularTimes?.places) sources.push('Google');
  if (data.classActivity?.buildings) sources.push('class schedules');
  const period = calendarPeriod(campusNow().date);
  const base = sources.length
    ? `Live estimates from ${sources.join(' + ')}`
    : CAMPUS.subtitle;
  document.getElementById('header-sub').textContent = period.label ? `${base} · ${period.label}` : base;
}

// ─── Study picks card ─────────────────────────────────────────────────────────
const pickCard = document.getElementById('pick');
const pickList = document.getElementById('pick-list');
const pickNote = document.getElementById('pick-note');
const pickToggle = document.getElementById('pick-toggle');

// Collapsing is remembered per browser: the card is worth about a fifth of a
// phone screen, and someone who has decided they don't want it there shouldn't
// have to dismiss it again on every visit. Same localStorage treatment as the
// other preferences here — it can throw outright in private mode, so every
// read and write is guarded and the card simply starts expanded if it fails.
const PICKS_COLLAPSED_KEY = 'uiucSpacesPicksCollapsed';

function picksCollapsed() {
  try { return localStorage.getItem(PICKS_COLLAPSED_KEY) === '1'; } catch (e) { return false; }
}

function setPicksCollapsed(collapsed) {
  try {
    if (collapsed) localStorage.setItem(PICKS_COLLAPSED_KEY, '1');
    else localStorage.removeItem(PICKS_COLLAPSED_KEY);
  } catch (e) { /* preference just won't survive the session */ }
  applyPicksCollapsed();
}

function applyPicksCollapsed() {
  const collapsed = picksCollapsed();
  pickCard.classList.toggle('is-collapsed', collapsed);
  publishSheetHeight();
  pickToggle.setAttribute('aria-expanded', String(!collapsed));
  pickToggle.title = collapsed ? 'Show study picks' : 'Hide study picks';
  pickToggle.setAttribute('aria-label', pickToggle.title);
}

pickToggle.addEventListener('click', () => {
  const collapsed = !picksCollapsed();
  setPicksCollapsed(collapsed);
  track('picks_toggled', { collapsed, device: deviceKind() });
});

// Same tap-to-slide as the picks above it, with its own remembered state —
// wanting the picks and wanting a room list are different wants.
document.getElementById('browse-all')?.addEventListener('click', openBrowse);
document.getElementById('browse-when-toggle')?.addEventListener('click', ev => {
  const wrap = document.getElementById('browse-when');
  const open = wrap.classList.contains('is-collapsed');
  wrap.classList.toggle('is-collapsed', !open);
  ev.currentTarget.setAttribute('aria-expanded', String(open));
  if (open) applyBrowseWhen(true);
});
document.getElementById('browse-note')?.addEventListener('click', ev => ev.currentTarget.classList.toggle('is-open'));
document.getElementById('browse-search')?.addEventListener('input', ev => {
  browseQuery = ev.target.value;
  renderBrowse({ seatWheels: false });
});
document.getElementById('browse-date')?.addEventListener('change', () => {
  const { date, time } = readWheels();
  setBrowseAt(date, time, true);      // leave the time wheels where they are
  track('browse_date_changed', { device: deviceKind() });
});

// One listener per wheel. Scroll-snap handles the feel; this only has to
// notice when a flick has come to rest, which a short debounce does — the
// scrollend event is still missing on Safari.
for (const id of ['wheel-hour', 'wheel-min', 'wheel-ampm']) {
  const el = document.getElementById(id);
  if (!el) continue;
  el.addEventListener('scroll', () => {
    if (Date.now() - seatedAt < SEAT_QUIET_MS) return;   // we moved it, not a finger
    markWheel(el, wheelIndex(el));            // highlight follows immediately
    clearTimeout(wheelSettle);
    wheelSettle = setTimeout(() => {
      const { date, time } = readWheels();
      setBrowseAt(date, time, true);
      track('browse_time_changed', { device: deviceKind() });
    }, 140);
  }, { passive: true });
  // Keyboard: the wheels are focusable, so arrows should move them.
  el.addEventListener('keydown', ev => {
    const step = ev.key === 'ArrowDown' ? 1 : ev.key === 'ArrowUp' ? -1 : 0;
    if (!step) return;
    ev.preventDefault();
    el.scrollTop = Math.max(0, (wheelIndex(el) + step) * WHEEL_ROW);
  });
}
document.getElementById('browse-now')?.addEventListener('click', () => {
  browseAt = null;
  renderBrowse();
});
document.getElementById('browse-backdrop')?.addEventListener('click', closeBrowse);
// Escape backs out one level: out of a building to the list, then out entirely.
document.addEventListener('keydown', ev => {
  if (ev.key !== 'Escape' || !browseIsOpen()) return;
  if (browseBuilding) { browseBuilding = null; renderBrowse(); }
  else closeBrowse();
});
document.getElementById('browse-close')?.addEventListener('click', closeBrowse);
document.getElementById('browse-back')?.addEventListener('click', () => {
  browseBuilding = null;
  renderBrowse();
});
document.getElementById('browse-body')?.addEventListener('click', ev => {
  const row = ev.target.closest('.browse-row');
  if (!row) return;
  browseBuilding = decodeURIComponent(row.dataset.building);
  renderBrowse();
  track('browse_building', { building: browseBuilding, device: deviceKind() });
});

/**
 * Ships to everyone, but a PostHog flag can switch it off without a deploy.
 * Unknown means on: the flag is undefined whenever analytics hasn't loaded or
 * is opted out via ?nostats=1, and the card should still work in those cases.
 */
function picksEnabled() {
  try { return window.posthog?.isFeatureEnabled?.('study-picks') !== false; }
  catch (e) { return true; }
}

// Which pick the camera is currently zoomed into, so tapping it again zooms
// back out. Kept here rather than read off the DOM because the card re-renders
// on every check-in poll, which would throw the state away.
let zoomedPick = null;

/**
 * Zoom to a pick, retrying briefly if it isn't on the map yet. Buildings are
 * labelled as their tiles arrive, which finishes a few seconds after the card
 * is already on screen and tappable, so an early tap would otherwise find no
 * position and silently do nothing at all.
 */
function zoomToPick(name, attempt = 0) {
  if (flyToBuilding(name)) return;
  if (attempt >= 12) return;   // give up after ~3s and leave the view alone
  setTimeout(() => {
    if (zoomedPick === name) zoomToPick(name, attempt + 1);
  }, 250);
}

/**
 * Reflect the zoom state on the buttons. The active one says so in words as
 * well as colour — tapping a thing again to undo it isn't discoverable
 * otherwise, especially on a phone where there's no hover to hint at it.
 */
function markZoomedPick() {
  for (const el of pickList.querySelectorAll('.pick-item')) {
    const on = el.dataset.building === zoomedPick;
    el.classList.toggle('is-zoomed', on);
    el.setAttribute('aria-pressed', String(on));
    const meta = el.querySelector('.pick-meta');
    meta.textContent = on ? `${meta.dataset.base} · tap to zoom out` : meta.dataset.base;
  }
}

/**
 * A line for when most of campus is shut, or null during ordinary hours.
 * Counts only buildings we have an answer for: saying "most of campus is
 * closed" while 45 buildings are actually unknown would be claiming more than
 * we know, so those are left out of both sides of the comparison.
 */
function scarcityNote() {
  if (!CAMPUS_CONTENT.sayWhenShut) return null;
  const { date, time } = campusNow();
  let open = 0, closed = 0;
  for (const name of knownBuildings()) {
    const state = hoursStatus(name, date, time).state;
    if (state === 'open') open++;
    else if (state === 'closed') closed++;
  }
  if (!open || closed <= open) return null;
  return `Most of campus is shut now — ${open} of the ${open + closed} `
       + `we have hours for ${open === 1 ? 'is' : 'are'} still open.`;
}

function renderPicks() {
  if (!pickCard) return;
  if (!picksEnabled()) { pickCard.hidden = true; publishSheetHeight(); return; }

  const picks = studyPicks();
  pickCard.hidden = false;
  applyPicksCollapsed();

  if (!picks.length) {
    pickList.replaceChildren();
    pickNote.textContent = 'Nothing on the study list is open right now.';
    pickNote.hidden = false;
    return;
  }

  pickList.replaceChildren(...picks.map(({ name, occ, until }) => {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = 'pick-item';
    item.dataset.building = name;

    const label = document.createElement('span');
    label.className = 'pick-name';
    label.textContent = pickLabel(name);

    const meta = document.createElement('span');
    meta.className = 'pick-meta';
    meta.dataset.base = until == null
      ? busyWord(occ)
      : `${busyWord(occ)} · until ${fmtHour(until)}`;
    meta.textContent = meta.dataset.base;

    item.append(label, meta);
    item.addEventListener('click', () => {
      if (zoomedPick === name) {
        zoomedPick = null;
        flyHome();
        track('pick_zoomed_out', { building: name, device: deviceKind() });
      } else {
        zoomedPick = name;
        zoomToPick(name);
        openPanel(name);
        track('pick_opened', { building: name, device: deviceKind(), source: occ.source });
      }
      markZoomedPick();
    });

    const li = document.createElement('li');
    li.append(item);
    return li;
  }));

  // A pick can drop out of the list as the hour changes. Leaving the state
  // pointing at a button that's gone would strand the view zoomed in with
  // nothing left to tap to get back out.
  if (zoomedPick && !picks.some(p => p.name === zoomedPick)) zoomedPick = null;
  markZoomedPick();

  // Late on, the map behind this list is mostly dark -- at Ohio State 11pm
  // leaves 5 buildings open out of 93, because that campus shuts earlier than
  // Illinois does. A dark map reads as a broken one unless something says
  // otherwise, and 11pm is exactly when people open this. So when more is shut
  // than open, the sheet says so, which turns the emptiness into the answer.
  const scarce = scarcityNote();
  pickNote.textContent = scarce ?? '';
  pickNote.hidden = !scarce;
  publishSheetHeight();   // the list just changed shape; the credits sit on it

  // Someone who reads the sheet and leaves looks exactly like someone who
  // bounced: both open no building. Recording that the list was on screen, and
  // whether it was open, is the only way to tell a satisfied visit from a
  // wasted one. Once per visit — it re-renders every five minutes.
  if (!picksSeenLogged) {
    picksSeenLogged = true;
    track('picks_seen', {
      count: picks.length,
      collapsed: pickCard.classList.contains('is-collapsed'),
      device: deviceKind(),
    });
  }
}
let picksSeenLogged = false;

function refresh({ keepThanks = false } = {}) {
  updateHeader();
  applyStyle();
  updateStats();
  renderPicks();
  if (panelBuilding) openPanel(panelBuilding, keepThanks);
}

// ─── Start ────────────────────────────────────────────────────────────────────
(async function start() {
  // Buildings take longest, so start them first; they're coloured once our
  // data arrives.
  const buildingsLoading = loadBuildings();
  const [classActivity, popularTimes, hours, gis, drawTile] = await Promise.all([
    loadJson(`${CAMPUS.dataDir}/class_activity.json`),
    loadJson(`${CAMPUS.dataDir}/popular_times.json`),
    loadJson(`${CAMPUS.dataDir}/building_hours.json`),
    // The university's own building register. Only Ohio State has one; the
    // 404 for Illinois is handled the same way popular_times.json is.
    loadJson(`${CAMPUS.dataDir}/buildings.json`),
    startBasemap(),
  ]);
  performance.mark('data-and-basemap-ready');
  if (drawTile) {
    viewer.imageryLayers.add(new Cesium.ImageryLayer(new VectorBasemapProvider(drawTile), { rectangle: AREA_RECT }));
  }
  data.classActivity = classActivity;
  data.popularTimes = popularTimes;
  data.hours = hours;
  data.gis = gis;

  updateHeader();
  createOverlays();
  labelOverlays();
  claimPendingTiles();
  refresh();
  // Before awaiting the buildings: neither of these needs the 3D map, and
  // queueing them behind it meant the room list arrived seconds late — or not
  // at all on a page where the tileset fails.
  loadRoomSchedule();
  loadRoomAvailability();
  await buildingsLoading;
  refresh();

  // Keep the live bookings current on the same cadence as everything else.
  setInterval(loadRoomAvailability, 5 * 60 * 1000);

  // Busyness changes with the hour; recheck every five minutes.
  setInterval(refresh, 5 * 60 * 1000);

  // Other people's reports: load now, then keep an open page current.
  if (sharedCheckins()) {
    fetchSharedCheckins();
    setInterval(fetchSharedCheckins, CHECKINS_POLL_MS);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') fetchSharedCheckins();
    });
  }
})();
