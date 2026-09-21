# -*- coding: utf-8 -*-
"""Tekent de kaarttegels van GAS mee zelf, uit OpenStreetMap-data.

Waarom: de kaart haalde haar tegels live bij tile.openstreetmap.org. Dat mag voor licht
gebruik, maar die servers draaien op giften, en de afspraak is dat er voor publicatie een
eigen tegelbron komt. GAS mee heeft geen server en draait op GitHub Pages, dus tekenen we de
tegels een keer zelf en zetten we ze als gewone afbeeldingen naast de site. Een bezoeker
vraagt daarna niets meer aan een derde partij.

Hoe:
1. Uit de dagelijkse build van de Protomaps-basiskaart (een ODbL-afgeleide van
   OpenStreetMap) leest dit script met range-verzoeken enkel de vectortegels rond Mechelen.
   Protomaps vraagt niet live aan die builds te hangen maar een eigen kopie te nemen: dat
   gebeurt hier, een keer, bij het bouwen. Wat al in de werkmap staat, wordt niet opnieuw
   gevraagd.
2. Een lokale pagina tekent die vectortegels met MapLibre en de Protomaps-stijl in een
   headless Chrome, per blok van hoogstens 14 op 14 tegels plus een rand van een tegel, zodat
   straatnamen aan de naad van twee blokken niet afbreken. Zodra MapLibre helemaal klaar is,
   stuurt de pagina het beeld naar de lokale server; Python wacht daarop in echte tijd.
3. Pillow knipt de blokken in tegels van 256 pixels en schrijft ze naar tegels/z/x/y.png.
   data/tegels.json houdt per zoomniveau bij welke tegels er zijn; de pagina vraagt geen
   tegel buiten die grenzen.

Alles wat van buiten komt (vectortegels, tekenpagina) landt in een werkmap BUITEN de repo.
In de repo komen enkel de getekende tegels en de lijst.

Draaien: python scripts/maak_tegels.py [build]   (enkele minuten; opnieuw doen hoeft zelden)
De bronvermelding op de kaart blijft: Kaartgegevens (c) OpenStreetMap-bijdragers, ODbL.
"""
import base64
import gzip
import http.server
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from datetime import date

from PIL import Image
from pmtiles.reader import Reader

HIER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UIT = os.path.join(HIER, "tegels")
LIJST = os.path.join(HIER, "data", "tegels.json")
WERK = os.path.join(tempfile.gettempdir(), "gasmee-kaartwerk")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
POORT = 8765
AGENT = "GAS mee met Mechelen, eenmalige tegelbouw (gasmee.asgaupaust.be)"

MAPLIBRE = "https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl"
BASEMAPS = "https://cdn.jsdelivr.net/npm/@protomaps/basemaps@5.7.2/dist/basemaps.js"
ASSETS = "https://protomaps.github.io/basemaps-assets"

# Zoomniveaus zoals de kaart ze toont (256 pixels per tegel), en per niveau de rand rond de
# camera's in tegels. Laag inzoomen kost weinig tegels, dus daar mag de rand ruim zijn.
ZOOMS = {11: 5, 12: 5, 13: 5, 14: 5, 15: 5, 16: 4, 17: 3}
BLOK = 14        # tegels per blokzijde, zonder de rand
VECTOR_MAX = 15  # de Protomaps-basiskaart gaat tot niveau 15, daarboven vergroot MapLibre

UITKOMST = {}
KLAAR = threading.Event()


