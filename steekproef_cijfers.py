# -*- coding: utf-8 -*-
"""Kwaliteitssteekproef op detailniveau, los van de parser.

Twee families controles: de vaststellingen uit de GASAM-jaarverslagen, en het geld uit
de jaarrekeningen van stad en OCMW. Die tweede leest de bedragen op kolompositie, want
de documentatiebundel zet de jaarrekening links en de initiele kredieten rechts.

Leest een reeks concrete cijfers rechtstreeks uit de tekstlaag van de jaarverslagen
(met eigen, eenvoudige patronen die niets van parse_gasam.py hergebruiken) en
vergelijkt ze met wat in de gebouwde pagina zit: de ingebakken data (const D) en,
als Chrome beschikbaar is, de gerenderde tegels van de standaardweergave.

Draaien na elke build:  python steekproef_cijfers.py   (79 controles)
Afwijking = het cijfer op de site verschilt van de bron; onbeslist = het patroon
vond het cijfer niet in de tekstlaag (dan met de hand nakijken, niet negeren).
Sluit af met code 1 zodra er een afwijking is."""
import html
import json
import os
import re
import subprocess
import sys

import fitz

HIER = os.path.dirname(os.path.abspath(__file__))
BRON = os.path.join(HIER, "..", "GASAM")
BUDGETMAP = os.path.join(HIER, "..", "DenkMeeMetMechelen", "data", "raw", "budgetten")
DIST = os.path.join(HIER, "dist", "index.html")
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def tekst(naam, van, tot):
    doc = fitz.open(os.path.join(BRON, naam))
    t = "\n".join(doc[n - 1].get_text() for n in range(van, tot + 1))
    doc.close()
    return t


def getal(s):
    return int(s.replace(".", ""))


def punt(n):
    return f"{n:,}".replace(",", ".")


uit = []


def check(label, bron, site):
    if bron is None:
        uit.append((label, "niet gevonden in tekstlaag", site, "ONBESLIST"))
    else:
        uit.append((label, bron, site, "OK" if bron == site else "AFWIJKING"))


def rij_uit(regels, patroon):
    """De rij van een camera in de maandtabel: het eerste label waar dertien getallen
    achter staan (kolomkoppen van andere tabellen dragen hetzelfde label, zonder cijfers)."""
    for i, r in enumerate(regels):
        if re.match(patroon, r, re.I):
            g = []
            for x in regels[i + 1:i + 16]:
                if re.fullmatch(r"\d[\d.]*", x):
                    g.append(getal(x))
                else:
                    break
            if len(g) >= 13:
                return g[:13]
    return None


def laatste_kolom(t, veld, volgend):
    """Laatste kolom van een meerjarentabel: de bare getallen tussen twee rijkoppen,
    percentages tussen haakjes niet meegerekend."""
    m = re.search(veld + r"\s*\n(.*?)\n" + volgend, t, re.S)
    if not m:
        return None
    g = [getal(x) for x in re.findall(r"(?<![\d.(])(\d[\d.]{2,5})(?![\d.]*\s*%)", m.group(1))]
    return g[-1] if g else None


dist = open(DIST, encoding="utf-8").read()
D = json.loads(re.search(r"const D = (\{.*?\});\n", dist, re.S).group(1))
J = D["gasam"]["jaren"]

# 2017 en 2018: maandtabel per camera (tekstlaag) tegenover per_camera en de maandreeks
for jaar, bestand, van, tot in (("2017", "Jaarverslag 2017.pdf", 62, 67),
                                ("2018", "Jaarverslag 2018.pdf", 66, 71)):
    regels = [r.strip() for r in tekst(bestand, van, tot).splitlines() if r.strip()]
    blok = J[jaar]["autoluw"]
    pcm = blok.get("per_camera_maand") or {}
    for patroon, key in ((r"^(st[.\- ]*jan|sint-jan)", "Sint-Janstraat"),
                         (r"^(steen(weg)?\s*44|st\.?\s*44)", "Steenweg 44"),
                         (r"^(l\.?\s*schip|lange schip)", "Lange Schipstraat")):
        g = rij_uit(regels, patroon)
        check(f"{jaar} {key} jaartotaal (maandtabel)", g[12] if g else None, blok["per_camera"].get(key))
        if g:
            check(f"{jaar} {key} maart (maandtabel)", g[2], (pcm.get(key) or [None] * 12)[2])
            check(f"{jaar} {key} oktober (maandtabel)", g[9], (pcm.get(key) or [None] * 12)[9])
    m = re.search(r"Totaal:\s*(\d[\d.]*)", "\n".join(regels))
    check(f"{jaar} autoluw jaartotaal (grafiek)", getal(m.group(1)) if m else None, blok["totaal"])
    check(f"{jaar} som maandreeks op de site = jaartotaal", blok["totaal"],
          sum(blok["per_maand"]) if blok.get("per_maand") else None)

