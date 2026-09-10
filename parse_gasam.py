"""Haalt de Mechelse cijfers uit de GASAM-jaarverslagen.

GASAM (sinds 2022 GAS Rivierenland) handelt de gemeentelijke administratieve
sancties af voor twaalf besturen. Enkel het hoofdstuk over Mechelen wordt hier
gelezen, en daarvan de twee onderdelen die dit dashboard toont:

  autoluw   GAS 4, negatie van verkeersbord C3, vastgesteld door ANPR-camera's
  parkeren  GAS 4, stilstaan en parkeren, vastgesteld door de vaststellers

Per jaargang worden dezelfde velden gezocht: het jaartotaal, de twaalf maanden,
de afhandeling van de dossiers, de woonplaats van de overtreders, en voor
autoluw ook de vaststellingen per camera. Elke jaargang zet die cijfers ergens
anders neer (lopende tekst, tabel of grafiek), dus elk veld wordt op meerdere
manieren geprobeerd. Wat niet gevonden wordt blijft leeg: liever een gat dan een
gok.

Twee harde controles, want een leesfout in een grafiek is stil:
  - de som van de twaalf maanden moet het jaartotaal halen
  - de som van de camera's moet het jaartotaal halen
Halen ze dat niet, dan meldt het script dat en laat het veld leeg.

Draaien:  python parse_gasam.py
Uit:      data/gasam_mechelen.json
"""

import json
import os
import re
import sys

import gasam_lees as lees

HIER = os.path.dirname(os.path.abspath(__file__))
BRONMAP = os.path.join(os.path.dirname(HIER), "GASAM")
UIT = os.path.join(HIER, "data", "gasam_mechelen.json")

# De verslagen schrijven camerastanden elk jaar anders af ("Merode", "Merodestr",
# "F. de Merodestraat"). Zonder deze tabel valt dezelfde camera in de grafiek
# uiteen in vijf verschillende palen.
CAMERANAMEN = {
    "begijn": "Begijnenstraat",
    "begijnenstr": "Begijnenstraat",
    "begijnenstraat": "Begijnenstraat",
    "boucherystr": "Désiré Boucherystraat",
    "d. boucherystraat": "Désiré Boucherystraat",
    "desire boucherystraat": "Désiré Boucherystraat",
    "haver": "Haverwerf",
    "haverw": "Haverwerf",
    "haverwerf": "Haverwerf",
    "havenwerf": "Haverwerf",
    "ijzerenleen": "IJzerenleen",
    "ivo cornelisstraat": "Ivo Cornelisstraat",
    "kruisbaan": "Kruisbaan",
    "l schip": "Lange Schipstraat",
    "l. schip": "Lange Schipstraat",
    "l schipstr": "Lange Schipstraat",
    "l. schipstraat": "Lange Schipstraat",
    "lange schipstraat": "Lange Schipstraat",
    "mechelsbroekstraat": "Mechelsbroekstraat",
    "merode": "Frederik de Merodestraat",
    "merodestr": "Frederik de Merodestraat",
    "merodestraat": "Frederik de Merodestraat",
    "f. de merodestraat": "Frederik de Merodestraat",
    "nauwstraat": "Nauwstraat",
    "olv straat": "Onze-Lieve-Vrouwestraat",
    "onze-lieve-vrouwestraat": "Onze-Lieve-Vrouwestraat",
    "st-janstr": "Sint-Janstraat",
    "st. janstraat": "Sint-Janstraat",
    "sint-janstraat": "Sint-Janstraat",
    "st 20": "Steenweg 20",
    "st. 20": "Steenweg 20",
    "steen 20": "Steenweg 20",
    "steenweg 20": "Steenweg 20",
    "st 44": "Steenweg 44",
    "st. 44": "Steenweg 44",
    "steen 44": "Steenweg 44",
    "steenweg 44": "Steenweg 44",
    "tuin": "Tuinstraatje",
    "tuinstr": "Tuinstraatje",
    "tuinstraatje": "Tuinstraatje",
    "v beethstr": "Van Beethovenstraat",
    "v. beethovenstraat": "Van Beethovenstraat",
    "van beethovenstraat": "Van Beethovenstraat",
    "v hoeystr": "Van Hoeystraat",
    "v. hoeystraat": "Van Hoeystraat",
    "van hoeystraat": "Van Hoeystraat",
    "veemarkt": "Veemarkt",
    "vijfhoek": "Vijfhoek",
    "wollemarkt": "Wollemarkt",
    "zak": "Zakstraat",
    "zakstr": "Zakstraat",
    "zakstraat": "Zakstraat",
    "zout": "Zoutwerf",
    "zoutw": "Zoutwerf",
    "zoutwerf": "Zoutwerf",
    "caputsteenstraat": "Caputsteenstraat",
    "h. speecqvest": "Hendrik Speecqvest",
    "hendrik speecqvest": "Hendrik Speecqvest",
    "kleine nieuwedijkstraat": "Kleine Nieuwedijkstraat",
    "koningin astridlaan": "Koningin Astridlaan",
    "van benedenlaan 1": "Van Benedenlaan 1",
    "van benedenlaan 47": "Van Benedenlaan 47",
    "frans halsvest": "Frans Halsvest",
    "hoogstratenplein": "Hoogstratenplein",
    "olivetenvest": "Olivetenvest",
    "schuttersvest": "Schuttersvest",
    "sint-gommarusstraat": "Sint-Gommarusstraat",
    "grote markt": "Grote Markt",
    "hoogstraat/milsenstraat": "Hoogstraat/Milsenstraat",
    "korenmarkt": "Korenmarkt",
    "mezenstraat": "Mezenstraat",
    "zwartzustersvest": "Zwartzustersvest",
    "désiré boucherystraat": "Désiré Boucherystraat",
    "desiré boucherystraat": "Désiré Boucherystraat",
    "?": "onbekend",
    "onbekend": "onbekend",
}

