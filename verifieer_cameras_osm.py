"""Zoekt de exacte ANPR-cameraposities op in OpenStreetMap.

De jaarverslagen noemen alleen de straat; het adressenregister geeft daarvan
het midden. OpenStreetMap bevat in Mechelen echter tientallen bewakings-
camera's als losse punten, door mappers ter plaatse ingetekend en onder
dezelfde ODbL-licentie als onze kaart. Dit script koppelt die punten aan onze
camera's, en zet de stip op het punt als de koppeling eenduidig is.

Werkwijze (herzien 27/08/2026):
  1. Kandidaten zijn camerapunten met de markering ALPR/ANPR, of camera's in
     de verkeerszone (surveillance:zone=traffic): de stad tekent haar nieuwe
     ANPR-camera's soms zo in, zonder ALPR-tag.
  2. Een punt hoort bij een camera als het binnen AFSTAND_STRAAT meter van de
     straat zelf ligt (de weggeometrie met die naam), niet van het straatmidden.
     Zo doen lange straten mee, en telt een camera op de hoek voor beide straten.
  3. Elk punt gaat naar hoogstens een camera. Bij twijfel wint de camera wiens
     eigen referentiepunt (huisnummer of straatmidden) het dichtst bij ligt; de
     paren worden op die afstand oplopend toegewezen.
  4. Wat overblijft zonder eenduidig punt houdt zijn straatmidden.

De uitkomst komt in cameras.json:
  positie                wat het dashboard toont: handmatig > osm > straatmidden
  osm_positie            het gekoppelde punt, met node-id, tags en afstanden
  positie_straatmidden   het straatmidden, als vergelijk en terugvaloptie

Google Maps of Street View gebruiken we hier bewust niet: coordinaten daaruit
overnemen verbiedt hun licentie.

Draaien:  python verifieer_cameras_osm.py
Uit:      cameras.json (bijgewerkt)
"""

import json
import math
import os
import re
import sys
import urllib.parse
import urllib.request

HIER = os.path.dirname(os.path.abspath(__file__))
CAMERAS = os.path.join(HIER, "cameras.json")
AFSTAND_STRAAT = 30        # meter: tot hier ligt een punt "in" de straat
AFSTAND_REFERENTIE = 400   # meter: verder dan dit van het eigen referentiepunt telt niet mee
BBOX = "(50.99,4.43,51.07,4.53)"
OVERPASS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
# de naam in het jaarverslag tegenover de straatnaam in OpenStreetMap
STRAATNAAM = {"Hoogstraat/Milsenstraat": "Hoogstraat"}
USER_AGENT = "GAS-mee-met-Mechelen-proef/0.1 (familie As Gau Paust)"


def overpass(vraag):
    for adres in OVERPASS:
        try:
            data = urllib.parse.urlencode({"data": vraag}).encode()
            verzoek = urllib.request.Request(adres, data=data, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(verzoek, timeout=150) as antwoord:
                return json.loads(antwoord.read())["elements"]
        except Exception as fout:
            print(f"   {adres.split('/')[2]}: {fout}")
    return None


def straatnaam(cameranaam):
    zonder_nummer = re.sub(r"\s+\d+$", "", cameranaam)
    return STRAATNAAM.get(zonder_nummer, zonder_nummer)


def is_kandidaat(node):
    tags = node.get("tags", {})
    soorten = (tags.get("surveillance:type", "") + " " + tags.get("camera:type", "")).lower()
    return "alpr" in soorten or "anpr" in soorten or tags.get("surveillance:zone") == "traffic"


def meter(a, b):
    """Afstand in meter tussen (lon, lat)-paren, vlakke benadering; ruim genoeg hier."""
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110540
    return math.hypot(dx, dy)


def afstand_tot_segment(p, a, b):
    schaal = 111320 * math.cos(math.radians(a[1]))
    bx, by = (b[0] - a[0]) * schaal, (b[1] - a[1]) * 110540
    px, py = (p[0] - a[0]) * schaal, (p[1] - a[1]) * 110540
    lengte2 = bx * bx + by * by
    t = 0 if lengte2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / lengte2))
    return math.hypot(px - t * bx, py - t * by)


def afstand_tot_straat(punt, naam, wegen):
    beste = float("inf")
    for weg in wegen.get(naam, []):
        for a, b in zip(weg, weg[1:]):
            beste = min(beste, afstand_tot_segment(punt, a, b))
    return beste


