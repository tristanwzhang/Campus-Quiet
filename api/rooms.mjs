// Live study-room availability, proxied from the libraries' own booking systems.
//
// Why this exists at all: LibCal answers a public, key-less call, but it sends
// no CORS headers, so the map cannot read it from the browser — verified
// 2026-10-16 from campusquiet.com, which fails with a plain "Failed to fetch".
// A proxy is the only way, and this is the site's first server-side component.
//
// What a "free room" means here: LibCal returns `slots` a person is allowed to
// BOOK and `bookings` already taken. A free slot therefore means nobody has
// reserved that room for that half hour — NOT that the room is empty. The two
// are different claims and the map must not blur them, so this endpoint returns
// counts of reservable rooms and the wording around it says reservable.

const CAMPUSES = {
  // Ohio State's main libraries (Thompson, 18th Avenue) are NOT here: their
  // booking app at libraryroombooking.cloud.osu.edu redirects to a university
  // login, so there is nothing public to read. Only the Health Sciences
  // Library publishes through LibCal, and it sits in Prior Hall.
  osu: {
    host: 'https://hsl-osu.libcal.com',
    locations: [
      { lid: '694', gid: '24674', building: 'Prior Hall', label: 'Health Sciences Library' },
    ],
  },

  // Maryland, enabled 2026-10-19. The lid-to-building question this comment
  // used to flag answered itself: LibCal's own location names state the host
  // building ("Art Library in Art Sociology Building", "STEM Library in
  // William E. Kirwan Hall"), so nothing here is a guess. Building names are
  // the ones Testudo's class data uses, because that is what the map joins on.
  //
  // Measured 2026-10-19: 96 bookable rooms, against Ohio State's 7 — this is
  // the one feature where Maryland has by far the most to show.
  //
  // McKeldin's sub-locations (lid 23065 Terrapin Learning Commons group study,
  // 23067 study carrels, 23082, 23071, 30085, 40070) are NOT listed. They are
  // category filters inside lid 2552 rather than separate locations: each
  // returns zero slots of its own, and adding them would have double-counted
  // McKeldin's 81 rooms.
  umd: {
    host: 'https://umd.libcal.com',
    locations: [
      { lid: '2552',  building: 'McKeldin Library',                      label: 'McKeldin Library' },
      { lid: '6745',  building: 'William E. Kirwan Hall',                label: 'STEM Library' },
      { lid: '14006', building: 'Clarice Smith Performing Arts Center',  label: 'Michelle Smith Performing Arts Library' },
      { lid: '14005', building: 'Parren J. Mitchell Art-Sociology Bldg.', label: 'Art Library' },
    ],
  },

  // Verified available and ready to switch on, but deliberately not enabled:
  //
  //   uoft  https://libcal.library.utoronto.ca lid 3320 (Zeidler), more libraries exist
  //
  // It needs its lid-to-BUILDING mapping confirmed first — a lid names a
  // library, and this map joins on the building that library sits in, which is
  // the same distinction that made Ohio State's register work fiddly.
};

const WINDOW_MS = 5 * 60 * 1000;    // how long a cached answer stays fresh
const cache = new Map();            // survives between invocations on a warm instance

/** YYYY-MM-DD for a date in a given IANA zone. */
function dayIn(zone, date = new Date()) {
  return new Intl.DateTimeFormat('en-CA', { timeZone: zone }).format(date);
}

async function fetchGrid(host, lid, gid, day, nextDay) {
  const body = new URLSearchParams({
    lid, gid: gid ?? '0', eid: '-1', seat: '0', seatId: '0', zone: '0',
    start: day, end: nextDay, pageIndex: '0', pageSize: '100',
  });
  const res = await fetch(`${host}/spaces/availability/grid`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'X-Requested-With': 'XMLHttpRequest',
      // LibCal rejects the call without a Referer from its own site.
      'Referer': `${host}/spaces`,
      'User-Agent': 'Mozilla/5.0 (campusquiet.com room availability)',
    },
    body,
  });
  if (!res.ok) throw new Error(`libcal ${res.status}`);
  return res.json();
}

/**
 * Reduce a grid response to "how many rooms could be booked right now".
 *
 * Exported for tests: the arithmetic is the part worth checking, and it cannot
 * be checked against the live feed without waiting for a real booking.
 */
export function countFree(grid, nowIso) {
  const slots = grid?.slots ?? [];
  const booked = new Set(
    (grid?.bookings ?? [])
      .filter(b => b.start <= nowIso && nowIso < b.end)
      .map(b => String(b.itemId)),
  );
  const rooms = new Set(slots.map(s => String(s.itemId)));
  // Rooms with a slot covering this instant -- i.e. rooms the library is taking
  // bookings for right now. Outside opening hours there are none at all.
  const bookableNow = new Set(
    slots
      .filter(s => s.start <= nowIso && nowIso < s.end)
      .map(s => String(s.itemId)),
  );
  const freeNow = new Set([...bookableNow].filter(id => !booked.has(id)));
  // `total` counts rooms the feed knows about today, so "0 of 7" still reads
  // as a real answer rather than as missing data.
  //
  // `bookable` is what separates "every room is taken" from "the library is
  // shut". Both used to come out as "0 of 7 free to book right now", which is
  // badly wrong at 1am: it sends someone away believing the place is heaving
  // when it is closed and empty.
  return { free: freeNow.size, total: rooms.size, bookable: bookableNow.size };
}

/** "2026-10-16 14:05:00" in the campus's own zone, which is what LibCal compares against. */
function localStamp(zone, date = new Date()) {
  const p = new Intl.DateTimeFormat('en-CA', {
    timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).formatToParts(date).reduce((a, x) => (a[x.type] = x.value, a), {});
  return `${p.year}-${p.month}-${p.day} ${p.hour === '24' ? '00' : p.hour}:${p.minute}:${p.second}`;
}

export default async function handler(req, res) {
  const campusId = String(req.query?.campus ?? '').toLowerCase();
  const campus = CAMPUSES[campusId];
  if (!campus) {
    res.status(404).json({ error: 'unknown campus' });
    return;
  }

  const zone = campus.zone ?? 'America/New_York';
  const cached = cache.get(campusId);
  if (cached && Date.now() - cached.at < WINDOW_MS) {
    res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600');
    res.status(200).json({ ...cached.body, cached: true });
    return;
  }

  const today = dayIn(zone);
  const tomorrow = dayIn(zone, new Date(Date.now() + 86400000));
  const now = localStamp(zone);

  const buildings = {};
  const failed = [];
  await Promise.all(campus.locations.map(async loc => {
    try {
      const grid = await fetchGrid(campus.host, loc.lid, loc.gid, today, tomorrow);
      const { free, total, bookable } = countFree(grid, now);
      // Several libraries can share a building; add them up rather than
      // letting the last one win.
      const prev = buildings[loc.building] ?? { free: 0, total: 0, bookable: 0, sources: [] };
      buildings[loc.building] = {
        free: prev.free + free,
        total: prev.total + total,
        bookable: prev.bookable + bookable,
        sources: [...prev.sources, loc.label],
      };
    } catch (err) {
      // One library being unreachable must not blank the others.
      failed.push(loc.label);
    }
  }));

  const body = { campus: campusId, asOf: now, buildings, failed };
  cache.set(campusId, { at: Date.now(), body });
  // Let Vercel's edge hold it too, so a traffic spike doesn't become a spike
  // of requests at the library's booking system.
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600');
  res.status(200).json(body);
}