meldingen = []
# gevuld in main(): de overgetypte maandtabellen van 2015 en 2016, en de
# overgetypte figuren per camera van 2022 t/m 2024
MAANDTABELLEN = {}
DOSSIERFIGUREN = {}


def meld(tekst):
    meldingen.append(tekst)
    print("   ! " + tekst)


def cameranaam(ruw):
    sleutel = " ".join(ruw.lower().replace("’", "'").split())
    # koppen die over twee regels braken plakken aaneen: 'Steen' + '20'
    sleutel = re.sub(r"([a-z])(\d)", r"\g<1> \g<2>", sleutel)
    if sleutel in CAMERANAMEN:
        return CAMERANAMEN[sleutel]
    meld(f"onbekende cameranaam: {ruw!r}")
    return ruw.strip()


def verslagen():
    """De jaarverslagen in de bronmap, op jaartal."""
    uit = {}
    for naam in sorted(os.listdir(BRONMAP)):
        if not naam.lower().endswith(".pdf"):
            continue
        jaar = re.search(r"(20\d\d)", naam)
        if jaar:
            uit[int(jaar.group(1))] = os.path.join(BRONMAP, naam)
    return uit


def hoofdstuk_mechelen(doc):
    """Eerste en laatste pagina van het Mechelen-hoofdstuk (1-gebaseerd)."""
    start = None
    for nr in range(1, doc.page_count + 1):
        tekst = lees.paginatekst(doc, nr)
        if start is None:
            # de inhoudsopgave bevat dezelfde koppen: die staat vooraan, dus
            # pas vanaf de tweede helft van het verslag zoeken
            if nr < doc.page_count * 0.2:
                continue
            if re.search(r"^\s*3\.\d\.\d\.?\s*Mechelen\s*$", tekst, re.M) or re.search(
                r"^\s*3\.\d\.\s*Politiezone Mechelen\s*$", tekst, re.M
            ):
                start = nr
            continue
        # het hoofdstuk eindigt bij het volgende zone- of gemeentekopje; sinds
        # 2024 heten die "3.4.3 Puurs-Sint-Amands" (zonder punt na het cijfer)
        if re.search(r"^\s*3\.\d\.\s*(Politiezone|Samenvattend)", tekst, re.M) or re.search(
            r"^\s*3\.\d\.\d\s+(?!Mechelen)[A-Z]", tekst, re.M
        ):
            return start, nr - 1
    return start, doc.page_count if start else (None, None)


def deelpaginas(doc, van, tot, kop, stopkoppen):
    """Paginabereik van een onderdeel binnen het hoofdstuk, op zijn kop."""
    start = None
    for nr in range(van, tot + 1):
        tekst = lees.paginatekst(doc, nr)
        if start is None:
            if re.search(rf"^\s*{kop}\s*$", tekst, re.M | re.I):
                start = nr
            continue
        for stop in stopkoppen:
            if re.search(rf"^\s*{stop}\s*$", tekst, re.M | re.I):
                return start, nr - 1
    return (start, tot) if start else (None, None)


def tekst_van(doc, van, tot):
    return "\n".join(lees.paginatekst(doc, nr) for nr in range(van, tot + 1))


def eerste_maandreeks(doc, van, tot, totaal):
    """De maandgrafiek van dit onderdeel, gecontroleerd op het jaartotaal."""
    for nr in range(van, tot + 1):
        reeks = lees.maandreeks(doc, nr)
        if not reeks:
            continue
        if totaal and sum(reeks) != totaal:
            meld(f"maandreeks p{nr} telt {sum(reeks)}, verslag zegt {totaal}")
            continue
        return reeks, nr
    return None, None


def afhandeling(tekst):
    """De taartpunten 'Initieel; 20127 / Gunstig; 1547 / ...' uit de grafiek.

    Vanaf 2017 zetten de verslagen die als datalabels in de taart. In 2015 en
    2016 staan ze in een tabelletje onder een staafgrafiek; die vangt
    afhandeling_tabel() op.
    """
    uit = {}
    for naam, waarde in re.findall(
        r"(Initieel|Gunstig|Ongunstig|Sepot|Beroep|Verweer|Waarschuwing\w*)\s*[;:]\s*\n?\s*([\d.\s]{1,9}?)(?=\n|$)",
        tekst,
        re.I,
    ):
        getal = re.sub(r"[.\s]", "", waarde)
        if getal.isdigit():
            uit[naam.lower()] = int(getal)
    # 2015 en 2016 zetten het aantal verweren niet als taartlabel maar in een zin:
    # "Voor 8.30% werd een verweer ingediend (822 dossiers)". In 2016 heet die taartpunt
    # zelfs "Overig", een woord dat in de inbreukentabellen iets heel anders betekent,
    # dus we lezen liever de zin. De tekst is al afgebakend tot deze sectie, dus het
    # cijfer van de autoluwe zones kan er niet tussen komen.
    if "verweer" not in uit:
        zin = re.search(r"(?i)werd\s+een\s+verweer\s+ingediend\s*\(\s*([\d.\s]+)\s*dossiers", tekst)
        if zin:
            getal = re.sub(r"[.\s]", "", zin.group(1))
            if getal.isdigit():
                uit["verweer"] = int(getal)
    return uit


def uit_tabel(tabel, veld, jaar):
    """Een cel uit de meerjarentabel; de jaarsleutels zijn daar getallen, in de json tekst."""
    rij = tabel.get(veld) or {}
    waarde = rij.get(jaar)
    return waarde if waarde is not None else rij.get(str(jaar))


