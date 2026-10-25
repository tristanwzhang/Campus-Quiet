#!/usr/bin/env node
// Build data/<campus>/study_rooms.json: one record per bookable library study room, read from the
// libraries' own booking pages (<libcal host>/space/<id>): name, floor, seats,
// features. Availability is NOT here -- that is live, from /api/rooms. Re-run once a term, or
// when the Libraries add rooms.
//
//   node scripts/build_study_rooms.mjs umd|osu
import fs from 'node:fs';
import { CAMPUSES } from '../api/rooms.mjs';

const campusId = process.argv[2] ?? 'utsg';
const campus = CAMPUSES[campusId];
const outDir = `data/${campusId}`;
const day = n => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const decode = s => s.replace(/&amp;/g, '&').replace(/&#0?39;|&apos;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim();
const strip = h => decode(h.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<[^>]+>/g, ' '));

async function grid(loc, start) {
  const body = new URLSearchParams({ lid: loc.lid, gid: loc.gid ?? '0', eid: '-1', seat: '0', seatId: '0',
    zone: '0', start, end: new Date(Date.parse(start) + 86400000).toISOString().slice(0, 10), pageIndex: '0', pageSize: '100' });
  const r = await fetch(`${campus.host}/spaces/availability/grid`, { method: 'POST', body, headers: {
    'Content-Type': 'application/x-www-form-urlencoded', 'X-Requested-With': 'XMLHttpRequest',
    Referer: `${campus.host}/spaces`, 'User-Agent': 'Mozilla/5.0 (campusquiet.com)' } });
  return r.json();
}

// The booking page for a location lists each room as a JS record carrying LibCal's own
// feature tags (filterIds -> "Power Available", "Monitor Available", ...) and a photo.
// These are the libraries' structured tags, not words fished out of a description.
async function tagsFor(loc) {
  const url = `${campus.host}/spaces?lid=${loc.lid}${loc.gid ? `&gid=${loc.gid}` : ''}`;
  const html = await (await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' } })).text();
  const names = {};
  const sf = html.match(/searchFilters:\s*(\{.*?\}\}),/);
  if (sf) for (const f of Object.values(JSON.parse(sf[1]))) names[f.id] = f.name;
  const out = {};
  for (const m of html.matchAll(/resources\.push\(\{([\s\S]*?)\}\);/g)) {
    const b = m[1];
    const eid = (b.match(/eid:\s*(\d+)/) ?? [])[1];
    if (!eid) continue;
    const ids = ((b.match(/filterIds:\s*\[([^\]]*)\]/) ?? [])[1] ?? '').split(',').map(x => x.trim()).filter(Boolean);
    out[eid] = {
      tags: ids.map(i => names[i]).filter(Boolean),
      photo: (b.match(/thumbnail:\s*"([^"]+)"/) ?? [])[1] ?? null,
      // "Room 2100A (Capacity 8)": the fallback when a room's own page has no info box.
      title: JSON.parse(`"${(b.match(/title:\s*"((?:[^"\\]|\\.)*)"/) ?? [, ''])[1]}"`).replace(/\s*\(Capacity \d+\)\s*$/, ''),
      capacity: +((b.match(/capacity:\s*(\d+)/) ?? [])[1] ?? 0) || null,
    };
  }
  return out;
}

const rooms = {};
for (const loc of campus.locations) {
  const tags = await tagsFor(loc);
  const ids = new Set();
  // A room with no slots on one day (closed that day) shows up on another.
  for (const n of [2, 3, 4, 5]) for (const s of (await grid(loc, day(n))).slots ?? []) ids.add(String(s.itemId));
  console.log(`${loc.label}: ${ids.size} rooms`);
  for (const id of ids) {
    if (rooms[id]) continue;
    const html = await (await fetch(`${campus.host}/space/${id}`, { headers: { 'User-Agent': 'Mozilla/5.0' } })).text();
    const info = html.match(/s-lc-spaces-setup-info[^>]*>([\s\S]*?)<\/div>/);
    const text = info ? strip(info[1]) : '';
    // "2241 Group Study Room 2A (Robarts Library and Robarts Common: 02nd Floor - Robarts Common) Capacity: 5 Description ..."
    const m = text.match(/^(.*?)\s*\((.*?)\)\s*Capacity:\s*(\d+)\s*(.*)$/);
    if (!m) {
      // Some rooms have no info box; the location page's own record still names them.
      const page = decode((html.match(/<title>([\s\S]*?)<\/title>/) ?? [, ''])[1]).split(' - ')[0];
      const t = tags[id] ?? (page ? { title: page, capacity: null, tags: [], photo: null } : null);
      if (!t?.title) { console.log(`  !! ${id}: could not read "${text.slice(0, 80)}"`); continue; }
      rooms[id] = { building: loc.building, where: loc.label, name: t.title, floor: null, capacity: t.capacity,
        features: null, tags: t.tags, photo: t.photo };
      continue;
    }
    const floor = (m[2].match(/(\d+\w*\s+Floor|Ground Floor|Basement|Lower Level)/i) ?? [])[0] ?? null;
    const feat = (m[4].match(/Features:\s*(.*)$/) ?? [, ''])[1];
    rooms[id] = {
      building: loc.building, where: loc.label, name: m[1], floor, capacity: +m[3],
      // Features run together ("TV Screen Dimmable Lighting Close to elevator ..."); keep the text.
      features: feat || null,
      tags: tags[id]?.tags ?? [],
      photo: tags[id]?.photo ?? null,
    };
    await new Promise(r => setTimeout(r, 120));
  }
}
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(`${outDir}/study_rooms.json`, JSON.stringify({
  built_at: new Date().toISOString(), source: `${campus.host}/space/<id> (the libraries' own booking pages)`,
  note: 'Static details only. Whether a room is free is live, from /api/rooms.', rooms }, null, 1) + '\n');
console.log(`${Object.keys(rooms).length} rooms -> ${outDir}/study_rooms.json`);
