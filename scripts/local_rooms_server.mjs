// Local stand-in for Vercel's /api/rooms, for the demo only: python's http.server
// cannot run api/rooms.mjs. Serves the SAME handler on :9099 with CORS.
import http from 'node:http';
import handler from '../api/rooms.mjs';
http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  const out = { status(c) { res.statusCode = c; return this; }, setHeader(k, v) { res.setHeader(k, v); },
    json(b) { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(b)); } };
  res.setHeader('Access-Control-Allow-Origin', '*');
  await handler({ query: Object.fromEntries(u.searchParams) }, out);
}).listen(9099, '127.0.0.1', () => console.log('rooms on :9099'));