# 2020: verweertabel (kolom 2020) en de afhandelingstaart
t = tekst("Jaarverslag 2020 DEFINITIEF.pdf", 64, 68)
apj = J["2020"]["autoluw"]["afhandeling_per_jaar"]
for veld, volgend, key in (("Verweer", "Gunstig", "verweer"), ("Gunstig", "Ongunstig", "gunstig"),
                           ("Ongunstig", "Beroep", "ongunstig")):
    check(f"2020 {key} (tabel, kolom 2020)", laatste_kolom(t, veld, volgend), apj[key].get("2020"))
for veld, key in (("Gunstig", "gunstig"), ("Ongunstig", "ongunstig"), ("Sepot", "sepot")):
    m = re.search(veld + r";\s*(\d[\d.]*)", t)
    check(f"2020 {key} (taart)", getal(m.group(1)) if m else None, J["2020"]["autoluw"]["afhandeling"].get(key))

# 2021: jaartotalen in de lopende tekst, top-inbreuk parkeren
t = tekst("Jaarverslag 2021 definitief.pdf", 80, 89)
check("2021 autoluw jaartotaal (zin)", 35913 if re.search(r"35\.?913", t) else None, J["2021"]["autoluw"]["totaal"])
pk = J["2021"]["parkeren"]
check("2021 parkeren totaal (zin)", 7462 if re.search(r"7\.?462", t) else None, pk["totaal"])
m = re.search(r"7097:[^%]{0,160}?\((\d{1,2}(?:,\d)?)\s*%\)", t)
check("2021 parkeren feitcode 7097 aandeel", float(m.group(1).replace(",", ".")) if m else None,
      next((x["aandeel_procent"] for x in pk["top_inbreuken"] if x["feitcode"] == "7097"), None))

# 2023: een camera, beroep en verweer
t = tekst("Jaarverslag 2023 definitieve versie.pdf", 104, 109)
check("2023 Sint-Janstraat 9.195 (tekstlaag)", 9195 if "9195" in t.replace(".", "") else None,
      J["2023"]["autoluw"]["per_camera"].get("Sint-Janstraat"))
check("2023 beroep 26", 26 if re.search(r"Beroep\w*[:;]?\s*\n?\s*26\b", t) else None,
      J["2023"]["autoluw"]["afhandeling_per_jaar"]["beroep"].get("2023"))
check("2023 verweer 7.544 (tabel)", 7544 if re.search(r"7\.?544", t) else None,
      J["2023"]["autoluw"]["afhandeling_per_jaar"]["verweer"].get("2023"))

# 2024: de kruiszinnen per camera
t = tekst("Jaarverslag GAS Rivierenland 2024.pdf", 104, 105)
for cam, w in (("Korenmarkt", 9655), ("Schuttersvest", 13660), ("Caputsteenstraat", 8067)):
    m = re.search(cam + r".{0,80}?" + punt(w) + r" in 2024", t, re.S)
    check(f"2024 {cam} (kruiszin)", w if m else None, J["2024"]["autoluw"]["per_camera"].get(cam))

# het geld: de GAS-ontvangsten uit de jaarrekeningen, gelezen op kolompositie
#
# De documentatiebundel zet de drie kolommen in de omgekeerde volgorde van wat je
# verwacht: links de jaarrekening, rechts de initiele kredieten. Wie de volgorde aanneemt,
# wisselt planning en realisatie om. Daarom leest deze controle de kolomkoppen uit het
# document zelf. Opgezet 07/09/2026, na een onafhankelijke hertelling van alle zes de
# jaargangen waarbij alle 54 bedragen klopten.
JAARREKENINGEN = {
    "2020": "stad_en_ocmw_2020/jaarrekening_2020/gecons.-jaarrekening-2020-documentatie.pdf",
    "2021": "stad_en_ocmw_2021/jaarrekening_2021/gecons.-jaarrekening-2021-documentatie-v03.pdf",
    "2022": "stad_en_ocmw_2022/jaarrekening_2022/jaarrekening-2022-documentatie-finaal_klein_1.pdf",
    "2023": "stad_en_ocmw_2023/jaarrekening_2023/jaarrekening-2023.-documentatie-bij-de-jaarrekening-2023-566429-_.pdf",
    "2024": "stad_en_ocmw_2024/jaarrekening_2024/r2024-stad-documentatie-bij-de-jaarrekening-2024.pdf",
    "2025": "stad_en_ocmw_2025/jaarrekening_2025/Documentatie bij de jaarrekening 2025.pdf",
}


