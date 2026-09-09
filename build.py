"""Giet de data in template.html en schrijft dist/index.html.

Eén bestand dat je kunt dubbelklikken: de cijfers zitten erin, niet ernaast. Zo
werkt het dashboard ook zonder webserver, want een browser mag een lokaal
json-bestand niet zomaar inlezen.

De omschrijvingen van de feitcodes staan alleen in de recentste jaarverslagen.
Die verzamelt dit script eenmalig, zodat een feitcode ook in de oudere jaren een
naam krijgt in plaats van enkel een nummer.

Draaien:  python build.py
Uit:      dist/index.html (plus de lettertypes ernaast)
"""

import json
import os
import re
import shutil
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HIER, "dist")
CUSTOM_DOMAIN = "gasmee.asgaupaust.be"
BESTANDEN = {
    "gasam": os.path.join(HIER, "data", "gasam_mechelen.json"),
    "budget": os.path.join(HIER, "data", "budget_mechelen.json"),
    "cameras": os.path.join(HIER, "cameras.json"),
}
# de gazet-voorpagina: artikels uit het Lees mee-dossier, opgehaald door
# haal_leesmee.py; ontbreekt het bestand, dan bouwt de rest gewoon door
LEESMEE = os.path.join(HIER, "data", "leesmee_dossier.json")


def feitcodes(gasam):
    """Feitcode -> omschrijving, uit de jaren die de omschrijving wél voluit geven."""
    uit = {}
    for blok in gasam["jaren"].values():
        for rij in (blok.get("parkeren") or {}).get("top_inbreuken", []):
            if rij.get("omschrijving"):
                uit.setdefault(rij["feitcode"], rij["omschrijving"])
    return uit


def controleer(gasam, cameras):
    """Kleine poort: wat scheef staat willen we zien vóór het in beeld komt."""
    problemen = []
    for jaar, blok in gasam["jaren"].items():
        for soort in ("autoluw", "parkeren"):
            onderdeel = blok.get(soort)
            if not onderdeel:
                continue
            maanden = onderdeel.get("per_maand")
            totaal = onderdeel.get("totaal")
            if maanden and totaal and sum(maanden) != totaal:
                problemen.append(f"{jaar} {soort}: maanden tellen {sum(maanden)}, totaal is {totaal}")
    zonder = [naam for naam, rij in cameras["cameras"].items() if not rij.get("positie")]
    if zonder:
        print("   camera's zonder positie op de kaart: " + ", ".join(zonder))
    return problemen


def mug_data_uri():
    """De mug ingebakken als data-URI, verkleind naar 128 px (hij toont op 34 px).

    Zo blijft dist/index.html één zelfstandig bestand dat met een dubbelklik
    werkt, zonder map beelden ernaast. Zonder Pillow gaat het volle bestand erin.
    """
    import base64
    import io
    pad = os.path.join(HIER, "beelden", "mug.png")
    ruw = open(pad, "rb").read()
    try:
        from PIL import Image
        beeld = Image.open(io.BytesIO(ruw)).resize((128, 128), Image.LANCZOS)
        buffer = io.BytesIO()
        beeld.save(buffer, "PNG", optimize=True)
        ruw = buffer.getvalue()
    except Exception as fout:
        print(f"   mug niet verkleind ({fout}); het volle bestand gaat erin")
    return "data:image/png;base64," + base64.b64encode(ruw).decode()