def naar_tegel(lon, lat, z):
    n = 2 ** z
    lat_r = math.radians(lat)
    return ((lon + 180) / 360 * n,
            (1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)


def naar_lonlat(x, y, z):
    n = 2 ** z
    return x / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def camerakader():
    data = json.load(open(os.path.join(HIER, "data", "cameras.json"), encoding="utf-8"))["cameras"]
    punten = [c["positie"] for c in (data.values() if isinstance(data, dict) else data) if c.get("positie")]
    lons, lats = [p[0] for p in punten], [p[1] for p in punten]
    return min(lons), min(lats), max(lons), max(lats)


def bereiken():
    """Per zoomniveau het tegelbereik [x0, x1, y0, y1] rond de camera's."""
    lon0, lat0, lon1, lat1 = camerakader()
    uit = {}
    for z, rand in ZOOMS.items():
        xa, ya = naar_tegel(lon0, lat1, z)   # noordwest
        xb, yb = naar_tegel(lon1, lat0, z)   # zuidoost
        uit[z] = [int(xa) - rand, int(xb) + rand, int(ya) - rand, int(yb) + rand]
    return uit


def blokken(z, bereik):
    x0, x1, y0, y1 = bereik
    for bx in range(x0, x1 + 1, BLOK):
        for by in range(y0, y1 + 1, BLOK):
            yield z, bx, min(bx + BLOK - 1, x1), by, min(by + BLOK - 1, y1)


def nodige_vectortegels(alle_blokken):
    """Welke vectortegels MapLibre nodig heeft om elk blok met zijn rand te tekenen.

    Kaartzoom z (256 px) is MapLibre-zoom z-1 (512 px), dus een vectortegel dekt 2 op 2
    kaarttegels; boven niveau 15 vergroot MapLibre de tegels van niveau 15. Een vectortegel
    extra rondom, voor labels die over een tegelgrens lopen."""
    nodig = set()
    for z, cx0, cx1, cy0, cy1 in alle_blokken:
        v = min(z - 1, VECTOR_MAX)
        schuif = z - v
        for vx in range(((cx0 - 1) >> schuif) - 1, ((cx1 + 1) >> schuif) + 2):
            for vy in range(((cy0 - 1) >> schuif) - 1, ((cy1 + 1) >> schuif) + 2):
                nodig.add((v, vx, vy))
    return nodig


def recentste_build():
    verzoek = urllib.request.Request("https://build-metadata.protomaps.dev/builds.json",
                                     headers={"User-Agent": AGENT})
    builds = json.load(urllib.request.urlopen(verzoek, timeout=30))
    return sorted(b["key"] for b in builds if b.get("key", "").endswith(".pmtiles"))[-1]


def pad_vectortegel(v, x, y):
    return os.path.join(WERK, "vt", str(v), str(x), f"{y}.pbf")


def haal_vectortegels(build, nodig):
    """Leest enkel de nodige tegels die nog niet in de werkmap staan, met range-verzoeken,
    en schrijft ze uitgepakt weg. De mappen van het archief worden bewaard, zodat elke map
    maar een keer over de lijn gaat."""
    ontbreekt = sorted(t for t in nodig if not os.path.exists(pad_vectortegel(*t)))
    if not ontbreekt:
        print(f"   alle {len(nodig)} vectortegels stonden al in de werkmap")
        return
    url = "https://build.protomaps.com/" + build
    bewaard = {}

    def lees(offset, lengte):
        sleutel = (offset, lengte)
        if sleutel not in bewaard:
            verzoek = urllib.request.Request(url, headers={
                "User-Agent": AGENT, "Range": f"bytes={offset}-{offset + lengte - 1}"})
            bewaard[sleutel] = urllib.request.urlopen(verzoek, timeout=60).read()
        return bewaard[sleutel]

    lezer = Reader(lees)
    geschreven = 0
    for v, x, y in ontbreekt:
        ruw = lezer.get(v, x, y)
        if not ruw:
            continue
        if ruw[:2] == b"\x1f\x8b":
            ruw = gzip.decompress(ruw)
        os.makedirs(os.path.dirname(pad_vectortegel(v, x, y)), exist_ok=True)
        with open(pad_vectortegel(v, x, y), "wb") as bestand:
            bestand.write(ruw)
        geschreven += 1
    print(f"   {geschreven} vectortegels gelezen in {len(bewaard)} verzoeken")


TEKENPAGINA = """<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="MAPLIBRE.css">
<style>html,body{margin:0}#k{position:absolute;left:0;top:0}</style>
<div id="k"></div>
<script src="MAPLIBRE.js"></script>
<script src="BASEMAPS"></script>
<script>
const meld = (soort, inhoud) => fetch("/" + soort, {method: "POST", body: inhoud});
const fouten = [];
window.addEventListener("error", e => fouten.push(String(e.message)));
const p = new URLSearchParams(location.hash.slice(1));
const k = document.getElementById("k");
k.style.width = p.get("b") + "px"; k.style.height = p.get("h") + "px";
let kaart = null;
try {
  kaart = new maplibregl.Map({
    container: k, interactive: false, attributionControl: false, fadeDuration: 0,
    pixelRatio: 1, maxCanvasSize: [8192, 8192],
    canvasContextAttributes: {preserveDrawingBuffer: true, antialias: true},
    center: [+p.get("lon"), +p.get("lat")], zoom: +p.get("zoom"),
    style: {
      version: 8,
      glyphs: "ASSETS/fonts/{fontstack}/{range}.pbf",
      sprite: "ASSETS/sprites/v4/light",
      sources: {protomaps: {type: "vector", tiles: [location.origin + "/vt/{z}/{x}/{y}.pbf"], maxzoom: VECTOR_MAX}},
      // Zonder de laag met winkels, cafes en scholen: op een kaart over camera's is dat ruis,
      // en het geeft zaken een vermelding waar niemand om vroeg.
      layers: basemaps.layers("protomaps", basemaps.namedFlavor("light"), {lang: "nl"})
        .filter(laag => !String(laag.id).startsWith("pois"))
    }
  });
  kaart.on("error", e => fouten.push((e.error && e.error.message) || "kaartfout"));
  kaart.once("idle", () => meld("klaar", kaart.getCanvas().toDataURL("image/png")));
} catch (e) {
  fouten.push("opbouw: " + e.message);
  meld("fout", fouten.join(" | "));
}
setTimeout(() => meld("fout", "tijd op; " + fouten.join(" | ") + " | geladen=" + (kaart && kaart.loaded())), 240000);
</script>
"""


class Bediening(http.server.SimpleHTTPRequestHandler):
    """Serveert de werkmap, en ontvangt het beeld of de fout van de tekenpagina."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WERK, **kwargs)

    def log_message(self, *args):
        pass

    def do_POST(self):
        lengte = int(self.headers.get("Content-Length", 0))
        UITKOMST.setdefault(self.path.strip("/"), self.rfile.read(lengte).decode("utf-8", "replace"))
        self.send_response(204)
        self.end_headers()
        KLAAR.set()


def start_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", POORT), Bediening)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def teken_blok(z, cx0, cx1, cy0, cy1):
    """Tekent een blok met een rand van een tegel en geeft het beeld zonder rand terug."""
    b, h = (cx1 - cx0 + 3) * 256, (cy1 - cy0 + 3) * 256
    lon, lat = naar_lonlat((cx0 + cx1 + 1) / 2, (cy0 + cy1 + 1) / 2, z)
    url = f"http://127.0.0.1:{POORT}/teken.html#b={b}&h={h}&lon={lon!r}&lat={lat!r}&zoom={z - 1}"
    UITKOMST.clear()
    KLAAR.clear()
    profiel = tempfile.mkdtemp(prefix="gasmee-chrome-")
    chrome = subprocess.Popen([CHROME, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                               "--no-first-run", "--no-default-browser-check", f"--user-data-dir={profiel}",
                               "--window-size=800,600", url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        gekomen = KLAAR.wait(300)
    finally:
        subprocess.run(["taskkill", "/PID", str(chrome.pid), "/T", "/F"], capture_output=True)
        shutil.rmtree(profiel, ignore_errors=True)
    if not gekomen or "klaar" not in UITKOMST:
        raise SystemExit(f"   STOP: blok z{z} {cx0},{cy0} kwam niet terug. {UITKOMST.get('fout', 'geen antwoord')[:400]}")
    beeld = Image.open(io.BytesIO(base64.b64decode(UITKOMST["klaar"].split(",", 1)[1]))).convert("RGB")
    if beeld.size != (b, h):
        raise SystemExit(f"   STOP: blok z{z} {cx0},{cy0} is {beeld.size}, verwacht {(b, h)}")
    return beeld.crop((256, 256, b - 256, h - 256))


def schrijf_tegels(z, cx0, cy0, beeld):
    geschreven = 0
    for i in range(beeld.width // 256):
        for j in range(beeld.height // 256):
            tegel = beeld.crop((i * 256, j * 256, i * 256 + 256, j * 256 + 256))
            pad = os.path.join(UIT, str(z), str(cx0 + i))
            os.makedirs(pad, exist_ok=True)
            tegel.quantize(colors=128, method=Image.Quantize.MEDIANCUT).save(
                os.path.join(pad, f"{cy0 + j}.png"), optimize=True)
            geschreven += 1
    return geschreven


def main():
    build = sys.argv[1] if len(sys.argv) > 1 else recentste_build()
    per_zoom = bereiken()
    alle_blokken = [blok for z, bereik in per_zoom.items() for blok in blokken(z, bereik)]
    print(f"build {build}, {len(alle_blokken)} blokken, "
          f"{sum((b[1] - b[0] + 1) * (b[3] - b[2] + 1) for b in per_zoom.values())} tegels")

    os.makedirs(WERK, exist_ok=True)
    haal_vectortegels(build, nodige_vectortegels(alle_blokken))
    pagina = (TEKENPAGINA.replace("MAPLIBRE", MAPLIBRE).replace("BASEMAPS", BASEMAPS)
              .replace("ASSETS", ASSETS).replace("VECTOR_MAX", str(VECTOR_MAX)))
    with open(os.path.join(WERK, "teken.html"), "w", encoding="utf-8") as bestand:
        bestand.write(pagina)

    server = start_server()
    shutil.rmtree(UIT, ignore_errors=True)
    totaal = 0
    try:
        for z, cx0, cx1, cy0, cy1 in alle_blokken:
            totaal += schrijf_tegels(z, cx0, cy0, teken_blok(z, cx0, cx1, cy0, cy1))
            print(f"   z{z} blok {cx0},{cy0}: klaar ({totaal} tegels)")
    finally:
        server.shutdown()

    with open(LIJST, "w", encoding="utf-8") as bestand:
        json.dump({
            "_leesmij": "Eigen kaarttegels, getekend door scripts/maak_tegels.py uit de Protomaps-basiskaart "
                        "(een ODbL-afgeleide van OpenStreetMap). Per zoomniveau het bereik [x0, x1, y0, y1].",
            "bron": f"Protomaps-basiskaart, build {build.replace('.pmtiles', '')}, OpenStreetMap-bijdragers (ODbL)",
            "gemaakt": date.today().isoformat(),
            "min": min(ZOOMS), "max": max(ZOOMS),
            "zooms": {str(z): b for z, b in per_zoom.items()},
        }, bestand, ensure_ascii=False, indent=1)
    grootte = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(UIT) for f in fs)
    print(f"{totaal} tegels geschreven naar tegels/ ({grootte / 1e6:.1f} MB), lijst in data/tegels.json")


if __name__ == "__main__":
    main()