def afhandeling_tabel(tekst):
    """Afhandeling uit de jaartabel 'Verweer / Gunstig / Ongunstig / Beroep'."""
    uit = {}
    for naam in ("verweer", "gunstig", "ongunstig", "beroep"):
        tabel = lees.jaartabel(tekst, naam)
        if tabel:
            uit[naam] = tabel
    return uit


def woonplaats(tekst, jaar=None):
    """Aandeel inwoners en niet-inwoners, zoals het verslag het zelf formuleert.

    Autoluw en parkeren zijn hier elkaars spiegelbeeld: bij de camera's is vier op
    de vijf overtreders een niet-Mechelaar, bij parkeren ongeveer de helft. De
    verslagen schrijven dat nu eens vanuit de inwoners, dan weer vanuit de
    niet-inwoners, en ze wisselen ook van werkwoordstijd.
    """
    percent = lees.zoek_kommagetal(
        tekst,
        r"(\d{1,3}(?:[.,]\d+)?)\s*%\)?[^.\n]{0,60}?"
        r"(?:wordt|worden|werd|werden)\s+begaan door niet-inwoners",
    )
    if percent is not None:
        return {"niet_inwoners_procent": percent, "inwoners_procent": round(100 - percent, 2)}
    percent = lees.zoek_kommagetal(
        tekst,
        r"(\d{1,3}(?:[.,]\d+)?)\s*%[,)]?[^.\n]{0,60}?"
        r"(?:wordt|worden|werd|werden|,)?\s*begaan door inwoners",
    )
    if percent is not None:
        return {"inwoners_procent": percent, "niet_inwoners_procent": round(100 - percent, 2)}
    # sinds 2022 een meerjarentabel met percentages ("Inwoners stad 51% 50,2% ... 50%"):
    # de laatste kolom is het verslagjaar
    rij = re.search(r"Inwoners stad\s+((?:\d{1,3}(?:,\d+)?%\s+){2,})", tekst)
    if rij:
        pct = [float(x.rstrip("%").replace(",", ".")) for x in rij.group(1).split()]
        return {"inwoners_procent": pct[-1], "niet_inwoners_procent": round(100 - pct[-1], 2)}
    tabel_in = lees.jaartabel(tekst, "Inwoners stad")
    tabel_uit = lees.jaartabel(tekst, "Niet-inwoners")
    # een jaartabel met percentages: alles boven 100 komt uit een andere tabel
    # (in 2017 stonden er feitcodes in de weg) en gooien we weg
    if tabel_in and tabel_uit and max(list(tabel_in.values()) + list(tabel_uit.values())) <= 100:
        return {"per_jaar_inwoners_procent": tabel_in, "per_jaar_niet_inwoners_procent": tabel_uit}
    return {}


def cameras_uit_tabel(doc, van, tot):
    """De tabel 'CAMERA | jan | ... | Totaal' (jaargangen 2017 en 2018).

    De tekstlaag geeft die tabel cel per cel terug: eerst de kop, dan per camera
    de naam gevolgd door dertien getallen, twaalf maanden en het jaartotaal. We
    houden ze alle dertien: de maandkolommen dragen de tijdlijn en de heatmap in
    het dashboard, het jaartotaal is de controle.
    """
    uit, maanden = {}, {}
    for nr in range(van, tot + 1):
        tekst = lees.paginatekst(doc, nr)
        if "CAMERA" not in tekst:
            continue
        regels = [r.strip() for r in tekst.split("\n") if r.strip()]
        i = 0
        while i < len(regels):
            regel = regels[i]
            sleutel = " ".join(regel.lower().split())
            if sleutel in CAMERANAMEN and sleutel != "?":
                getallen = []
                j = i + 1
                while j < len(regels) and len(getallen) < 13:
                    deel = regels[j].split()
                    if all(re.fullmatch(r"[\d.]+", d) for d in deel):
                        getallen.extend(int(d.replace(".", "")) for d in deel)
                        j += 1
                    else:
                        break
                if len(getallen) == 13:
                    naam = cameranaam(regel)
                    uit[naam] = getallen[12]
                    if sum(getallen[:12]) == getallen[12]:
                        maanden[naam] = getallen[:12]
                    else:
                        meld(f"tabelrij {naam}: maanden tellen {sum(getallen[:12])}, rij zegt {getallen[12]}")
                    i = j
                    continue
            i += 1
        if uit:
            return uit, maanden, nr
    return None, None, None


def cameras_maand_overgetypt(jaar, maandreeks, totaal, tabellen):
    """De maandtabel per camera van 2015 en 2016, uit camera_maanden.json.

    Die tabel staat in het verslag als beeld, dus zonder tekstlaag om te lezen.
    Ze is overgenomen in camera_maanden.json en wordt hier op drie manieren
    nageteld: elke kolom tegen de maandgrafiek die wél uit de tekstlaag komt, het
    geheel tegen het gepubliceerde jaartotaal, en de rijen tegen datzelfde
    totaal. Faalt één van die controles, dan gebruiken we de tabel niet.
    """
    ruw = tabellen.get(str(jaar))
    if not ruw:
        return None, None
    rijen = {cameranaam(naam): waarden for naam, waarden in ruw.items() if not naam.startswith("_")}
    if any(len(waarden) != 12 for waarden in rijen.values()):
        meld(f"{jaar}: overgetypte maandtabel heeft een rij zonder twaalf maanden")
        return None, None

    kolommen = [sum(waarden[m] for waarden in rijen.values()) for m in range(12)]
    if maandreeks and kolommen != list(maandreeks):
        meld(f"{jaar}: overgetypte maandtabel botst met de maandgrafiek {kolommen} tegenover {maandreeks}")
        return None, None
    som = sum(kolommen)
    if totaal and som != totaal:
        meld(f"{jaar}: overgetypte maandtabel telt {som}, jaartotaal is {totaal}")
        return None, None
    return {naam: sum(waarden) for naam, waarden in rijen.items()}, rijen


