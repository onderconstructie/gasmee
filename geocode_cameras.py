"""Zet de ANPR-camera's uit de jaarverslagen op de kaart, bij benadering.

De GASAM-jaarverslagen noemen enkel de straat waar een camera hangt, nooit een
exacte plaats. Dit script zoekt per straat de adressen op in het Vlaams
Adressenregister, rekent hun Lambert 72-coördinaten om naar WGS84 en neemt het
midden van de straat. Dat is dus een straatpositie, geen camerapositie: het punt
staat ergens in de straat, niet noodzakelijk aan de paal.

Twee camera's dragen een huisnummer in hun naam ("Steenweg 20", "Steenweg 44").
Die worden op dat adres zelf gezet, wat een stuk preciezer is dan het
straatmidden.

Zelf een positie verbeteren doe je in cameras.json: zet de gevonden lengte- en
breedtegraad in het veld "handmatig" en het script laat dat punt met rust.

    "Zoutwerf": {"handmatig": [4.4784, 51.0271], "opmerking": "paal aan nr. 12"}

Draaien:  python geocode_cameras.py           (alleen wat nog geen positie heeft)
          python geocode_cameras.py --alles   (alles opnieuw ophalen)
Uit:      cameras.json
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
DENKMEE = os.path.join(os.path.dirname(HIER), "DenkMeeMetMechelen")
CAMERAS = os.path.join(HIER, "cameras.json")
GASAM = os.path.join(HIER, "data", "gasam_mechelen.json")

API = "https://api.basisregisters.vlaanderen.be/v2"
USER_AGENT = "GASAM-proef/0.1 (burgerexperiment; contact via asgaupaust.be)"
PAUZE = 0.6

# De naam in het jaarverslag is niet altijd de naam in het adressenregister.
STRAATNAAM = {
    "Onze-Lieve-Vrouwestraat": "Onze-Lieve-Vrouwestraat",
    "Steenweg 20": ("Steenweg", "20"),
    "Steenweg 44": ("Steenweg", "44"),
    "Van Benedenlaan 1": ("Van Benedenlaan", "1"),
    "Van Benedenlaan 47": ("Van Benedenlaan", "47"),
    # de camera staat op de hoek; het register kent alleen losse straten
    "Hoogstraat/Milsenstraat": "Hoogstraat",
}

sys.path.insert(0, DENKMEE)
from straten_mechelen import lambert72_to_wgs84  # noqa: E402  (pad eerst zetten)

_GML = re.compile(r"<gml:pos>([\d.]+)\s+([\d.]+)</gml:pos>")


def haal(url, pogingen=5):
    """GET met geduld: het adressenregister knijpt af met een 429 als je doorholt."""
    verzoek = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    for poging in range(pogingen):
        try:
            with urllib.request.urlopen(verzoek, timeout=30) as antwoord:
                return json.loads(antwoord.read())
        except urllib.error.HTTPError as fout:
            if fout.code != 429 or poging == pogingen - 1:
                raise
            time.sleep(2.0 * (poging + 1))
        except (urllib.error.URLError, TimeoutError):
            if poging == pogingen - 1:
                raise
            time.sleep(1.5 * (poging + 1))
    return {}


def punt_van_adres(objectid):
    gegevens = haal(f"{API}/adressen/{objectid}")
    positie = gegevens.get("adresPositie", {}).get("point", {})
    if "coordinates" in positie:
        x, y = positie["coordinates"][:2]
        return lambert72_to_wgs84(float(x), float(y))
    ruw = json.dumps(gegevens)
    treffer = _GML.search(ruw)
    if treffer:
        return lambert72_to_wgs84(float(treffer.group(1)), float(treffer.group(2)))
    return None


def adressen(straat, huisnummer=None, maximum=5):
    """Objectid's van adressen in een Mechelse straat."""
    vraag = {"gemeentenaam": "Mechelen", "straatnaam": straat, "limit": str(maximum)}
    if huisnummer:
        vraag["huisnummer"] = huisnummer
    url = f"{API}/adressen?" + urllib.parse.urlencode(vraag)
    return [rij["identificator"]["objectId"] for rij in haal(url).get("adressen", [])]


