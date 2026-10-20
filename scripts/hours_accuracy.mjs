#!/usr/bin/env node
/**
 * Score the map's open/closed claims, using the real functions out of app.js.
 *
 * There was no way to tell whether a change to the hours logic helped or hurt.
 * The "94% Illinois / 83% Ohio State" figures that get quoted were worked out
 * once, by a method nobody wrote down, and nothing recomputed them. This does,
 * from data already in the repo, with no network and no API key.
 *
 * TWO MEASUREMENTS
 *
 * 1. HOLD-OUT (this is the measured part). For every building that DOES publish
 *    hours, hide them, ask the class-timetable fallback what it would have
 *    said, and score it against the published truth. That fallback carries
 *    every building with no published hours, so this is the honest way to ask
 *    how good those claims are without walking to the door.
 *
 * 2. CENSUS. What share of claims each source makes, and how often the map
 *    declines to answer at all.
 *
 * WHAT IS AND IS NOT MEASURED
 *
 * Only the fallback row is measured. The published rows are the assumptions in
 * ASSUMED below, because nobody has yet checked a published schedule against a
 * real door. The composite is therefore an estimate, and it moves when those
 * assumptions move -- which is why they are printed next to the result instead
 * of buried. Two composites are printed because the honest answer depends on a
 * convention nobody recorded: whether staying silent counts as being wrong.
 *
 * To make the published rows real, compare them against student check-ins: a
 * check-in arriving at a building the map calls closed is a measured error.
 *
 * HOW IT RUNS app.js
 *
 * app.js is browser code that builds a Cesium viewer. It is evaluated whole, in
 * a vm, against stubs permissive enough that every line runs -- so the harness
 * scores the SAME functions the site serves, rather than a copy that can drift.
 * Data is injected straight into `data` afterwards; fetch always rejects, so
 * the real loader cannot overwrite it.
 *
 * Usage:
 *   node scripts/hours_accuracy.mjs                      # every campus
 *   node scripts/hours_accuracy.mjs --campus osu
 *   node scripts/hours_accuracy.mjs --week 2026-11-09    # any Monday in term
 */

import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

// Accuracy of the published sources. NOT measured -- see the header.
const ASSUMED = {
  'published schedule': 0.93,   // a weekly pattern: registrar, spreadsheet, unit page
  'dated feed':         0.97,   // exact hours for that date, refreshed weekly
  // A campus-wide RULE applied building by building ("academic buildings are
  // generally open 7am-9pm on weekdays"), not a schedule anyone published for
  // that building. It has no number here on purpose. 93% belongs to a source
  // that names each building's own hours, and handing the same figure to a
  // general rule turned Maryland from 51.6% to 92.2% on paper without a single
  // door being checked. It is left out of the composite and reported beside it.
  'campus-wide rule':   null,
  // A venue's game schedule says when a game is on, not when the doors are open:
  // a day with no game is "probably closed", which the schedule cannot confirm
  // (the stadium hosts other events). Unmeasured for the same reason as the rule.
  'event schedule':     null,
};

// What assumedStatus() stamps on a claim it derived from the class timetable.
const FALLBACK_SOURCE = 'assumed from the class timetable';
const FALLBACK = 'class-timetable fallback';

const HOURS   = [8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23];
const SAMPLED = [8, 10, 12, 14, 16, 18, 20, 22];
const EVENING = [18, 19, 20, 21, 22, 23];

const CAMPUSES = { uiuc: 'data', osu: 'data/osu', umd: 'data/umd' };