def main():
    cams = json.load(open(CAMERAS, encoding="utf-8"))
    for rij in cams["cameras"].values():
        rij["positie_straatmidden"] = rij.get("positie_straatmidden") or rij.get("positie")

    namen = sorted({straatnaam(n) for n in cams["cameras"]})
    regex = "^(" + "|".join(re.escape(n) for n in namen) + ")$"
    print("OpenStreetMap bevragen: camerapunten en de straten zelf ...")
    nodes = overpass('[out:json][timeout:120];node["man_made"="surveillance"]' + BBOX + ";out body;")
    wegen_ruw = overpass('[out:json][timeout:120];way["highway"]["name"~"' + regex + '"]' + BBOX + ";out geom;")
    if nodes is None or wegen_ruw is None:
        print("Overpass niet bereikbaar; cameras.json blijft ongemoeid.")
        return 1
    punten = [n for n in nodes if is_kandidaat(n)]
    wegen = {}
    for weg in wegen_ruw:
        geom = [(p["lon"], p["lat"]) for p in weg.get("geometry", [])]
        wegen.setdefault(weg["tags"].get("name"), []).append(geom)
    print(f"{len(punten)} kandidaat-camerapunten, {len(wegen_ruw)} straatsegmenten voor {len(namen)} straten")

    # alle paren (camera, punt) waarbij het punt in de straat van de camera ligt;
    # gesorteerd op de afstand tot het eigen referentiepunt, dan gretig uniek
    paren = []
    for naam, rij in cams["cameras"].items():
        if rij.get("handmatig"):
            continue
        referentie = rij.get("positie_straatmidden")
        for punt in punten:
            xy = (punt["lon"], punt["lat"])
            in_straat = afstand_tot_straat(xy, straatnaam(naam), wegen)
            if in_straat > AFSTAND_STRAAT:
                continue
            tot_ref = meter(referentie, xy) if referentie else 0
            if referentie and tot_ref > AFSTAND_REFERENTIE:
                continue
            paren.append((tot_ref, in_straat, naam, punt))
    paren.sort(key=lambda p: (p[0], p[1]))
    toegewezen, gebruikte_punten = {}, set()
    for tot_ref, in_straat, naam, punt in paren:
        if naam in toegewezen or punt["id"] in gebruikte_punten:
            continue
        toegewezen[naam] = (punt, tot_ref, in_straat)
        gebruikte_punten.add(punt["id"])

    gekoppeld = 0
    for naam, rij in cams["cameras"].items():
        basis = rij.get("positie_straatmidden")
        if rij.get("handmatig"):
            rij["positie"] = rij["handmatig"]
            rij["positie_bron"] = rij.get("handmatig_bron") or "handmatig ingevuld"
            continue
        if naam in toegewezen:
            punt, tot_ref, in_straat = toegewezen[naam]
            tags = punt.get("tags", {})
            rij["osm_positie"] = {
                "punt": [round(punt["lon"], 6), round(punt["lat"], 6)],
                "node": punt["id"],
                "soort": tags.get("surveillance:type"),
                "zone": tags.get("surveillance:zone"),
                "beheerder": tags.get("operator"),
                "afstand_tot_straat_m": round(in_straat),
                "afstand_tot_referentie_m": round(tot_ref),
            }
            alpr = "alpr" in (tags.get("surveillance:type", "") + tags.get("camera:type", "")).lower()
            if not alpr and rij.get("reglement_positie"):
                # een ongetagde verkeerscamera wint niet van de officiele omschrijving
                # van de stad (plaats_verkeersstops.py); het OSM-punt blijft wel bewaard
                rij["positie"] = rij["reglement_positie"]["punt"]
                rij["positie_bron"] = rij["reglement_positie"].get("label") or "verkeersstop volgens het autoluwreglement van de stad, gezet op de kruising of doorgang uit OpenStreetMap"
            else:
                rij["positie"] = rij["osm_positie"]["punt"]
                rij["positie_bron"] = ("ANPR-camerapunt uit OpenStreetMap (ODbL)" if alpr
                                       else "verkeerscamera uit OpenStreetMap (ODbL), daar niet als ANPR gemarkeerd")
            gekoppeld += 1
            beheerder = (", " + tags["operator"]) if tags.get("operator") else ""
            print(f"   {naam}: OSM-punt {punt['id']} ({tags.get('surveillance:type')}{beheerder}), "
                  f"{round(in_straat)} m van de straat, {round(tot_ref)} m van het referentiepunt")
        elif rij.get("reglement_positie"):
            # plaats_verkeersstops.py zette deze camera op de kruising of doorgang
            # die het autoluwreglement beschrijft; dat gaat voor het straatmidden
            rij.pop("osm_positie", None)
            rij["positie"] = rij["reglement_positie"]["punt"]
            rij["positie_bron"] = rij["reglement_positie"].get("label") or "verkeersstop volgens het autoluwreglement van de stad, gezet op de kruising of doorgang uit OpenStreetMap"
        elif basis:
            rij.pop("osm_positie", None)
            rij["positie"] = basis
            rij["positie_bron"] = "midden van de straat (Vlaams Adressenregister)"
        else:
            rij.pop("osm_positie", None)
            rij.pop("positie", None)
            rij["positie_bron"] = "geen positie"
            print(f"   {naam}: geen positie (niet in het adressenregister, geen OSM-punt)")

    cams["_leesmij"] = (
        "Posities: handmatig > camerapunt uit OpenStreetMap (ODbL, verifieer_cameras_osm.py: punt in "
        "de straat zelf, uniek toegewezen) > straatmidden uit het Vlaams Adressenregister "
        "(geocode_cameras.py). Vul 'handmatig' met [lengtegraad, breedtegraad] om een camera vast te "
        "zetten; de scripts blijven daar af. Google Maps is geen bron: hun licentie verbiedt "
        "coordinaten overnemen."
    )
    with open(CAMERAS, "w", encoding="utf-8") as bestand:
        json.dump(cams, bestand, ensure_ascii=False, indent=1)
    print(f"cameras.json bijgewerkt: {gekoppeld} van de {len(cams['cameras'])} camera's op een OSM-punt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
