#!/usr/bin/env python3
"""
Write utsg-demo.html (gitignored): utsg.html with a fake clock, for showing the map
at a moment other than now. ?t=2026-10-20T20:30 picks the moment (Toronto time).

The clock RUNS from that moment rather than standing still. A frozen Date.now()
breaks Cesium: its camera inertia decays by elapsed time, so with no time passing a
drag never stops and the view drifts and tilts into the ground on its own.

Usage:  python3 scripts/make_utsg_demo.py   (rerun after build_campus_pages.py)
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INJECT = """<script>/* LOCAL DEMO ONLY: fake clock starting at ?t= (Toronto), running in real time. */
(function(){const q=new URLSearchParams(location.search).get('t')||'2026-10-20T11:00';
const F=new Date(q+(q.length<=16?':00-04:00':'')).getTime(),R=Date,T0=R.now();
const now=()=>F+(R.now()-T0);
window.Date=class extends R{constructor(...a){a.length?super(...a):super(now())}static now(){return now()}};
addEventListener('DOMContentLoaded',()=>{const b=document.createElement('div');
b.textContent='DEMO CLOCK: started at '+new R(F).toLocaleString('en-CA',{timeZone:'America/Toronto',weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' Toronto time. Not live.';
b.style.cssText='position:fixed;left:50%;transform:translateX(-50%);bottom:8px;z-index:99999;background:#c0392b;color:#fff;font:600 12px system-ui;padding:4px 10px;border-radius:6px;pointer-events:none';
document.body.appendChild(b)})})();</script>"""

s = (ROOT / "utsg.html").read_text()
i = s.index("<head>") + len("<head>")
(ROOT / "utsg-demo.html").write_text(s[:i] + INJECT + s[i:])
print("-> utsg-demo.html")
