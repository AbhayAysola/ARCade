#!/usr/bin/env python3

import json
import os
import re
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ----------------------------- settings -----------------------------------
PIS = ["arcade1"]   # hostnames or IPs ("host:port" also works)
PI_PORT = 8080          # port of the RetroPie-Parental website on each Pi
PORT = 5000             # port this leaderboard is served on
POLL_SECONDS = 10       # how often the Pis are asked for fresh numbers
TOP_N = 15              # rows shown
TITLE = "MOST PLAYED"
SUBTITLE = "ARCADE MACHINE"
TICKER = ""
# ---------------------------------------------------------------------------

DEMO = "--demo" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEMS = {
    "pico8": "PICO-8", "psx": "PlayStation", "n64": "Nintendo 64", "atari2600": "Atari 2600",
    "nes": "NES", "snes": "SNES", "gb": "Game Boy", "gbc": "Game Boy Color", "gba": "GBA",
    "megadrive": "Mega Drive", "genesis": "Genesis", "mastersystem": "Master System",
    "arcade": "Arcade", "mame-libretro": "Arcade", "fba": "Arcade", "neogeo": "Neo Geo",
    "pcengine": "PC Engine", "c64": "Commodore 64", "zxspectrum": "ZX Spectrum",
    "amiga": "Amiga", "dreamcast": "Dreamcast", "psp": "PSP", "nds": "Nintendo DS",
} # Properly display console after the game name (Purely for aesthetics)

state = {}              
lock = threading.Lock()


# ------------------------------ data --------------------------------------
def demo_totals(i):
    base = {
        "doom (psx)": (5400, 7), "Diddy Kong Racing (n64)": (4700, 9),
        "birds_with_guns (pico8)": (3100, 6), "celeste_classic (pico8)": (2500, 8),
        "Donkey Kong (atari2600)": (1800, 5), "celeste (pico8)": (1500, 4),
        "Super Mario Kart (snes)": (4100, 8), "Sonic the Hedgehog (megadrive)": (2200, 6),
        "pac-man (arcade)": (900, 3), "tetris (gb)": (700, 3), "Mortal Kombat (arcade)": (1200, 4),
    }
    out = {}
    for k, (s, p) in base.items():
        f = (hash((k, i)) % 70 + 30) / 100.0       # a different mix on every "Pi"
        out[k] = {"seconds": int(s * f / 3), "plays": max(1, int(p * f / 2))}
    return out


def fetch_pi(host):
    if ":" not in host:
        host = "%s:%d" % (host, PI_PORT)
    with urllib.request.urlopen("http://%s/top" % host, timeout=3) as r:
        return json.load(r)


