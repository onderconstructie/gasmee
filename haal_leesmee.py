"""Haalt de artikels van het dossier "GAS & de autoluwe zone" op bij Lees mee.

Lees mee (leesmee.asgaupaust.be) is een zelfstandige pagina die haar hele archief
als één gegevensblok in zich draagt (LEESMEE_DATA). Dit script haalt die pagina
op, knipt het blok eruit, en bewaart van het dossier gas-autoluw alleen wat de
gazet-voorpagina nodig heeft: titel, datum, samenvatting, leestijd, beeld en de
link naar het artikel. De artikelteksten zelf blijven waar ze horen, op Lees mee.

De uitkomst gaat in data/leesmee_dossier.json met de ophaaldatum erbij; build.py
giet ze mee in het dashboard. Geen verbinding of geen dossier: dan blijft het
oude bestand staan en meldt het script dat, zodat een kapotte run nooit een
werkende gazet leegmaakt.

Draaien:  python haal_leesmee.py
Uit:      data/leesmee_dossier.json
"""

import datetime
import json
import os
import sys
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
UIT = os.path.join(HIER, "data", "leesmee_dossier.json")
BRON = "https://leesmee.asgaupaust.be/"
DOSSIER = "gas-autoluw"
MERK = "LEESMEE_DATA = "


def haal_pagina():
    verzoek = urllib.request.Request(BRON, headers={"User-Agent": "GAS-mee-met-Mechelen-proef/0.1 (familie As Gau Paust)"})
    with urllib.request.urlopen(verzoek, timeout=60) as antwoord:
        return antwoord.read().decode("utf-8")


def knip_datablok(pagina):
    """Het gegevensblok begint na 'LEESMEE_DATA = ' en is één JSON-object.

    We lezen het met een accoladeteller in plaats van een regex: het blok bevat
    artikel-html met alle mogelijke tekens erin.
    """
    start = pagina.index(MERK) + len(MERK)
    diepte = 0
    in_tekst = False
    ontsnapt = False
    for i in range(start, len(pagina)):
        teken = pagina[i]
        if in_tekst:
            if ontsnapt:
                ontsnapt = False
            elif teken == "\\":
                ontsnapt = True
            elif teken == '"':
                in_tekst = False
            continue
        if teken == '"':
            in_tekst = True
        elif teken == "{":
            diepte += 1
        elif teken == "}":
            diepte -= 1
            if diepte == 0:
                return json.loads(pagina[start : i + 1])
    raise ValueError("gegevensblok niet afgesloten")


def main():
    try:
        pagina = haal_pagina()
        data = knip_datablok(pagina)
    except Exception as fout:
        print(f"Lees mee niet bereikbaar of onleesbaar ({fout}); het bestaande bestand blijft staan.")
        return 0 if os.path.exists(UIT) else 1

    dossier = next((d for d in data.get("dossiers", []) if d.get("slug") == DOSSIER), None)
    if not dossier:
        print(f"dossier {DOSSIER} niet gevonden; het bestaande bestand blijft staan.")
        return 0 if os.path.exists(UIT) else 1

    ids = set(dossier.get("post_ids", []))
    artikels = []
    for post in data.get("posts", []):
        if post.get("id") not in ids:
            continue
        artikels.append({
            "titel": post.get("titel"),
            "datum": post.get("datum"),
            "datum_disp": post.get("datum_disp"),
            "excerpt": post.get("excerpt", "").strip(),
            "leestijd": post.get("leestijd"),
            "beeld": (BRON + post["beeld"]) if post.get("beeld") else None,
            "url": BRON + "#/artikel/" + post.get("slug", ""),
        })
    artikels.sort(key=lambda a: a.get("datum") or "", reverse=True)

    uit = {
        "opgehaald": datetime.date.today().isoformat(),
        "bron": BRON + "#/dossier/" + DOSSIER,
        "dossier": {
            "naam": dossier.get("naam"),
            "omschrijving": dossier.get("omschrijving"),
            "jaar_van": dossier.get("jaar_van"),
            "jaar_tot": dossier.get("jaar_tot"),
        },
        "artikels": artikels,
    }
    os.makedirs(os.path.dirname(UIT), exist_ok=True)
    with open(UIT, "w", encoding="utf-8") as bestand:
        json.dump(uit, bestand, ensure_ascii=False, indent=1)
    print(f"{UIT} geschreven: {len(artikels)} artikels uit het dossier \"{dossier.get('naam')}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
