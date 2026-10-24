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

export const CAMPUSES = {
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

  // U of T St. George, built 2026-10-21. Every lid below was checked against the
  // library's own page: LibCal names the library ("Space Availability - Gerstein
  // Library"), and library.utoronto.ca gives the address that places it in a
  // building (10 King's College Road is Sandford Fleming, 80 St. George is Lash
  // Miller, 1 Spadina Crescent is Daniels, 9 King's College Circle is Gerstein's
  // Sigmund Samuel building; the Map & Data Library is on Robarts' 5th floor).
  // Building names are the map's own, because that is what the class data joins on.
  //
  // Measured 2026-10-21: 138 bookable rooms in 11 buildings. NOT here: Robarts' own booking was
  // first thought unreachable; it is lid 3446, split by category below. The
  // Graham Library (lid 3483) is at 3 Devonshire Place, a building not on the map.
  utsg: {
    host: 'https://libcal.library.utoronto.ca',
    zone: 'America/Toronto',
    // Live public-computer availability in the libraries, from U of T's own Information
    // Commons status page (linked from the libraries' site as their "computer finder"; no
    // login). Summary page lists each library with "Total: N  Available: M of N". Keyed to the
    // building that library IS or sits in, by the address the page itself prints. Noranda
    // Earth Sciences (5 Bancroft Ave) is left out: that address does not match the map's.
    computers: {
      url: 'https://cafstatus.icicle.utoronto.ca/frontend/Web/Summary/StGeorge',
      buildings: {
        'John P. Robarts Research Library': 'Robarts Library',
        'Gerstein Science Information Centre': 'Sigmund Samuel Library Building',
        'Engineering & Computer Science Library': 'Sandford Fleming Building',
        'Mathematical Sciences Library': 'Bahen Centre for Information Technology',
        'Music Library': 'Edward Johnson Building',
        'OISE Library': 'Ontario Institute for Studies in Education',
        'John W. Graham Library': 'Trinity College & Residence',
        'John M. Kelly Library': 'John M. Kelly Library',
        'E. J. Pratt Library': 'E.J. Pratt Library',
        'Emmanuel College Library': 'Emmanuel College',
      },
    },
    locations: [
      { lid: '3324', building: 'Sigmund Samuel Library Building',          label: 'Gerstein Library' },
      { lid: '3473', building: 'Sandford Fleming Building',                label: 'Engineering & Computer Science Library' },
      { lid: '3301', building: 'Lash Miller Chemical Laboratories',        label: 'Chemistry Library' },
      { lid: '3320', building: 'Daniels Building',                         label: 'Eberhard Zeidler Library' },
      { lid: '3335', building: 'Ontario Institute for Studies in Education', label: 'OISE Library' },
      { lid: '3836', building: 'Robarts Library',                          label: 'Map & Data Library' },
      // Added 2026-10-21 once each building was confirmed from a page: the Music
      // Library's address is 80 Queen's Park (Edward Johnson, whose map record also
      // names it); UC Library's is 15 King's College Circle; Pratt is its own building.
      { lid: '3472', building: 'Edward Johnson Building',                  label: 'Music Library' },
      { lid: '3482', building: 'University College',                       label: 'University College Library' },
      { lid: '3484', building: 'E.J. Pratt Library',                       label: 'E.J. Pratt Library' },
      // Robarts (lid 3446) lists its rooms by category, and one category is Robarts
      // Common's, which is its own building on this map with its own (24 h) hours.
      // Asking per category credits each room to the right building. Measured
      // 2026-10-21: Common 32, Robarts 20 + 5 + 2 + 5 individual.
      { lid: '3446', gid: '7314', building: 'Robarts Common',                 label: 'Robarts Common group study rooms' },
      { lid: '3446', gid: '7466', building: 'Robarts Library',                label: 'Robarts group study rooms (stacks)' },
      { lid: '3446', gid: '7474', building: 'Robarts Library',                label: 'Robarts group study rooms (ground floor)' },
      { lid: '3446', gid: '7708', building: 'Robarts Library',                label: 'Robarts group study rooms (3rd floor)' },
      { lid: '3446', gid: '7816', building: 'Robarts Library',                label: 'Robarts individual study rooms' },
      { lid: '3348', building: 'John M. Kelly Library',                    label: 'John M. Kelly Library' },
    ],
  },
};

