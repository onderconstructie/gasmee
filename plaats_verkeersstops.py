"""Zet camera's op de plek die het autoluwreglement van de stad beschrijft.

De jaarverslagen noemen alleen een straat, en OpenStreetMap kent de nieuwste
camera's op de vesten en in de wijk Caputsteen-Nekkerspoel nog niet. Maar het
reglement "Autoluwe binnenstad en verkeersstops" van de stad Mechelen
beschrijft elke verkeersstop tot op de kruising of de doorgang: "Van
Benedenlaan ter hoogte van de Groenstraat", "Kleine Nieuwedijkstraat ter
hoogte van de spoorweg", "Frans Halsvest tussen de Jan Bolstraat en de
Populierendreef". Dit script vertaalt die officiele omschrijvingen naar een punt
op de straatgeometrie van OpenStreetMap (ODbL):

  kruising      het punt waar twee straten elkaar raken
  spoorkruising het punt waar de straat de spoorlijn kruist
  tussen        het midden van het stuk straat tussen twee zijstraten
  huisnummer    het adrespunt uit het Vlaams Adressenregister (via geocode)
  nabij         een aantal meter voorbij een kruising, in een windrichting
  uiteinde      het einde van de straat dat het dichtst bij een benoemde plek ligt
                (een woonzorgcentrum, een school), voor een doorsteek zonder naam

Een recept mag een eigen "bron" en "label" dragen. Zo staat een camera die het
reglement enkel in een stratenlijst met huisnummers noemt ("Wollemarkt (nrs
2-10)") op dat adrespunt, en de knip van 2019 op de Kruisbaan op de plek die de
regionale pers beschreef; de site zegt dan precies welke bron dat is.

Les van 04/09/2026: bij "tussen" het midden op de DICHTSTBIJZIJNDE weg van de
straat projecteren, nooit op de langste. Een straat bestaat in OpenStreetMap
vaak uit meerdere stukken, en op de langste projecteren zette Van Benedenlaan 1
133 m naast de Brusselpoort en Ivo Cornelisstraat 292 m naast het afgesloten
stuk. Een onafhankelijke controle (reglementen, de officiele knipkaart van de
stad, het antwoord van het college op een schriftelijke vraag over de boetes per
camera, pers, OSM) bracht dat aan het licht.

Elke uitkomst komt in cameras.json onder "reglement_positie", met het
letterlijke citaat uit het reglement en de rekenwijze, en telt mee in de
volgorde handmatig > OSM-camerapunt > reglement > straatmidden. Alleen
omschrijvingen die eenduidig op een punt uitkomen staan in RECEPTEN; wat vaag
is (een zone-ingang zonder plaatsaanduiding) blijft op het straatmidden.

Bron: Reglement autoluwe binnenstad en verkeersstops, stad Mechelen (2025-04
en 2026-08), www.mechelen.be. Google Maps is bewust geen bron.

Draaien:  python plaats_verkeersstops.py   (na verifieer_cameras_osm.py)
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
BBOX = "(50.99,4.43,51.07,4.53)"
OVERPASS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
USER_AGENT = "GAS-mee-met-Mechelen-proef/0.1 (familie As Gau Paust)"
BRON = "Reglement autoluwe binnenstad en verkeersstops, stad Mechelen (2026)"
LABEL = "verkeersstop volgens het autoluwreglement van de stad, gezet op de kruising of doorgang uit OpenStreetMap"

# Per camera: hoe het reglement de stop beschrijft, en hoe we dat op de kaart
# zetten. Het citaat is letterlijk; de straatnamen zijn die van OpenStreetMap.
RECEPTEN = {
    "Ivo Cornelisstraat": {
        "citaat": "Ivo Cornelisstraat: tussen de Abeelstraat en Kardinaal Cardynstraat",
        "type": "tussen", "straat": "Ivo Cornelisstraat", "van": "Abeelstraat", "tot": "Kardinaal Cardynstraat"},
    "Mechelsbroekstraat": {
        "citaat": "Verkeersstop die de straat onderbreekt tussen de sporthal en nr 21",
        "type": "huisnummer", "straat": "Mechelsbroekstraat", "nummer": "21"},
    "Van Benedenlaan 47": {
        "citaat": "Verkeersstop langs de binnenkant van de vesten, die de doorgang onderbreekt op de Van Benedenlaan ter hoogte van de Groenstraat",
        "type": "kruising", "straat": "Van Benedenlaan", "met": "Groenstraat"},
    "Van Benedenlaan 1": {
        "citaat": "Brusselpoort / Van Benedenlaan 1: verkeersstop langs de binnenkant van de vesten, die de doorgang onderbreekt tussen de Hoogstraat en Koningin Astridlaan",
        "type": "tussen", "straat": "Van Benedenlaan", "van": "Hoogstraat", "tot": "Koningin Astridlaan"},
    "Koningin Astridlaan": {
        "citaat": "Verkeersstop langs de binnenkant van de vesten, die de doorgang onderbreekt van Koningin Astridlaan naar het kruispunt met de Adegemstraat/Battelsesteenweg",
        "type": "nabij", "straat": "Koningin Astridlaan", "kruising": "Adegemstraat", "meter": 40},
    "Olivetenvest": {
        "citaat": "Olivetenvest: binnenkant van de vesten ten noorden van het kruispunt (met de Adegemstraat/Battelsesteenweg)",
        "type": "nabij", "straat": "Olivetenvest", "kruising": "Battelsesteenweg", "meter": 40, "richting": "noord"},
    "Zwartzustersvest": {
        "citaat": "Verkeersstop gelegen langs de binnenkant van de vesten ten zuiden van de Zwartzustersberg",
        "type": "nabij", "straat": "Zwartzustersvest", "kruising": "Zwartzustersberg", "meter": 40, "richting": "zuid"},
    "Hoogstratenplein": {
        "citaat": "Hoogstratenplein: binnenkant van de vesten ter hoogte van de Keizerstraat",
        "type": "kruising", "straat": "Hoogstratenplein", "met": "Keizerstraat"},
    "Hendrik Speecqvest": {
        "citaat": "Verkeersstop langs de binnenkant van de vesten, die de verbinding richting het Kardinaal Mercierplein onderbreekt",
        "type": "kruising", "straat": "Hendrik Speecqvest", "met": "Kardinaal Mercierplein"},
    "Schuttersvest": {
        "citaat": "Verkeersstop langs de binnenkant van de vesten die de verbinding komende vanaf het Kardinaal Mercierplein richting Schuttersvest onderbreekt",
        "type": "kruising", "straat": "Schuttersvest", "met": "Kardinaal Mercierplein"},
    "Frans Halsvest": {
        "citaat": "Verkeersstop die de Frans Halsvest onderbreekt, gelegen tussen de Jan Bolstraat en Populierendreef",
        "type": "tussen", "straat": "Frans Halsvest", "van": "Jan Bolstraat", "tot": "Populierendreef"},
    "Sint-Gommarusstraat": {
        "citaat": "Verkeersstop op de aansluiting van de Sint-Gommarusstraat met de Jan Bolstraat",
        "type": "kruising", "straat": "Sint-Gommarusstraat", "met": "Jan Bolstraat"},
    "Kleine Nieuwedijkstraat": {
        "citaat": "Verkeersstop die de Kleine Nieuwedijkstraat onderbreekt ter hoogte van de spoorweg",
        "type": "spoorkruising", "straat": "Kleine Nieuwedijkstraat"},
    "Caputsteenstraat": {
        "citaat": "Verkeersstop die de Caputsteenstraat onderbreekt, gelegen ten westen van de spoorlijn",
        "type": "spoorkruising", "straat": "Caputsteenstraat"},
    "Hoogstraat/Milsenstraat": {
        "citaat": "camera Hoogstraat/Milsenstraat (jaarverslag 2024)",
        "type": "kruising", "straat": "Hoogstraat", "met": "Milsenstraat"},
    "Mezenstraat": {
        "citaat": "Verkeersstop die de route onderbreekt tussen de Mezenstraat en het woonzorgcentrum Roosendaelveld",
        "type": "uiteinde", "straat": "Mezenstraat", "naar": "Woonzorgcentrum Roosendaelveld",
        "label": "verkeersstop volgens het autoluwreglement van de stad, gezet op het einde van de straat richting het woonzorgcentrum (OpenStreetMap); de paal kan iets verder op die doorsteek staan"},
    # Zonecamera's die het reglement enkel in de stratenlijst noemt, met huisnummers:
    # het adrespunt is dan de beste plek die de stad zelf aanwijst.
    "Wollemarkt": {
        "citaat": "Wollemarkt (nrs 2-10)",
        "type": "huisnummer", "straat": "Wollemarkt", "nummer": "2",
        "bron": "Reglement autoluwe binnenstad, stratenlijst zone 2 (GR 27/11/2023); Radio Reflex 02/07/2019: de nieuwe camera op de Wollemarkt achter de kathedraal controleert ook de Schoolstraat, Nieuwwerk en de Scheerstraat",
        "label": "plaats volgens de stratenlijst van het autoluwreglement (Wollemarkt 2-10), gezet op het adrespunt uit het Vlaams Adressenregister"},
    "Korenmarkt": {
        "citaat": "Korenmarkt (nrs 3-7)",
        "type": "huisnummer", "straat": "Korenmarkt", "nummer": "3",
        "bron": "Reglement autoluwe binnenstad en verkeersstops, stratenlijst zone 2 (GR 16/09/2025); RTV 11/2023: het heraangelegde deel tussen de Korenmarkt en de Louizastraat wordt autoluw",
        "label": "plaats volgens de stratenlijst van het autoluwreglement (Korenmarkt 3-7), gezet op het adrespunt uit het Vlaams Adressenregister"},
    # De knip van 2019 op de Kruisbaan staat in geen reglement meer (in 2023: "niet
    # meer in gebruik"); de regionale pers beschreef de plek toen ze verdween.
    "Kruisbaan": {
        "citaat": "de knip op de Kruisbaan ter hoogte van kleuterschool Pius X",
        "type": "huisnummer", "straat": "Kruisbaan", "nummer": "119",
        "bron": "RTV (december 2019) en Radio Reflex (10/12/2019); de kleuterschool is Kruisbaan 119 (OpenStreetMap, Vlaams Adressenregister)",
        "label": "plaats volgens de regionale pers van december 2019 (knip ter hoogte van kleuterschool Pius X), gezet op het adrespunt Kruisbaan 119"},
}


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


def meter(a, b):
    dx = (a[0] - b[0]) * 111320 * math.cos(math.radians((a[1] + b[1]) / 2))
    dy = (a[1] - b[1]) * 110540
    return math.hypot(dx, dy)


def dichtste_paar(lijnen_a, lijnen_b):
    """Het dichtste puntenpaar tussen twee bundels polylijnen (op knooppunten en
    segmentprojecties), met de afstand ertussen in meter."""
    beste = (float("inf"), None)
    for la in lijnen_a:
        for lb in lijnen_b:
            for p in la:
                q, d = projecteer(p, lb)
                if d < beste[0]:
                    beste = (d, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
            for p in lb:
                q, d = projecteer(p, la)
                if d < beste[0]:
                    beste = (d, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2))
    return beste


def projecteer(p, lijn):
    """Het punt op de polylijn dat het dichtst bij p ligt, en de afstand in meter."""
    beste = (None, float("inf"))
    for a, b in zip(lijn, lijn[1:]):
        schaal = 111320 * math.cos(math.radians(a[1]))
        bx, by = (b[0] - a[0]) * schaal, (b[1] - a[1]) * 110540
        px, py = (p[0] - a[0]) * schaal, (p[1] - a[1]) * 110540
        lengte2 = bx * bx + by * by
        t = 0 if lengte2 == 0 else max(0.0, min(1.0, (px * bx + py * by) / lengte2))
        q = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
        d = math.hypot(px - t * bx, py - t * by)
        if d < beste[1]:
            beste = (q, d)
    return beste


def loop_langs(lijnen, start, afstand, richting=None):
    """Een punt op de straat, `afstand` meter van `start`; met een windrichting
    als er twee kanten op kan worden gelopen."""
    kandidaten = []
    for lijn in lijnen:
        q, d = projecteer(start, lijn)
        if d > 25:
            continue
        # de polylijn in beide richtingen aflopen vanaf de projectie
        for volgorde in (lijn, list(reversed(lijn))):
            # begin bij het segment waar q op ligt
            pad = [q]
            gestart = False
            for a, b in zip(volgorde, volgorde[1:]):
                if not gestart:
                    _, dq = projecteer(q, [a, b])
                    if dq < 1:
                        gestart = True
                        pad.append(b)
                    continue
                pad.append(b)
            gelopen = 0
            for a, b in zip(pad, pad[1:]):
                stuk = meter(a, b)
                if gelopen + stuk >= afstand:
                    f = (afstand - gelopen) / stuk if stuk else 0
                    kandidaten.append((a[0] + f * (b[0] - a[0]), a[1] + f * (b[1] - a[1])))
                    break
                gelopen += stuk
    if not kandidaten:
        return None
    if richting == "noord":
        return max(kandidaten, key=lambda k: k[1])
    if richting == "zuid":
        return min(kandidaten, key=lambda k: k[1])
    return kandidaten[0]


def adrespunt(straat, nummer):
    """Het adrespunt uit het Vlaams Adressenregister, via het bestaande geocode-script."""
    sys.path.insert(0, HIER)
    import geocode_cameras
    try:
        ids = geocode_cameras.adressen(straat, nummer, maximum=3)
        punten = [q for q in (geocode_cameras.punt_van_adres(i) for i in ids) if q]
        return geocode_cameras.middenpunt(punten) if punten else None
    except Exception as fout:
        print(f"   adressenregister: {fout}")
        return None


def main():
    cams = json.load(open(CAMERAS, encoding="utf-8"))
    namen = set()
    for r in RECEPTEN.values():
        namen.update(v for k, v in r.items() if k in ("straat", "van", "tot", "met", "kruising"))
    regex = "^(" + "|".join(re.escape(n) for n in sorted(namen)) + ")$"
    print("OpenStreetMap bevragen: straten uit het reglement en de spoorlijn ...")
    wegen_ruw = overpass('[out:json][timeout:120];(way["highway"]["name"~"' + regex + '"]' + BBOX
                         + ';way["railway"="rail"]' + BBOX + ";);out geom;")
    if wegen_ruw is None:
        print("Overpass niet bereikbaar; cameras.json blijft ongemoeid.")
        return 1
    wegen, spoor = {}, []
    for weg in wegen_ruw:
        geom = [(p["lon"], p["lat"]) for p in weg.get("geometry", [])]
        if weg["tags"].get("railway") == "rail":
            spoor.append(geom)
        else:
            wegen.setdefault(weg["tags"].get("name"), []).append(geom)
    ontbrekend = sorted(n for n in namen if n not in wegen)
    if ontbrekend:
        print("   niet gevonden in OpenStreetMap:", ", ".join(ontbrekend))
    plekken = {}
    doelen = sorted({r["naar"] for r in RECEPTEN.values() if r.get("naar")})
    if doelen:
        regex2 = "^(" + "|".join(re.escape(n) for n in doelen) + ")$"
        for plek in overpass('[out:json][timeout:120];nwr["name"~"' + regex2 + '"]' + BBOX + ";out center;") or []:
            midden = plek.get("center") or {"lon": plek.get("lon"), "lat": plek.get("lat")}
            if midden.get("lon") is not None:
                plekken.setdefault(plek["tags"]["name"], (midden["lon"], midden["lat"]))

    geplaatst = 0
    for naam, recept in RECEPTEN.items():
        rij = cams["cameras"].get(naam)
        if rij is None:
            print(f"   {naam}: staat niet in cameras.json")
            continue
        soort = recept["type"]
        punt, toelichting = None, ""
        if soort == "kruising":
            d, punt = dichtste_paar(wegen.get(recept["straat"], []), wegen.get(recept["met"], []))
            toelichting = f"kruising {recept['straat']} x {recept['met']} (straten {round(d)} m uiteen)"
            if d > 30:
                punt = None
        elif soort == "spoorkruising":
            d, punt = dichtste_paar(wegen.get(recept["straat"], []), spoor)
            toelichting = f"kruising van {recept['straat']} met de spoorlijn ({round(d)} m)"
            if d > 30:
                punt = None
        elif soort == "tussen":
            d1, p1 = dichtste_paar(wegen.get(recept["straat"], []), wegen.get(recept["van"], []))
            d2, p2 = dichtste_paar(wegen.get(recept["straat"], []), wegen.get(recept["tot"], []))
            if p1 and p2 and d1 <= 30 and d2 <= 30:
                midden = ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)
                # op het stuk straat dat het dichtst bij het midden ligt, niet op het
                # langste stuk: een straat bestaat in OSM vaak uit meerdere wegen
                punt, _ = min((projecteer(midden, lijn) for lijn in wegen.get(recept["straat"], [])),
                              key=lambda uitkomst: uitkomst[1])
                toelichting = f"midden van {recept['straat']} tussen {recept['van']} en {recept['tot']} ({round(meter(p1, p2))} m uiteen)"
        elif soort == "nabij":
            d, kruispunt = dichtste_paar(wegen.get(recept["straat"], []), wegen.get(recept["kruising"], []))
            if kruispunt and d <= 30:
                punt = loop_langs(wegen.get(recept["straat"], []), kruispunt, recept["meter"], recept.get("richting"))
                toelichting = f"{recept['meter']} m voorbij de kruising {recept['straat']} x {recept['kruising']}" + (f", kant {recept['richting']}" if recept.get("richting") else "")
        elif soort == "huisnummer":
            punt = adrespunt(recept["straat"], recept["nummer"])
            toelichting = f"adrespunt {recept['straat']} {recept['nummer']} (Vlaams Adressenregister)"
        elif soort == "uiteinde":
            doel = plekken.get(recept["naar"])
            einden = [lijn[k] for lijn in wegen.get(recept["straat"], []) for k in (0, -1)]
            if doel and einden:
                punt = min(einden, key=lambda e: meter(e, doel))
                toelichting = f"einde van {recept['straat']} het dichtst bij {recept['naar']} ({round(meter(punt, doel))} m ervandaan)"
            elif not doel:
                toelichting = f"{recept['naar']} niet gevonden in OpenStreetMap"

        if not punt:
            print(f"   {naam}: niet plaatsbaar ({toelichting or soort})")
            rij.pop("reglement_positie", None)
            continue
        rij["reglement_positie"] = {
            "punt": [round(punt[0], 6), round(punt[1], 6)],
            "citaat": recept["citaat"],
            "rekenwijze": toelichting,
            "bron": recept.get("bron", BRON),
            "label": recept.get("label", LABEL),
        }
        geplaatst += 1
        afwijking = ""
        if rij.get("osm_positie"):
            afwijking = f"; OSM-punt ligt {round(meter(punt, rij['osm_positie']['punt']))} m verderop"
        elif rij.get("positie_straatmidden"):
            afwijking = f"; {round(meter(punt, rij['positie_straatmidden']))} m van het straatmidden"
        print(f"   {naam}: {toelichting}{afwijking}")

    # de positielaag toepassen: handmatig > OSM-punt met ANPR-tag > reglement >
    # ongetagde verkeerscamera uit OSM > straatmidden. Een punt dat iemand als
    # ANPR intekende is het sterkste bewijs; de officiele omschrijving van de
    # stad gaat voor op een camera waarvan niemand zei wat ze doet.
    for naam, rij in cams["cameras"].items():
        osm = rij.get("osm_positie")
        osm_is_anpr = bool(osm) and (osm.get("soort") or "").lower() == "alpr"
        if rij.get("handmatig") or osm_is_anpr:
            continue
        if osm and not rij.get("reglement_positie"):
            continue
        if rij.get("reglement_positie"):
            rij["positie"] = rij["reglement_positie"]["punt"]
            rij["positie_bron"] = rij["reglement_positie"].get("label") or LABEL
        elif rij.get("positie_straatmidden"):
            rij["positie"] = rij["positie_straatmidden"]
            rij["positie_bron"] = "midden van de straat (Vlaams Adressenregister)"

    cams["_leesmij"] = (
        "Posities, in volgorde van sterkte: handmatig > camerapunt met ANPR-tag uit OpenStreetMap "
        "(ODbL, verifieer_cameras_osm.py) > de plek die een officiele omschrijving aanwijst "
        "(plaats_verkeersstops.py: het autoluwreglement, een stratenlijst met huisnummers, of voor de "
        "knip van 2019 de regionale pers; het citaat en de rekenwijze staan onder reglement_positie) > "
        "verkeerscamera uit OpenStreetMap zonder ANPR-tag > midden van de straat uit het Vlaams "
        "Adressenregister (geocode_cameras.py). Vul 'handmatig' met [lengtegraad, breedtegraad] om een "
        "camera vast te zetten; de scripts blijven daar af. Google Maps is geen bron: hun licentie "
        "verbiedt coordinaten overnemen.")

    with open(CAMERAS, "w", encoding="utf-8") as bestand:
        json.dump(cams, bestand, ensure_ascii=False, indent=1)
    print(f"cameras.json bijgewerkt: {geplaatst} verkeersstops uit het reglement geplaatst")
    return 0


if __name__ == "__main__":
    sys.exit(main())
