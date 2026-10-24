#!/usr/bin/env node
// Build data/utsg/study_rooms.json: one record per bookable U of T study room, read from the
// libraries' own booking pages (libcal.library.utoronto.ca/space/<id>): name, floor, seats,
// features. Availability is NOT here -- that is live, from /api/rooms. Re-run once a term, or
// when the Libraries add rooms.
//
//   node scripts/build_utsg_study_rooms.mjs
import fs from 'node:fs';
import { CAMPUSES } from '../api/rooms.mjs';

const campus = CAMPUSES.utsg;
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

const rooms = {};
for (const loc of campus.locations) {
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
    if (!m) { console.log(`  !! ${id}: could not read "${text.slice(0, 80)}"`); continue; }
    const floor = (m[2].match(/(\d+\w*\s+Floor|Ground Floor|Basement|Lower Level)/i) ?? [])[0] ?? null;
    const feat = (m[4].match(/Features:\s*(.*)$/) ?? [, ''])[1];
    rooms[id] = {
      building: loc.building, where: loc.label, name: m[1], floor, capacity: +m[3],
      // Features run together ("TV Screen Dimmable Lighting Close to elevator ..."); keep the text.
      features: feat || null,
    };
    await new Promise(r => setTimeout(r, 120));
  }
}
fs.mkdirSync('data/utsg', { recursive: true });
fs.writeFileSync('data/utsg/study_rooms.json', JSON.stringify({
  built_at: new Date().toISOString(), source: `${campus.host}/space/<id> (the libraries' own booking pages)`,
  note: 'Static details only. Whether a room is free is live, from /api/rooms.', rooms }, null, 1) + '\n');
console.log(`${Object.keys(rooms).length} rooms -> data/utsg/study_rooms.json`);