def cameras_uit_kolomgrafiek(doc, van, tot):
    """Grafiek 'woonplaats overtreders per camera' (jaargangen 2015 en 2016).

    Onder die grafiek staat een datatabel met twee rijen (inwoners van de stad en
    niet-inwoners). De kolomkoppen zijn afgekorte cameranamen die soms over twee
    regels breken ('Vijfhoe' / 'k', 'Steen' / '20'). We groeperen dus alles op
    x-positie: elke kolom is één camera, het totaal is de som van beide rijen.

    Opgelet: de woorden 'Inwoners Stad' en 'Niet-inwoners' staan op zo'n pagina
    ook in de legende van de volgende grafiek. Daarom zoeken we alle plaatsen
    waar ze staan en houden we het paar rijen dat de meeste getallen naast zich
    heeft staan.
    """
    for nr in range(van, tot + 1):
        alle = lees.spans(doc, nr)
        inwonersrijen = [y for _, y, tekst in alle if tekst.lower().strip().startswith("inwoners")]
        nietrijen = [y for _, y, tekst in alle if tekst.lower().strip().startswith("niet")]

        beste = None
        for boven in inwonersrijen:
            for onder in nietrijen:
                if not 4 < onder - boven < 24:
                    continue
                rijen = {"inwoners": boven, "niet": onder}
                kolommen = {}
                for sleutel, rij_y in rijen.items():
                    for x, y, tekst in alle:
                        if abs(y - rij_y) > 4:
                            continue
                        waarde = re.sub(r"[.\s]", "", tekst)
                        if waarde.isdigit():
                            kolommen.setdefault(sleutel, []).append((x, int(waarde)))
                if len(kolommen.get("inwoners", [])) < 3:
                    continue
                if beste is None or len(kolommen["inwoners"]) > len(beste[1]["inwoners"]):
                    for sleutel in kolommen:
                        kolommen[sleutel].sort()
                    beste = (rijen, kolommen)
        if not beste:
            continue

        rijen, kolommen = beste
        kop_y = min(rijen.values())
        # de kolomkoppen staan vlak boven de eerste waarderij en breken soms over
        # twee regels; ook een cijferstukje ('20', '44') hoort er dus bij
        labelspans = [(x, y, tekst) for x, y, tekst in alle if kop_y - 32 < y < kop_y - 2]
        posities = [x for x, _ in kolommen["inwoners"]]
        breedte = (max(posities) - min(posities)) / max(len(posities) - 1, 1)
        # elk stukje kop hoort bij de kolom waar het het dichtst bij staat; met
        # een vast venster pikt een smalle kolom de kop van zijn buur mee
        stukken = {}
        for lx, ly, tekst in labelspans:
            dichtst = min(range(len(posities)), key=lambda i: abs(posities[i] - lx))
            if abs(posities[dichtst] - lx) < breedte * 0.9 and lx > posities[0] - breedte * 0.5:
                stukken.setdefault(dichtst, []).append((ly, lx, tekst))

        uit = {}
        for i, (x, inwoners) in enumerate(kolommen["inwoners"]):
            if i not in stukken:
                continue
            naam = "".join(t for _, _, t in sorted(stukken[i]))
            niet = kolommen["niet"][i][1] if i < len(kolommen["niet"]) else 0
            uit[cameranaam(naam)] = inwoners + niet
        if len(uit) >= 3:
            return uit, nr
    return None, None


def _splits_geplakt(waarden, aantal, totaal):
    """Herstelt staaflabels die in de pdf aan elkaar geplakt zijn.

    In de jaargang 2021 staat '19161607' als één tekstfragment waar de grafiek
    twee staven toont (1916 en 1607). We proberen zo'n te lang getal op elke
    plaats door te knippen en houden de knip die zowel het aantal staven als het
    jaartotaal doet kloppen. Lukt dat niet, dan geven we niets terug.
    """
    if len(waarden) >= aantal:
        return None
    for i, (x, y, waarde) in enumerate(waarden):
        cijfers = str(waarde)
        if len(cijfers) < 6:
            continue
        for knip in range(1, len(cijfers)):
            links, rechts = cijfers[:knip], cijfers[knip:]
            if links.startswith("0") or rechts.startswith("0"):
                continue
            poging = (
                waarden[:i]
                + [(x - 0.1, y, int(links)), (x + 0.1, y, int(rechts))]
                + waarden[i + 1 :]
            )
            if len(poging) == aantal and sum(w for _, _, w in poging) == totaal:
                return poging
            hersteld = _splits_geplakt(poging, aantal, totaal)
            if hersteld:
                return hersteld
    return None