def bouw_techniek(sjabloon):
    """Giet template-techniek.html (een fragment: eigen <style> plus <main>) in de huid van
    de GAS-pagina en schrijft dist/techniek.html.

    De huid is letterlijk die van template.html: dezelfde head (met eigen titel en
    beschrijving), de appbalk met het merkwoord, het hamburgermenu, het colofon en de
    onderbalk. Alleen wijzen de knoppen hier naar index.html#onderdeel, want het
    dashboard leest de hash bij het laden en opent dat onderdeel. Zo is de techniekpagina
    een echte zus van de andere techniekpagina's in de familie, zonder dat de tekst van
    de schrijver iets van de opmaak hoeft te weten."""
    pad = os.path.join(HIER, "template-techniek.html")
    if not os.path.exists(pad):
        print("       (geen template-techniek.html: techniekpagina overgeslagen)")
        return
    fragment = open(pad, encoding="utf-8").read()
    kop = sjabloon[:sjabloon.index("</head>")]
    kop = re.sub(r"<title>.*?</title>", "<title>Technische pagina &middot; GAS mee met Mechelen</title>", kop, count=1, flags=re.S)
    uitleg = ("Hoe GAS mee met Mechelen de cijfers uit de jaarverslagen haalt, de camera&#39;s op de kaart zet "
              "en zichzelf controleert.")
    kop = re.sub(r'(<meta name="description" content=")[^"]*(")', r"\g<1>" + uitleg + r"\g<2>", kop, count=1)
    kop = re.sub(r'(<meta property="og:title" content=")[^"]*(")', r"\g<1>Technische pagina: GAS mee met Mechelen\g<2>", kop, count=1)
    kop = re.sub(r'(<meta property="og:description" content=")[^"]*(")', r"\g<1>" + uitleg + r"\g<2>", kop, count=1)
    appbalk = sjabloon[sjabloon.index('<div class="appbalk"'):sjabloon.index('<div class="menuvlak"')]
    menuvlak = sjabloon[sjabloon.index('<div class="menuvlak"'):sjabloon.index('<div class="wrap">')]
    menuvlak = re.sub(r'href="#(\w+)" onclick="event\.preventDefault\(\);toonView\(\'\w+\'\)"', r'href="index.html#\1"', menuvlak)
    menuvlak = menuvlak.replace('href="#verantwoording" onclick="naarVerantwoording(event)"', 'href="index.html#verantwoording"')
    colofon = sjabloon[sjabloon.index('<footer class="colofon">'):sjabloon.index("</footer>") + len("</footer>")]
    colofon = colofon.replace('href="#camera" aria-label="GAS mee met Mechelen, naar het begin" onclick="event.preventDefault();toonView(\'camera\')"',
                              'href="index.html" aria-label="GAS mee met Mechelen, naar het begin"')
    onderbalk = sjabloon[sjabloon.index('<nav class="onderbalk"'):sjabloon.index("</nav>", sjabloon.index('<nav class="onderbalk"')) + len("</nav>")]
    onderbalk = re.sub(r'<button role="tab" data-view="(\w+)" aria-selected="\w+">', r'<a href="index.html#\1">', onderbalk).replace("</button>", "</a>")
    # Op de techniekpagina zijn dit geen tabbladen maar links naar het dashboard.
    # Een tablist waarvan elke tab naar een andere pagina springt, klopt niet voor
    # een schermlezer, dus de rollen gaan eruit.
    onderbalk = onderbalk.replace('<nav class="onderbalk" role="tablist" aria-label="Onderdelen">',
                                  '<nav class="onderbalk" aria-label="Onderdelen">')
    script = """<button class="terug" id="terug" title="Terug naar boven" aria-label="Terug naar boven">&uarr;</button>
<script>
function menu(open) {
  const vlak = document.getElementById("menuvlak"), knop = document.getElementById("menuknop");
  if (!vlak || !knop) return;
  const nu = open === undefined ? vlak.hidden : open;
  vlak.hidden = !nu;
  knop.setAttribute("aria-expanded", String(nu));
  document.body.classList.toggle("menu-open", nu);
}
document.addEventListener("keydown", e => { if (e.key === "Escape") menu(false); });
(function () {
  const terug = document.getElementById("terug");
  if (!terug) return;
  const toon = () => terug.classList.toggle("zichtbaar", window.scrollY > 600);
  window.addEventListener("scroll", toon, {passive: true}); toon();
  terug.addEventListener("click", () => window.scrollTo({top: 0, behavior: "smooth"}));
})();
</script>
"""
    pagina = (kop + "</head>\n<body class=\"techniek\">\n" + appbalk + menuvlak + fragment + "\n" + colofon + "\n\n"
              + onderbalk + "\n" + script + "</body>\n</html>\n")
    pagina = pagina.replace("beelden/mug.png", mug_data_uri())
    doel = os.path.join(DIST, "techniek.html")
    with open(doel, "w", encoding="utf-8") as bestand:
        bestand.write(pagina)
    print(f"       techniekpagina gebouwd: dist/techniek.html ({len(pagina) // 1000} kB)")


def main():
    gegevens = {}
    for sleutel, pad in BESTANDEN.items():
        if not os.path.exists(pad):
            sys.exit(f"ontbreekt: {pad}\nDraai eerst parse_gasam.py, parse_budget.py en geocode_cameras.py.")
        gegevens[sleutel] = json.load(open(pad, encoding="utf-8"))

    problemen = controleer(gegevens["gasam"], gegevens["cameras"])
    for regel in problemen:
        print("   ! " + regel)

    gegevens["feitcodes"] = feitcodes(gegevens["gasam"])
    gegevens["leesmee"] = json.load(open(LEESMEE, encoding="utf-8")) if os.path.exists(LEESMEE) else None
    if not gegevens["leesmee"]:
        print("   let op: geen data/leesmee_dossier.json; de gazet blijft leeg (draai haal_leesmee.py)")

    sjabloon = open(os.path.join(HIER, "template.html"), encoding="utf-8").read()
    blok = "const D = " + json.dumps(gegevens, ensure_ascii=False, separators=(",", ":")) + ";"
    pagina = sjabloon.replace("/* DATA_HIER */", blok)
    pagina = pagina.replace("beelden/mug.png", mug_data_uri())

    os.makedirs(os.path.join(DIST, "fonts"), exist_ok=True)
    for naam in os.listdir(os.path.join(HIER, "fonts")):
        if naam.endswith(".woff2") or naam.endswith(".txt"):
            shutil.copy(os.path.join(HIER, "fonts", naam), os.path.join(DIST, "fonts", naam))

    # CNAME voor het eigen subdomein op GitHub Pages. Door dit bij elke build mee te
    # schrijven, kan een volgende publicatie het domein niet per ongeluk laten vallen:
    # de Actions-publicatie vervangt de hele map. Eenmalig ingesteld in Settings -> Pages,
    # met een DNS-record naar onderconstructie.github.io.
    with open(os.path.join(DIST, "CNAME"), "w", encoding="utf-8") as bestand:
        bestand.write(CUSTOM_DOMAIN + "\n")

    doel = os.path.join(DIST, "index.html")
    with open(doel, "w", encoding="utf-8") as bestand:
        bestand.write(pagina)
    bouw_techniek(sjabloon)
    print(f"{doel} geschreven ({len(pagina) // 1024} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