/** Parse the status summary: [{ name, total, free }] per library. Exported for tests. */
export function parseComputers(html) {
  // Each library reads: | Name | Address | Total: N | Available: M of N |
  const tokens = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, ' ')
    .replace(/<[^>]+>/g, '|').replace(/&amp;/g, '&').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .split('|').map(x => x.replace(/\s+/g, ' ').trim()).filter(Boolean);
  const out = [];
  for (let i = 2; i < tokens.length - 1; i++) {
    const t = tokens[i].match(/^Total:\s*(\d+)$/);
    const a = tokens[i + 1].match(/^Available:\s*(\d+)\s*of\s*(\d+)$/);
    if (t && a) out.push({ name: tokens[i - 2], total: +a[2], free: +a[1] });
  }
  return out;
}

async function fetchComputers(cfg) {
  const res = await fetch(cfg.url, { headers: { 'User-Agent': 'Mozilla/5.0 (campusquiet.com library computers)' } });
  if (!res.ok) throw new Error(`computers ${res.status}`);
  const out = {};
  for (const lib of parseComputers(await res.text())) {
    const building = cfg.buildings[lib.name];
    if (!building) continue;
    const prev = out[building] ?? { free: 0, total: 0, sources: [] };
    out[building] = { free: prev.free + lib.free, total: prev.total + lib.total, sources: [...prev.sources, lib.name] };
  }
  return out;
}

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
  // A taken slot is NOT in `bookings` -- that array comes back empty on every
  // campus (checked 2026-10-21: UMD, OSU, UIUC and U of T, all 0). LibCal marks a
  // booked slot inside `slots` with className "s-lc-eq-checkout" instead; a free
  // one has no className. Reading only `bookings` counted every booked room as free.
  const takenSlot = s => !!s.className && /checkout|unavail|booked/i.test(s.className);
  const booked = new Set([
    ...(grid?.bookings ?? [])
      .filter(b => b.start <= nowIso && nowIso < b.end)
      .map(b => String(b.itemId)),
    ...slots
      .filter(s => s.start <= nowIso && nowIso < s.end && takenSlot(s))
      .map(s => String(s.itemId)),
  ]);
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

/**
 * Per-room state at `nowIso`, from the same grid: for each room that has slots today,
 *   free  -- a slot covers now and nobody has taken it
 *   until -- when a free room stops being free (end of the unbroken run of untaken slots)
 *   next  -- when a room that is booked right now next becomes free
 *   opens -- when a room the library is not yet taking bookings for becomes bookable
 * Times are the campus's local "YYYY-MM-DD HH:MM:SS" strings, returned as "HH:MM". Rooms
 * the library is not taking bookings for right now are omitted (no slot covers now and
 * none later today), so the list never claims a room we know nothing about.
 */
export function roomStates(grid, nowIso) {
  const takenSlot = s => !!s.className && /checkout|unavail|booked/i.test(s.className);
  const byRoom = new Map();
  for (const s of grid?.slots ?? []) {
    const id = String(s.itemId);
    if (!byRoom.has(id)) byRoom.set(id, []);
    byRoom.get(id).push(s);
  }
  const hm = t => t.slice(11, 16);
  const out = {};
  for (const [id, slots] of byRoom) {
    slots.sort((a, b) => (a.start < b.start ? -1 : 1));
    const nowSlot = slots.find(s => s.start <= nowIso && nowIso < s.end);
    if (nowSlot && !takenSlot(nowSlot)) {
      let end = nowSlot.end;
      for (const s of slots) {
        if (s.start === end && !takenSlot(s)) end = s.end; else if (s.start >= end) break;
      }
      out[id] = { free: true, until: hm(end) };
    } else {
      const later = slots.find(s => s.start >= nowIso && !takenSlot(s));
      if (nowSlot) out[id] = { free: false, next: later ? hm(later.start) : null };   // booked now
      else if (later) out[id] = { free: false, opens: hm(later.start) };              // not taking bookings yet
    }
  }
  return out;
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
      const prev = buildings[loc.building] ?? { free: 0, total: 0, bookable: 0, sources: [], rooms: {} };
      buildings[loc.building] = {
        free: prev.free + free,
        total: prev.total + total,
        bookable: prev.bookable + bookable,
        sources: [...prev.sources, loc.label],
        rooms: { ...prev.rooms, ...roomStates(grid, now) },
      };
    } catch (err) {
      // One library being unreachable must not blank the others.
      failed.push(loc.label);
    }
  }));

  let computers = null;
  if (campus.computers) {
    try { computers = await fetchComputers(campus.computers); }
    catch (err) { failed.push('library computers'); }
  }

  const body = { campus: campusId, asOf: now, buildings, failed, ...(computers ? { computers } : {}) };
  cache.set(campusId, { at: Date.now(), body });
  // Let Vercel's edge hold it too, so a traffic spike doesn't become a spike
  // of requests at the library's booking system.
  res.setHeader('Cache-Control', 'public, s-maxage=300, stale-while-revalidate=600');
  res.status(200).json(body);
}