def cameras_dossiers_overgetypt(jaar, totaal, sectietekst):
    """Figuren 'aantal dossiers per camera' van 2022 t/m 2024, overgetypt in
    camera_dossiers.json omdat ze (deels) beeld zijn in de pdf.

    Drie natellingen vóór het bestand meetelt: de som van elk blok tegen het
    totaal dat de figuur zelf vermeldt, alle blokken samen tegen het
    gepubliceerde jaartotaal, en de kruiszinnen in de lopende tekst
    ("Sint-Janstraat = 5.844 in 2022, ... en 5.018 in 2024") tegen de
    overgetypte waarden. Elke afwijking betekent: melding, geen cijfers.
    """
    opzet = DOSSIERFIGUREN.get(str(jaar))
    if not opzet:
        return None, None
    cameras = {}
    for blok in opzet["blokken"]:
        som = sum(blok["cameras"].values())
        if som != blok["totaal"]:
            meld(f"{jaar}: overgetypt blok telt {som}, figuur zegt {blok['totaal']}")
            return None, None
        for naam, n in blok["cameras"].items():
            cameras[naam] = cameras.get(naam, 0) + n
    if totaal and sum(cameras.values()) != totaal:
        meld(f"{jaar}: overgetypte figuren tellen {sum(cameras.values())}, jaartotaal is {totaal}")
        return None, None
    for regel in sectietekst.splitlines():
        treffer = re.match(r"^[-\u2022o]?\s*([A-Za-z\u00c0-\u00ff][\w./'\u00c0-\u00ff -]{2,40}?)\s*=\s*(.+)$", regel.strip())
        if not treffer:
            continue
        sleutel = " ".join(treffer.group(1).lower().split())
        naam = CAMERANAMEN.get(sleutel)
        if not naam or naam not in cameras:
            continue
        for waarde, kruisjaar in re.findall(r"([\d.]{3,})\s+in\s+(20\d\d)", treffer.group(2)):
            if int(kruisjaar) != int(jaar):
                continue
            w = int(waarde.replace(".", ""))
            if cameras[naam] != w:
                meld(f"{jaar}: kruiszin zegt {naam} = {w}, overgetypt staat {cameras[naam]}")
                return None, None
    return cameras, opzet["paginas"][0]


def cameras_uit_staafgrafiek(doc, van, tot, jaar, labels, totaal):
    """Grafiek 'aantal vaststellingen per camera' (jaargangen 2019 t/m 2021).

    Daar zijn de namen beeld geworden; die komen uit camera_labels.json. De
    waarden staan wel als tekst in de pdf. Elke staaf is in deze verslagen een
    apart beeldje: samen bakenen ze het tekenvlak af, en binnen dat vlak liggen
    de waardelabels. Zo blijven de tabel erboven en het paginanummer eronder
    buiten beeld. We nemen de grafiek pas aan als het aantal staven én de som
    kloppen met het gepubliceerde jaartotaal.
    """
    namen = labels.get(str(jaar))
    if not namen:
        return None, None
    for nr in range(van, tot + 1):
        tekst = lees.paginatekst(doc, nr)
        if "per camera" not in tekst:
            continue
        pagina = doc[nr - 1]
        staafjes = [pagina.get_image_bbox(beeld) for beeld in pagina.get_images(full=True)]
        if not staafjes:
            continue
        links = min(r.x0 for r in staafjes)
        rechts = max(r.x1 for r in staafjes)
        boven = min(r.y0 for r in staafjes)
        basis = max(r.y1 for r in staafjes)
        waarden = [
            (x, y, waarde)
            for x, y, waarde in sorted(lees.getalspans(doc, nr, maxcijfers=12))
            if links - 12 < x < rechts + 12 and boven - 25 < y < basis - 2
        ]
        if len(waarden) != len(namen):
            hersteld = _splits_geplakt(waarden, len(namen), totaal)
            if not hersteld:
                meld(
                    f"cameragrafiek {jaar} p{nr}: {len(waarden)} waarden voor "
                    f"{len(namen)} camera's"
                )
                continue
            waarden = hersteld
        som = sum(w for _, _, w in waarden)
        if totaal and som != totaal:
            meld(f"cameragrafiek {jaar} p{nr} telt {som}, verslag zegt {totaal}")
            continue
        return {cameranaam(naam): w for naam, (_, _, w) in zip(namen, waarden)}, nr
    return None, None