const readJson = (p) => {
  try { return JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8')); } catch { return null; }
};

/** Permissive stand-ins for everything app.js touches on its way up. */
function browserStubs(campus) {
  const anything = new Proxy(function () {}, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => 0 : anything),
    set: () => true, apply: () => anything, construct: () => anything,
  });
  const real = { dataset: { campus }, src: 'http://localhost/basemap-render.js?v=1',
                 value: '', hidden: true, textContent: '', children: [],
                 classList: anything, style: anything };
  const el = new Proxy(real, {
    get: (t, k) => k in t ? t[k]
      : k === 'querySelector' ? () => el
      : k === 'querySelectorAll' ? () => [] : anything,
    set: (t, k, v) => { t[k] = v; return true; },
  });
  const doc = { documentElement: el, body: el, head: el, hidden: false,
                getElementById: () => el, querySelector: () => el, querySelectorAll: () => [],
                addEventListener() {}, createElement: () => el, createElementNS: () => el,
                createTextNode: () => el };
  return {
    Cesium: anything, document: doc,
    window: { addEventListener() {}, matchMedia: () => ({ matches: false, addEventListener() {} }),
              location: { search: '' } },
    location: { search: '', href: 'http://localhost/', hostname: 'localhost', origin: 'http://localhost' },
    localStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    navigator: { userAgent: 'node' },
    // Always rejects: the real loader must not overwrite the injected data.
    fetch: () => Promise.reject(new Error('the accuracy harness does not use the network')),
    performance: anything, requestAnimationFrame: () => 0,
    IntersectionObserver: class { observe() {} disconnect() {} },
    ResizeObserver: class { observe() {} disconnect() {} },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    CustomEvent: class {}, Event: class {},
    setTimeout, clearTimeout, setInterval, clearInterval,
    console: { ...console, log() {}, warn() {}, error() {} },   // app.js chatter stays out of the report
    Intl, Date, Math, JSON, URL, URLSearchParams,
  };
}

function loadCampus(campus) {
  const dir = CAMPUSES[campus];
  if (!dir) throw new Error(`unknown campus "${campus}" (expected: ${Object.keys(CAMPUSES).join(', ')})`);
  const injected = {
    hours:         readJson(path.join(dir, 'building_hours.json')),
    classActivity: readJson(path.join(dir, 'class_activity.json')),
    popularTimes:  readJson(path.join(dir, 'popular_times.json')),
    gis:           readJson(path.join(dir, 'buildings.json')),
  };
  if (!injected.hours || !injected.classActivity) {
    throw new Error(`missing building_hours.json or class_activity.json under ${dir}/`);
  }

  // Appended INSIDE the script: app.js's top-level `const`s are lexically
  // scoped and cannot be reached from outside it.
  const bridge = `
    data.hours = __injected.hours;
    data.classActivity = __injected.classActivity;
    data.popularTimes = __injected.popularTimes;
    data.gis = __injected.gis;
    globalThis.__api = { hoursStatus, assumedStatus, publishedRanges, knownBuildings,
                         entries: () => data.hours.buildings };
  `;
  const ctx = vm.createContext({ ...browserStubs(campus), __injected: injected });
  ctx.globalThis = ctx;
  new vm.Script(fs.readFileSync(path.join(ROOT, 'app.js'), 'utf8') + '\n;' + bridge)
    .runInContext(ctx);
  return ctx.__api;
}

const weekFrom = (iso) => Array.from({ length: 7 }, (_, i) => {
  const d = new Date(iso + 'T12:00:00Z');
  d.setUTCDate(d.getUTCDate() + i);
  return d.toISOString().slice(0, 10);
});

/**
 * Which kind of source answered, or null when the map stayed silent.
 * Decided from the DATA, not from source names, so it works on either campus:
 * a feed that published exact hours for this date is a different quality of
 * claim from a weekly pattern, whoever wrote it.
 */
function pathOf(status, entry, date) {
  if (status.state === 'unknown') return null;
  if (status.source === FALLBACK_SOURCE) return FALLBACK;
  if (entry?.generalRule) return 'campus-wide rule';
  if (entry?.eventVenue) return 'event schedule';
  if (entry?.dates && date in entry.dates) return 'dated feed';
  return 'published schedule';
}

function holdOut(api, days, hours) {
  let correct = 0, saidOpenWasClosed = 0, saidClosedWasOpen = 0, declined = 0;
  for (const [name, entry] of Object.entries(api.entries())) {
    // A general rule is not independent ground truth: Maryland's is built from
    // the same class windows the fallback reads, plus 7am-9pm, so scoring the
    // fallback against it measures how well it agrees with itself.
    if (entry.generalRule || entry.eventVenue) continue;
    for (const day of days) {
      const truth = api.publishedRanges(entry, day);
      if (truth == null) continue;                 // nothing published to score against
      for (const h of hours) {
        const guess = api.assumedStatus(name, day, h);
        if (guess.state === 'unknown') { declined++; continue; }
        const trulyOpen = truth.some(([o, c]) => h >= o && h < c);
        if ((guess.state === 'open') === trulyOpen) correct++;
        else if (guess.state === 'open') saidOpenWasClosed++;
        else saidClosedWasOpen++;
      }
    }
  }
  const scored = correct + saidOpenWasClosed + saidClosedWasOpen;
  return { scored, declined, correct, saidOpenWasClosed, saidClosedWasOpen,
           accuracy: scored ? correct / scored : null };
}