def poll_once():
    def work(i, host):
        try:
            totals = demo_totals(i) if DEMO else fetch_pi(host)
            with lock:
                state[host] = {"ok": True, "totals": totals, "seen": time.time()}
        except Exception:
            with lock:                       # keep the last numbers, just flag it offline
                old = state.get(host, {"totals": {}, "seen": 0})
                state[host] = {"ok": False, "totals": old["totals"], "seen": old["seen"]}

    threads = [threading.Thread(target=work, args=(i, h), daemon=True) for i, h in enumerate(PIS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)


def poll_loop():
    while True:
        poll_once()
        time.sleep(POLL_SECONDS)


def pretty(name):
    m = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", name)
    game, system = (m.group(1), m.group(2)) if m else (name, "")
    game = game.replace("_", " ").strip()
    if game == game.lower():                              # rom file names are often all lower case
        game = " ".join(w.capitalize() for w in game.split())
    return game, SYSTEMS.get(system, system.upper())


def build():
    with lock:
        snap = {h: dict(v) for h, v in state.items()}
    merged, pis = {}, []
    for host in PIS:
        s = snap.get(host, {"ok": False, "totals": {}})
        pis.append({"host": host, "ok": s["ok"]})
        for name, t in s["totals"].items():
            m = merged.setdefault(name, {"seconds": 0, "plays": 0})
            m["seconds"] += int(t.get("seconds", 0))
            m["plays"] += int(t.get("plays", 0))
    rows = []
    for name, t in merged.items():
        game, system = pretty(name)
        rows.append({"game": game, "system": system, "seconds": t["seconds"], "plays": t["plays"]})
    rows.sort(key=lambda r: (-r["seconds"], -r["plays"], r["game"]))
    return {
        "title": TITLE, "subtitle": SUBTITLE, "ticker": TICKER,
        "rows": rows[:TOP_N], "pis": pis,
        "total_seconds": sum(r["seconds"] for r in rows),
        "total_plays": sum(r["plays"] for r in rows),
        "updated": time.strftime("%H:%M:%S"),
    }


# ------------------------------ page --------------------------------------
PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Most Played</title>
<style>
@font-face { font-family: 'upheaval-tt-brk'; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body { background: #0b0620; color: #fff; overflow: hidden; text-align: center;
       font-family: 'upheaval-tt-brk', 'Courier New', monospace; font-weight: bold; font-size: 1rem; }
#bg { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: -3;
      background: linear-gradient(#0b0620 0%, #1b0a45 60%, #2f0f66 100%); }
#grid { position: fixed; left: -20%; right: -20%; bottom: 0; height: 32%; z-index: -2; opacity: .5;
        background-image: linear-gradient(rgba(190,80,255,.6) 2px, transparent 2px),
                          linear-gradient(90deg, rgba(190,80,255,.6) 2px, transparent 2px);
        background-size: 70px 44px;
        -webkit-transform: perspective(320px) rotateX(58deg); transform: perspective(320px) rotateX(58deg);
        -webkit-transform-origin: bottom; transform-origin: bottom; }
#scan { position: fixed; top: 0; left: 0; right: 0; bottom: 0; z-index: 9; pointer-events: none;
        background: repeating-linear-gradient(rgba(0,0,0,.24) 0, rgba(0,0,0,.24) 1px, transparent 1px, transparent 4px); }
#leds { position: absolute; top: 1rem; right: 1.6rem; font-size: .8rem; color: #9aa; }
.led { display: inline-block; width: .9rem; height: .9rem; margin: 0 .3rem 0 1rem; border-radius: 50%;
       vertical-align: middle; }
.led.on  { background: #3cff7a; box-shadow: 0 0 .7rem #3cff7a; }
.led.off { background: #ff3b3b; box-shadow: 0 0 .7rem #ff3b3b; }
h1 {font-family: 'UPHEAVAL TT (BRK)'; margin-top: 1rem; font-size: 3rem; letter-spacing: .1rem; color: #fff078;
     text-shadow: .25rem .25rem 0 #ff2fa8, 0 0 1.6rem #ff3cbe; }
#sub { margin-top: .7rem; font-size: 1.25rem; color: #6af0ff; text-shadow: 0 0 1rem #28c8ff; }
#stats { margin-top: .7rem; font-size: .85rem; color: #c8b8ff; }
table { width: 88%; margin: 1rem auto 0; border-collapse: separate; border-spacing: 0 .3rem; table-layout: fixed; }
td { padding: .35rem .5rem; vertical-align: middle; background: rgba(20,8,60,.78); }
td:first-child { border-radius: .4rem 0 0 .4rem; }
td:last-child  { border-radius: 0 .4rem .4rem 0; }
.rank { width: 9%; font-size: 1.6rem; text-align: center; color: #c8b8ff; }
.name { width: 37%; text-align: left; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; font-size: 1.25rem; }
.sys  { display: block; margin-top: .25rem; font-size: .7rem; color: #6af0ff; }
.barc { width: 28%; }
.bar  { height: 1.1rem; background: rgba(255,255,255,.1); border-radius: .2rem; }
.fill { height: 100%; border-radius: .2rem; background: #ff3cbe; box-shadow: 0 0 .8rem #ff3cbe;
        -webkit-transition: width .8s; transition: width .8s; }
.time  { width: 14%; font-size: 1.15rem; text-align: right; color: #fff078; }
.plays { width: 12%; font-size: .85rem; text-align: right; color: #c8b8ff; }
tr.r1 td { background: rgba(255,60,190,.2); }
tr.r1 .rank { color: #ffd34d; text-shadow: 0 0 1rem #ffd34d; }
tr.r1 .fill { background: #ffd34d; box-shadow: 0 0 .8rem #ffd34d; }
tr.r2 .rank { color: #dfe7f1; }
tr.r2 .fill { background: #cfd8e3; box-shadow: 0 0 .6rem #cfd8e3; }
tr.r3 .rank { color: #e29a5a; }
tr.r3 .fill { background: #d98b4a; box-shadow: 0 0 .6rem #d98b4a; }
#empty { margin-top: 5rem; font-size: 1.4rem; color: #c8b8ff; line-height: 2.4rem; }
#ticker { position: fixed; left: 0; right: 0; bottom: 1.1rem; font-size: 1.05rem; color: #ff3cbe;
          text-shadow: 0 0 1rem #ff3cbe;
          -webkit-animation: blink 1.1s steps(1) infinite; animation: blink 1.1s steps(1) infinite; }
@-webkit-keyframes blink { 50% { opacity: 0; } }
@keyframes blink { 50% { opacity: 0; } }
</style></head>
<body>
<div id="bg"></div><div id="grid"></div>
<div id="leds"></div>
<h1 style="font-size: 4rem"; id="title">&nbsp;</h1>
<div id="sub"></div>
<div id="stats"></div>
<div id="list"></div>
<div id="ticker"></div>
<div id="scan"></div>
<script>
function fit() { document.documentElement.style.fontSize = Math.max(10, window.innerHeight / 54) + 'px'; }
fit(); window.onresize = fit;

function el(tag, cls, text) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
function fmt(s) {
  if (s < 60) return s + ' SEC';
  var h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60);
  if (m === 60) { h += 1; m = 0; }
  if (h === 0) return m + ' MIN';
  return h + 'H ' + (m < 10 ? '0' : '') + m + 'M';
}
function render(d) {
  document.getElementById('title').textContent = d.title;
  document.getElementById('sub').textContent = d.subtitle;
  document.getElementById('ticker').textContent = d.ticker;
  document.getElementById('stats').textContent = d.total_plays
    ? 'TOTAL PLAYTIME ' + fmt(d.total_seconds) + '   *   ' + d.total_plays + ' PLAYS' : '';

  var leds = document.getElementById('leds');
  leds.innerHTML = '';
  for (var i = 0; i < d.pis.length; i++) {
    leds.appendChild(el('span', '', ''));
    leds.lastChild.textContent = 'P' + (i + 1);
    leds.appendChild(el('span', 'led ' + (d.pis[i].ok ? 'on' : 'off')));
  }

  var list = document.getElementById('list');
  list.innerHTML = '';
  if (!d.rows.length) {
    var e = el('div', '', ''); e.id = 'empty';
    e.appendChild(document.createTextNode('NO GAMES PLAYED YET'));
    e.appendChild(document.createElement('br'));
    e.appendChild(document.createTextNode('BE THE FIRST!'));
    list.appendChild(e);
    return;
  }
  var max = d.rows[0].seconds || 1;
  var table = document.createElement('table');
  for (var j = 0; j < d.rows.length; j++) {
    var r = d.rows[j], tr = el('tr', 'r' + (j + 1));
    tr.appendChild(el('td', 'rank', j === 0 ? '1' : String(j + 1)));
    var n = el('td', 'name', r.game);
    if (r.system) n.appendChild(el('span', 'sys', r.system));
    tr.appendChild(n);
    var b = el('td', 'barc'), bar = el('div', 'bar'), fill = el('div', 'fill');
    fill.style.width = Math.max(2, Math.round(100 * r.seconds / max)) + '%';
    bar.appendChild(fill); b.appendChild(bar); tr.appendChild(b);
    tr.appendChild(el('td', 'time', fmt(r.seconds)));
    tr.appendChild(el('td', 'plays', r.plays + (r.plays === 1 ? ' PLAY' : ' PLAYS')));
    table.appendChild(tr);
  }
  list.appendChild(table);
}
function load() {
  var x = new XMLHttpRequest();
  x.open('GET', '/api/top?t=' + new Date().getTime(), true);
  x.onload = function () { try { render(JSON.parse(x.responseText)); } catch (e) {} };
  x.send();
}
load(); setInterval(load, 5000);
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/top":
            self._send(200, json.dumps(build()).encode(), "application/json")
        elif path == "/font.ttf":
            f = os.path.join(HERE, "PressStart2P-Regular.ttf")
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    self._send(200, fh.read(), "font/ttf")
            else:
                self._send(404, b"", "text/plain")
        else:
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    threading.Thread(target=poll_loop, daemon=True).start()
    print("Leaderboard on http://localhost:%d  (%s)" % (PORT, "DEMO data" if DEMO else ", ".join(PIS)))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