def top_inbreuken(tekst):
    """De feitcodes uit de top 5 van parkeerinbreuken, met hun aandeel.

    Vanaf 2019 zet het verslag ze als lijstje onder de taart: '7097: Parkeren
    waar een verkeersbord E1 geldt (27%)'. Daarvoor stond dezelfde top 5 in een
    tabel met de wetsartikelen erbij, waar per feitcode '2291 dossiers = 24%'
    onderaan de cel staat; die vorm leest de tweede lus.
    """
    uit = []
    for code, omschrijving, procent in re.findall(
        r"(\d{4}):\s*(.+?)\s*\((\d{1,2}(?:[.,]\d+)?)\s*%\)", tekst, re.S
    ):
        uit.append(
            {
                "feitcode": code,
                "omschrijving": " ".join(omschrijving.split()),
                "aandeel_procent": float(procent.replace(",", ".")),
            }
        )
    if uit:
        return uit
    # sinds 2022 staat er het wetsartikel in plaats van de feitcode:
    # 'Art. 25 (E1): Parkeren waar een verkeersbord E1 geldt (36,39%)'
    for code, omschrijving, procent in re.findall(
        r"(Art\.\s*\d+(?:,\d+°)?(?:\s*\([^)]*\))?):\s*(.+?)\s*\((\d{1,2}(?:[.,]\d+)?)\s*%\)", tekst, re.S
    ):
        uit.append({"feitcode": " ".join(code.split()), "omschrijving": " ".join(omschrijving.split()),
                    "aandeel_procent": float(procent.replace(",", "."))})
    if not uit:
        # het verslag van 2024 zet het percentage achter een isgelijkteken in plaats van
        # tussen haakjes: 'Art. 25 (E1): Parkeren waar een verkeersbord E1 geldt = 32%'.
        # Zonder dit patroon vielen alle vijf de omschrijvingen van dat jaar weg en bleef
        # er op de pagina een kale feitcode staan.
        for code, omschrijving, procent in re.findall(
            r"(Art\.\s*\d+(?:,\d+°)?(?:\s*\([^)]*\))?):\s*(.+?)\s*=\s*(\d{1,2}(?:[.,]\d+)?)\s*%",
            tekst, re.S
        ):
            uit.append({"feitcode": " ".join(code.split()),
                        "omschrijving": " ".join(omschrijving.split()),
                        "aandeel_procent": float(procent.replace(",", "."))})
    if uit:
        # 2022 geeft de percentages als aandeel BINNEN de top 5 (ze tellen tot 100) en
        # zegt erbij welk deel van alle dossiers de top 5 samen is: omrekenen, zodat
        # elk jaar hetzelfde betekent (aandeel in alle dossiers)
        samen = re.search(r"Samen stellen deze (\d{1,3}(?:,\d+)?)\s*% van alle", tekst)
        if samen and abs(sum(t["aandeel_procent"] for t in uit) - 100) < 1.5:
            factor = float(samen.group(1).replace(",", ".")) / 100
            for t in uit:
                t["aandeel_procent"] = round(t["aandeel_procent"] * factor, 1)
        return uit

    for treffer in re.finditer(
        r"([\d.]{2,7})\s*\n?\s*dossiers\s*\n?\s*=\s*\n?\s*(\d{1,3}(?:[.,]\d+)?)\s*%", tekst
    ):
        aanloop = tekst[: treffer.start()]
        # de rij 'Overige ... dossiers = 26,35%' sluit de tabel af en is geen
        # feitcode; die zou anders de code van de vorige rij meekrijgen
        if re.search(r"overig\w*\s*\n?\s*$", aanloop[-40:], re.I):
            continue
        eerder = re.findall(r"(?<!\d)([78]\d{3})(?!\d)", aanloop)
        if not eerder or any(rij["feitcode"] == eerder[-1] for rij in uit):
            continue
        uit.append(
            {
                "feitcode": eerder[-1],
                "aantal": int(treffer.group(1).replace(".", "")),
                "aandeel_procent": float(treffer.group(2).replace(",", ".")),
            }
        )
    return uit[:5]


def jaartotaal(tekst):
    """Het jaartotaal zoals het verslag het in de lopende tekst schrijft.

    Elke jaargang draait dezelfde zin anders: "In totaal werden er 31 698
    vaststellingen verwerkt" (2015), "In totaal werden er in 2016 19489
    vaststellingen" (2016), "In 2021 werden er in totaal 35913 vaststellingen
    verwerkt" (2021). We nemen daarom het láátste getal vóór het woord
    vaststellingen; een jaartal dat er vlak voor staat valt zo vanzelf af.
    Duizendtallen die met een spatie geschreven zijn (31 698) worden weer
    aaneengezet.
    """
    for woord in ("vaststellingen", "dossiers"):
        for treffer in re.finditer(r"(?:in totaal|werden er)([^\n]{0,60}?)" + woord, tekst, re.I):
            stukken = re.findall(r"\d+", treffer.group(1))
            samen = []
            for stuk in stukken:
                if samen and len(stuk) == 3 and len(samen[-1]) <= 3:
                    samen[-1] += stuk
                else:
                    samen.append(stuk)
            if samen and len(samen[-1]) >= 3:
                return int(samen[-1])
    return None


def reeks_uit_jaargrafiek(doc, nr, marge=5.0):
    """Een staafgrafiek met jaartallen op de as: jaartal -> waarde, op x-positie gekoppeld.

    Het verslag van 2024 zet de reeksen "dossiers per jaar" voor overlast (blz. 99) en
    voor snelheid (blz. 120) als grafiek neer. De jaartallen staan onderaan op een rij,
    elke waarde staat vlak boven haar eigen staaf. We koppelen op x-positie, net als bij
    de maandgrafieken. De asschaal links valt vanzelf weg: die staat op een x waar geen
    enkel jaartal onder hangt.
    """
    punten = [(x, y, t.strip()) for x, y, t in lees.spans(doc, nr) if t.strip()]
    jaartallen = [(x, y, int(t)) for x, y, t in punten if re.fullmatch(r"20[0-3]\d", t)]
    if len(jaartallen) < 3:
        return {}
    rijen = {}
    for x, y, j in jaartallen:
        rijen.setdefault(round(y), []).append((x, j))
    asy, asrij = max(rijen.items(), key=lambda kv: len(kv[1]))
    if len(asrij) < 3:
        return {}
    uit = {}
    for ax, jaar in sorted(asrij):
        boven = [(abs(x - ax), t) for x, y, t in punten
                 if y < asy - 4 and abs(x - ax) <= marge and re.fullmatch(r"[\d.\s]+", t)]
        if not boven:
            continue
        getal = re.sub(r"[.\s]", "", min(boven)[1])
        if getal.isdigit():
            uit[str(jaar)] = int(getal)
    return uit