function census(api, days, hours) {
  const entries = api.entries();
  const counts = {};
  let silent = 0, total = 0;
  for (const name of api.knownBuildings()) {
    for (const day of days) for (const h of hours) {
      total++;
      const p = pathOf(api.hoursStatus(name, day, h), entries[name], day);
      if (!p) { silent++; continue; }
      counts[p] = (counts[p] || 0) + 1;
    }
  }
  return { total, silent, claims: total - silent, silentShare: silent / total, counts };
}

const pct = (x) => x == null ? '   n/a' : (x * 100).toFixed(1).padStart(5) + '%';

function report(campus, weekStart) {
  const api = loadCampus(campus);
  const days = weekFrom(weekStart);
  const all   = census(api, days, HOURS);
  const fbAll = holdOut(api, days, SAMPLED);
  const fbEve = holdOut(api, days, EVENING);
  const rateOf = (p, fb) => p === FALLBACK ? fb : ASSUMED[p];
  const ruled = (all.counts['campus-wide rule'] ?? 0) + (all.counts['event schedule'] ?? 0);

  console.log(`\n=== ${campus.toUpperCase()} — week of ${weekStart} ===`);
  console.log(`${api.knownBuildings().length} buildings · ${all.total} building-hours · ` +
              `${all.claims} claims · silent ${pct(all.silentShare)}\n`);
  console.log('  source                     share   accuracy  basis');
  for (const [p, n] of Object.entries(all.counts).sort((a, b) => b[1] - a[1])) {
    console.log(`  ${p.padEnd(24)} ${pct(n / all.claims)}  ${pct(rateOf(p, fbAll.accuracy))}  ` +
                (p === FALLBACK ? 'MEASURED (hold-out)'
                  : (p === 'campus-wide rule' || p === 'event schedule') ? 'UNMEASURED — no ground truth'
                  : 'assumed'));
  }

  // Over the claims that HAVE a number. A row with no rate is not counted as
  // right or as wrong; it is reported separately so that nobody reads the
  // composite as covering it.
  const rated = all.claims - ruled;
  const composite = (fb) => rated === 0 ? null : Object.entries(all.counts)
    .filter(([p]) => rateOf(p, fb) != null)
    .reduce((sum, [p, n]) => sum + (n / rated) * rateOf(p, fb), 0);
  const allDay = composite(fbAll.accuracy), evening = composite(fbEve.accuracy);

  console.log(`\n  hold-out all day  ${pct(fbAll.accuracy)}  ${fbAll.correct}/${fbAll.scored} ` +
              `· declined ${fbAll.declined} · ${fbAll.saidOpenWasClosed} said open when closed ` +
              `· ${fbAll.saidClosedWasOpen} said closed when open`);
  console.log(`  hold-out evening  ${pct(fbEve.accuracy)}  ${fbEve.correct}/${fbEve.scored}`);
  console.log(`\n  ESTIMATE  of claims made   all day ${pct(allDay)}   evening ${pct(evening)}`);
  console.log(`            of every slot     all day ${pct(allDay == null ? null : allDay * (1 - all.silentShare))}` +
              `   evening ${pct(evening == null ? null : evening * (1 - all.silentShare))}   (silence counted as wrong)`);
  if (ruled) {
    console.log(`\n  NOT IN THE ESTIMATE  ${pct(ruled / all.claims)} of claims come from a campus-wide rule ` +
                `or an event schedule, with no ground truth to score them against.`);
    console.log('  The figures above cover only the other ' + pct(rated / all.claims).trim() + '.');
  }
}

process.on('unhandledRejection', () => {});   // app.js's own loaders, which cannot reach the network

const args = process.argv.slice(2);
const at = (f) => args.includes(f) ? args[args.indexOf(f) + 1] : null;
const week = at('--week') ?? '2026-10-19';
const only = at('--campus');
for (const campus of only ? [only] : Object.keys(CAMPUSES)) report(campus, week);
console.log();