def middenpunt(punten):
    """Het midden van een straat: het gemiddelde van de gevonden adressen."""
    lengte = sum(p[0] for p in punten) / len(punten)
    breedte = sum(p[1] for p in punten) / len(punten)
    return round(lengte, 6), round(breedte, 6)


def cameranamen():
    """Alle camera's die ooit in een jaarverslag opdoken, met hun laatste jaar."""
    gegevens = json.load(open(GASAM, encoding="utf-8"))
    namen = {}
    for jaar, blok in gegevens["jaren"].items():
        for naam in (blok.get("autoluw", {}).get("per_camera") or {}):
            if naam == "onbekend":
                continue
            namen.setdefault(naam, []).append(int(jaar))
    return {naam: sorted(jaren) for naam, jaren in sorted(namen.items())}


def main():
    alles = "--alles" in sys.argv
    bestaand = {}
    if os.path.exists(CAMERAS):
        bestaand = json.load(open(CAMERAS, encoding="utf-8"))

    uit = {
        "_leesmij": (
            "Posities zijn straatmiddens uit het Vlaams Adressenregister, dus bij "
            "benadering. Vul het veld 'handmatig' met [lengtegraad, breedtegraad] "
            "om een camera exact te plaatsen; geocode_cameras.py laat die dan met rust."
        ),
        "cameras": {},
    }

    for naam, jaren in cameranamen().items():
        oud = bestaand.get("cameras", {}).get(naam, {})
        rij = {"jaren": jaren}
        rij.update({sleutel: oud[sleutel] for sleutel in ("handmatig", "handmatig_bron", "opmerking", "reglement_positie") if sleutel in oud})

        if rij.get("handmatig"):
            rij["positie"] = rij["handmatig"]
            rij["positie_bron"] = rij.get("handmatig_bron") or "handmatig ingevuld"
            uit["cameras"][naam] = rij
            print(f"   {naam}: handmatige positie behouden")
            continue

        if not alles and oud.get("positie"):
            # dit script beheert het STRAATMIDDEN; een eerder gevonden OSM-punt
            # (verifieer_cameras_osm.py) mag hier nooit als straatmidden gaan
            # doorleven, anders meet de volgende verificatie circulair 0 meter
            midden = oud.get("positie_straatmidden") or oud["positie"]
            rij["positie"] = midden
            rij["positie_straatmidden"] = midden
            rij["positie_bron"] = "midden van de straat (Vlaams Adressenregister)"
            uit["cameras"][naam] = rij
            continue

        opzoeking = STRAATNAAM.get(naam, naam)
        straat, huisnummer = opzoeking if isinstance(opzoeking, tuple) else (opzoeking, None)
        try:
            gevonden = adressen(straat, huisnummer)
            time.sleep(PAUZE)
            punten = []
            for objectid in gevonden:
                punt = punt_van_adres(objectid)
                time.sleep(PAUZE)
                if punt:
                    punten.append(punt)
        except Exception as fout:  # netwerk of onbekende straat: laat het gat staan
            punten = []
            print(f"   {naam}: opzoeking mislukt ({fout})")

        if punten:
            rij["positie"] = middenpunt(punten)
            rij["positie_bron"] = (
                f"adres {straat} {huisnummer} (Vlaams Adressenregister)"
                if huisnummer
                else f"midden van {straat}, {len(punten)} adressen (Vlaams Adressenregister)"
            )
            print(f"   {naam}: {rij['positie']}  ({len(punten)} adressen)")
        else:
            rij["positie"] = None
            rij["positie_bron"] = "niet gevonden in het adressenregister"
            print(f"   {naam}: GEEN positie")
        uit["cameras"][naam] = rij

    with open(CAMERAS, "w", encoding="utf-8") as bestand:
        json.dump(uit, bestand, ensure_ascii=False, indent=1)
    zonder = [n for n, r in uit["cameras"].items() if not r.get("positie")]
    print(f"\n{CAMERAS} geschreven: {len(uit['cameras'])} camera's, {len(zonder)} zonder positie")
    if zonder:
        print("   zonder positie: " + ", ".join(zonder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