def andere_soorten(doc, van, tot):
    """De jaarreeksen voor overlast (GAS 1, 2, 3) en snelheid (GAS 5) uit het nieuwste verslag.

    Die twee soorten krijgen in de verslagen geen eigen maand- en cameracijfers, maar het
    nieuwste verslag herhaalt wel de hele geschiedenis in een staafgrafiek. Elke reeks wordt
    pas aanvaard als het jongste jaar ook in de lopende tekst van diezelfde bladzijde staat:
    zo kan een verkeerd gekoppeld label niet ongemerkt doorschuiven.
    """
    uit = {}
    recepten = (
        ("overlast", r"aantal dossiers GAS ?123", "GAS 1, 2 en 3: overlast"),
        ("snelheid", r"GAS snelheid", "GAS 5: snelheid"),
    )
    for sleutel, kop, naam in recepten:
        for nr in range(van, tot + 1):
            tekst = lees.paginatekst(doc, nr)
            if not re.search(kop, tekst, re.I):
                continue
            reeks = reeks_uit_jaargrafiek(doc, nr)
            if len(reeks) < 3:
                continue
            jongste = max(reeks)
            plat = re.sub(r"[.\s]", "", tekst)
            if str(reeks[jongste]) not in plat:
                meld(f"reeks {sleutel} op blz. {nr}: {reeks[jongste]} voor {jongste} staat "
                     f"niet in de tekst van die bladzijde, dus niet overgenomen")
                continue
            uit[sleutel] = {"naam": naam, "per_jaar": reeks, "pagina": nr}
            break
    return uit


def lees_onderdeel(doc, van, tot, jaar, soort, labels):
    tekst = tekst_van(doc, van, tot)
    totaal = jaartotaal(tekst)

    reeks_tabel = lees.jaartabel(tekst, "Vaststellingen")
    if totaal is None and reeks_tabel:
        totaal = reeks_tabel.get(jaar)

    maanden, maandpagina = eerste_maandreeks(doc, van, tot, totaal)
    if maanden is None and soort == "autoluw":
        # de maandgrafiek van 2024 is beeld: overgetypt in camera_dossiers.json,
        # en alleen bruikbaar als de som exact het jaartotaal haalt
        opzet = DOSSIERFIGUREN.get(str(jaar))
        if opzet and opzet.get("per_maand") and totaal and sum(opzet["per_maand"]) == totaal:
            maanden = opzet["per_maand"]
            maandpagina = opzet.get("maand_pagina")

    afh = afhandeling(tekst)
    afh_tabel = afhandeling_tabel(tekst)
    opzet_afh = ((DOSSIERFIGUREN.get(str(jaar)) or {}).get("afhandeling") or {}).get(soort)
    if opzet_afh and not afh.get("initieel"):
        # de afhandelingstaart is beeld (2024): initieel en sepot overgetypt, de
        # rest uit de verweertabel, en alleen aanvaard als alles samen exact het
        # jaartotaal geeft
        proef = dict(opzet_afh)
        for veld in ("verweer", "gunstig", "ongunstig", "beroep"):
            waarde = uit_tabel(afh_tabel, veld, jaar)
            if waarde is not None:
                proef[veld] = waarde
        som = sum(proef.get(v, 0) for v in ("initieel", "gunstig", "ongunstig", "sepot", "beroep"))
        if totaal and som == totaal:
            afh = proef
        else:
            meld(f"{jaar} {soort}: overgetypte afhandeling telt {som}, jaartotaal is {totaal}")
    # de tabel en de taart van hetzelfde verslag kunnen elkaar tegenspreken (2018):
    # dat zeggen we, in plaats van stil een van beide te kiezen
    verschillen = []
    for veld in ("verweer", "gunstig", "ongunstig"):
        a, b = uit_tabel(afh_tabel, veld, jaar), afh.get(veld)
        if a is not None and b is not None and a != b:
            punt = lambda n: f"{n:,}".replace(",", ".")
            verschillen.append(f"{veld} {punt(a)} in de tabel, {punt(b)} in de figuur")
    if verschillen:
        meld(f"{jaar} {soort}: het verslag spreekt zichzelf tegen (" + "; ".join(verschillen) + ")")
    # FIX: de punten van de afhandelingstaart horen samen het jaartotaal te halen. Voor
    # parkeren 2016 doet de bron dat zelf niet: 91,06 plus 0,46 plus 8,30 procent is 99,82,
    # en er blijven zo'n zeventien dossiers onbenoemd. De grafiek herschaalde dat gat stil
    # weg; nu staat het als melding op de pagina, zoals de tegenspraak van 2018.
    somdelen = sum(afh.get(k, 0) for k in ("initieel", "gunstig", "ongunstig", "sepot", "beroep"))
    if somdelen and totaal and somdelen != totaal:
        punt = lambda n: f"{n:,}".replace(",", ".")
        meld(f"{jaar} {soort}: de afhandeling telt {punt(somdelen)}, het jaartotaal is "
             f"{punt(totaal)} ({punt(abs(totaal - somdelen))} dossiers benoemt het verslag niet)")

    onderdeel = {
        "totaal": totaal,
        "per_maand": maanden,
        "reeks_per_jaar": reeks_tabel,
        "afhandeling": afh,
        "afhandeling_per_jaar": afh_tabel,
        "woonplaats": woonplaats(tekst, jaar),
        "paginas": [van, tot],
        "maandgrafiek_pagina": maandpagina,
    }

    if soort == "autoluw":
        per_maand = None
        cameras, per_maand, pagina = cameras_uit_tabel(doc, van, tot)
        herkomst = "tabel per camera per maand"
        if not cameras:
            # 2015 en 2016 hebben dezelfde tabel, maar als beeld: overgetypt en
            # nageteld tegen de maandgrafiek en het jaartotaal
            cameras, per_maand = cameras_maand_overgetypt(jaar, maanden, totaal, MAANDTABELLEN)
            herkomst = "tabel per camera per maand (overgetypt uit het beeld, nageteld)"
        if not cameras:
            cameras, pagina = cameras_uit_staafgrafiek(doc, van, tot, jaar, labels, totaal)
            herkomst = "staafgrafiek per camera (namen uit camera_labels.json)"
        if not cameras:
            cameras, pagina = cameras_dossiers_overgetypt(jaar, totaal, tekst)
            herkomst = "figuur per camera (overgetypt uit het beeld, nageteld)"
        if not cameras:
            cameras, pagina = cameras_uit_kolomgrafiek(doc, van, tot)
            herkomst = "grafiek woonplaats per camera"
        if cameras:
            som = sum(cameras.values())
            if totaal and som != totaal:
                meld(f"{jaar}: camera's tellen {som}, jaartotaal is {totaal} ({herkomst})")
            onderdeel["per_camera"] = cameras
            onderdeel["per_camera_herkomst"] = herkomst
            onderdeel["per_camera_pagina"] = pagina
            onderdeel["per_camera_som"] = som
            if per_maand:
                onderdeel["per_camera_maand"] = per_maand
        else:
            meld(f"{jaar}: geen cijfers per camera gevonden")
        # de woonplaatstaart van 2024 is beeld: overgetypt, met de som-op-100-toets
        opzet = DOSSIERFIGUREN.get(str(jaar))
        if not onderdeel.get("woonplaats") and opzet and opzet.get("woonplaats"):
            wp = opzet["woonplaats"]
            if abs(wp["inwoners_procent"] + wp["niet_inwoners_procent"] - 100) < 0.01:
                onderdeel["woonplaats"] = wp
    else:
        onderdeel["top_inbreuken"] = top_inbreuken(tekst)
        # 2024 zet ook de parkeerfiguren als beeld in de pdf: overgetypt in
        # camera_dossiers.json, en enkel bruikbaar als de natelling klopt
        opzet = (DOSSIERFIGUREN.get(str(jaar)) or {}).get("parkeren")
        if opzet:
            if not onderdeel["per_maand"] and opzet.get("per_maand") and totaal and sum(opzet["per_maand"]) == totaal:
                onderdeel["per_maand"] = opzet["per_maand"]
                onderdeel["maandgrafiek_pagina"] = opzet["paginas"][0]
            wp = opzet.get("woonplaats")
            if not onderdeel["woonplaats"] and wp and abs(wp["inwoners_procent"] + wp["niet_inwoners_procent"] - 100) < 0.01:
                onderdeel["woonplaats"] = wp
            if not onderdeel["top_inbreuken"] and opzet.get("top_inbreuken"):
                onderdeel["top_inbreuken"] = opzet["top_inbreuken"]

    return onderdeel