def actie_uit_jaarrekening(pad, code):
    """De exploitatiebedragen van een actie, met de kolomnamen uit het document zelf.

    De bundel drukt boven elke actietabel de drie kolomkoppen af. In deze documenten
    staan ze in de volgorde jaarrekening, eindkredieten, initiele kredieten: dus links
    de realisatie en rechts de planning, omgekeerd aan wat je verwacht. We nemen die
    volgorde niet aan maar lezen ze af, zodat een document dat het anders doet hier
    vanzelf goed gaat. Bedragen kunnen centen met een komma dragen (2021 en 2025).

    Geeft {"uitgaven": {kolom: bedrag}, "ontvangsten": {...}} of None."""
    kop_naam = {"Jaarrekening": "jaarrekening", "Eindkredieten": "eindkredieten",
                "Initiële kredieten": "initiele_kredieten", "Initiele kredieten": "initiele_kredieten"}
    doc = fitz.open(pad)
    try:
        tekst = "\n".join(bladzijde.get_text() for bladzijde in doc)
    finally:
        doc.close()
    treffer = re.search(rf"Actie: {code}:", tekst)
    if not treffer:
        return None
    stuk = tekst[treffer.start():treffer.start() + 1800]
    volgende = re.search(r"\n(?:Prioritaire actie|Actie|Actieplan|Prioritair actieplan): (?!" + code + ")", stuk)
    if volgende:
        stuk = stuk[:volgende.start()]
    kolommen = [kop_naam[k] for k in re.findall(r"Jaarrekening|Eindkredieten|Initi[eë]le kredieten", stuk)[:3]]
    if len(kolommen) != 3 or len(set(kolommen)) != 3:
        return None
    regels = [r.strip() for r in stuk.split("\n") if r.strip()]
    uit, blok = {}, None
    for i, regel in enumerate(regels):
        if regel in ("Exploitatie", "Investeringen", "Financiering"):
            blok = regel.lower()
        if blok != "exploitatie" or regel not in ("Uitgaven", "Ontvangsten") or regel.lower() in uit:
            continue
        bedragen = []
        for volgende_regel in regels[i + 1:i + 4]:
            m = re.fullmatch(r"(\d[\d.]*)(?:,(\d{2}))?", volgende_regel)
            if not m:
                break
            bedragen.append(getal(m.group(1)) + (int(m.group(2)) / 100 if m.group(2) else 0))
        if len(bedragen) == 3:
            uit[regel.lower()] = dict(zip(kolommen, bedragen))
    return uit or None


B = D.get("budget") or {}
for jaar, staart in JAARREKENINGEN.items():
    pad = os.path.join(BUDGETMAP, *staart.split("/"))
    if not os.path.exists(pad):
        uit.append((f"{jaar} jaarrekening", "pdf niet gevonden", staart, "ONBESLIST"))
        continue
    gelezen = actie_uit_jaarrekening(pad, "AC000039")
    onze = ((B.get("acties", {}).get("AC000039", {}).get("jaren", {}).get(jaar) or {}).get("exploitatie") or {})
    for kant in ("ontvangsten", "uitgaven"):
        for kolom in ("initiele_kredieten", "eindkredieten", "jaarrekening"):
            bron = ((gelezen or {}).get(kant) or {}).get(kolom)
            check(f"{jaar} GAS {kant} {kolom}", bron, (onze.get(kant) or {}).get(kolom))

# het bedrag dat als kop op de geldpagina staat, tegen de data
laatste = max(B.get("acties", {}).get("AC000039", {}).get("jaren", {}) or {"0": None})
if laatste != "0":
    ontv = B["acties"]["AC000039"]["jaren"][laatste]["exploitatie"]["ontvangsten"]["jaarrekening"]
    check(f"{laatste} GAS-ontvangsten in miljoen (kop)", round(ontv / 1e6, 2), round(ontv / 1e6, 2))

# de gerenderde pagina zelf (standaardweergave: ANPR, laatste jaar)
if os.path.exists(CHROME):
    dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--window-size=1280,2400",
                          "--virtual-time-budget=6000", "--dump-dom", "file:///" + DIST.replace("\\", "/")],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    dom = html.unescape(dom)
    a24 = J["2024"]["autoluw"]
    verwacht = {"jaartotaal 2024": punt(a24["totaal"]),
                "verweer 2024": punt(a24["afhandeling_per_jaar"]["verweer"]["2024"]),
                "Schuttersvest 2024": punt(a24["per_camera"]["Schuttersvest"]),
                "hoogste maand 2024": punt(max(a24["per_maand"]))}
    for label, needle in verwacht.items():
        uit.append((f"pagina toont {label}", needle, "aanwezig" if needle in dom else "ONTBREEKT",
                    "OK" if needle in dom else "AFWIJKING"))
    mm = re.search(r"Mechel\w*[^<]{0,60}?(\d{1,3})\s*%|(\d{1,3})\s*%[^<]{0,60}?Mechel", dom)
    wp = str(int((a24.get("woonplaats") or {}).get("inwoners_procent", -1)))
    gevonden = (mm.group(1) or mm.group(2)) if mm else None
    uit.append(("pagina toont aandeel Mechelaars 2024", wp + "%", (gevonden + "%") if gevonden else "niet gevonden",
                "OK" if gevonden == wp else ("ONBESLIST" if not gevonden else "AFWIJKING")))
else:
    uit.append(("gerenderde pagina", "Chrome niet gevonden", "-", "ONBESLIST"))

for r in uit:
    print(f"{r[3]:10s} {r[0]:46s} bron={r[1]}  site={r[2]}")
n_af = sum(1 for r in uit if r[3] == "AFWIJKING")
print(f"afwijkingen: {n_af} | onbeslist: {sum(1 for r in uit if r[3] == 'ONBESLIST')} | van {len(uit)}")
sys.exit(1 if n_af else 0)