def main():
    global MAANDTABELLEN, DOSSIERFIGUREN
    labels = json.load(open(os.path.join(HIER, "camera_labels.json"), encoding="utf-8"))
    MAANDTABELLEN = json.load(open(os.path.join(HIER, "camera_maanden.json"), encoding="utf-8"))
    DOSSIERFIGUREN = json.load(open(os.path.join(HIER, "camera_dossiers.json"), encoding="utf-8"))
    uit = {"bron": "GASAM-jaarverslagen, verkregen via openbaarheidsverzoek", "jaren": {}}

    for jaar, pad in sorted(verslagen().items()):
        print(f"-- {jaar}: {os.path.basename(pad)}")
        doc = lees.open_verslag(pad)
        van, tot = hoofdstuk_mechelen(doc)
        if not van:
            meld(f"{jaar}: geen hoofdstuk Mechelen gevonden")
            continue
        print(f"   hoofdstuk Mechelen: p{van}-{tot}")

        jaarblok = {"bestand": os.path.basename(pad), "hoofdstuk": [van, tot]}

        av = at = None
        for kop in (
            "Autoluw",                                    # 2015 t/m 2021
            "Autoluwe binnenstad",                        # 2022
            r"3\.\d\.\d\.\d\.?\s*GAS Verkeer \(GAS4\)",   # 2023
            r"b\.\s*GAS verkeer",                         # 2024
        ):
            av, at = deelpaginas(doc, van, tot, kop,
                [r"2\s+Waarschuwingen", "Vrachtwagensluis", "Parkeren en stilstaan"])
            if av:
                break
        if av:
            jaarblok["autoluw"] = lees_onderdeel(doc, av, at, jaar, "autoluw", labels)
            print(f"   autoluw p{av}-{at}: totaal {jaarblok['autoluw']['totaal']}")
        else:
            print("   autoluw: niet in dit verslag")

        pv, pt = deelpaginas(
            doc, van, tot, "Parkeren en stilstaan", [r"3\.\d.*", r"1\.4\.2\.3.*", r"GAS ?Snelheid", r"[a-z]\.\s*GAS snelheid"]
        )
        if pv:
            jaarblok["parkeren"] = lees_onderdeel(doc, pv, pt, jaar, "parkeren", labels)
            print(f"   parkeren p{pv}-{pt}: totaal {jaarblok['parkeren']['totaal']}")
        else:
            print("   parkeren: niet in dit verslag")

        uit["jaren"][str(jaar)] = jaarblok

    # De jaarreeksen voor overlast en snelheid staan enkel in het nieuwste verslag, dat de
    # hele geschiedenis herhaalt. Daarvoor gaat dat verslag nog een keer open.
    nieuwste = sorted(verslagen().items())[-1]
    doc = lees.open_verslag(nieuwste[1])
    van, tot = hoofdstuk_mechelen(doc)
    if van:
        uit["soorten"] = andere_soorten(doc, van, tot)
        for sleutel, blok in uit["soorten"].items():
            print(f"   reeks {sleutel}: {len(blok['per_jaar'])} jaren, blz. {blok['pagina']}")
    doc.close()

    uit["meldingen"] = meldingen
    os.makedirs(os.path.dirname(UIT), exist_ok=True)
    with open(UIT, "w", encoding="utf-8") as bestand:
        json.dump(uit, bestand, ensure_ascii=False, indent=1)
    print(f"\n{UIT} geschreven, {len(meldingen)} melding(en)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
