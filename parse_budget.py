"""Haalt uit de Mechelse jaarrekeningen wat er van de planning terechtkwam.

De stad legt in het meerjarenplan vast wat een actie mag kosten en mag opbrengen.
Dat cijfer heet in de jaarrekening "Initiële kredieten": het bedrag zoals het aan
het begin van dat jaar in de boeken stond. Wijzigt de raad dat in de loop van het
jaar, dan wordt het "Eindkredieten". Wat er echt binnenkwam of buitenging staat
in de kolom "Jaarrekening". Die drie kolommen staan naast elkaar in hetzelfde
document, per actie, en dat is precies de vergelijking planning-tegenover-rekening.

Twee acties dragen dit dashboard:

  AC000039  Mechelen zorgt voor een sterke bestuurlijke handhaving (GASAM)
            Hier zitten de GAS-ontvangsten: de boetes voor autoluw en parkeren,
            en vanaf 2021 ook de lichte snelheidsovertredingen (GAS 5). Het is
            dus ruimer dan wat de GASAM-jaarverslagen over Mechelen tellen.
  AC000034  Mechelen zet in op deelsystemen, (buurt)parkings, betere
            infrastructuur en het autoluw gebied
            De uitgavenkant: wat de stad in dat autoluw gebied en in parkings
            steekt.

Daarnaast leest dit script de proef- en saldibalans die vanaf de jaarrekening
2023 bij de documentatie zit. Die splitst de GAS-ontvangsten wél uit per soort
(overlast, snelheid, en GAS 4 parkeren en autoluw) en toont apart de
parkeeropbrengsten. Voor 2020 tot 2022 bestaat die splitsing in deze documenten
niet; die jaren blijven dus leeg.

Bron: de budgetdocumenten die de pijplijn van Denk mee met Mechelen al ophaalt
(data/raw/budgetten). Dit script schrijft daar niets, het leest alleen.

Draaien:  python parse_budget.py
Uit:      data/budget_mechelen.json
"""

import glob
import json
import os
import re
import sys

import fitz

HIER = os.path.dirname(os.path.abspath(__file__))
BUDGETMAP = os.path.join(
    os.path.dirname(HIER), "DenkMeeMetMechelen", "data", "raw", "budgetten"
)
UIT = os.path.join(HIER, "data", "budget_mechelen.json")

ACTIES = {
    "AC000039": "bestuurlijke handhaving (GASAM): de GAS-ontvangsten",
    "AC000034": "deelsystemen, (buurt)parkings, infrastructuur en autoluw gebied",
}

# De rekeningnummers die met dit dashboard te maken hebben. 73-rekeningen zijn
# belastingen en boetes, 70-rekeningen zijn opbrengsten uit prestaties.
REKENINGEN = {
    "7390010": "GAS: overlast",
    "7390020": "GAS: parkeren",
    "7390030": "GAS: autoluw",
    "7390040": "GAS: snelheid",
    "7390050": "GAS 4: parkeren en autoluw",
    "7318100": "Administratiekosten GAS",
    # Deze twee horen NIET bij actie AC000039. Het meerjarenplan (AMJP10, document 04)
    # zet ze op andere acties, dus het is geen GAS-geld. Ze blijven hier staan als
    # context bij het parkeerbeleid, maar mogen nooit in de geldweergave meetellen.
    "7020600": "Parkeeropbrengsten",
    "7373000": "Belasting op ontbreken van parkeerplaatsen",
}

KOLOMMEN = ["jaarrekening", "eindkredieten", "initiele_kredieten"]


def bedrag(tekst):
    """'1.469.849' of '1.016.464,60' -> float."""
    schoon = tekst.replace(".", "").replace(",", ".")
    try:
        return float(schoon)
    except ValueError:
        return None


def jaarrekeningen():
    """De documentatiebundel bij elke jaarrekening, op jaartal."""
    uit = {}
    for pad in glob.glob(os.path.join(BUDGETMAP, "stad_en_ocmw_20*", "jaarrekening_*", "*.pdf")):
        naam = os.path.basename(pad).lower()
        if "documentatie" not in naam:
            continue
        jaar = re.search(r"jaarrekening_(20\d\d)", pad.replace("\\", "/"))
        if jaar:
            uit[int(jaar.group(1))] = pad
    return dict(sorted(uit.items()))


def actieblok(tekst, code):
    """De drie kolommen van één actie: exploitatie en investeringen.

    De tekstlaag geeft zo'n blok als een rijtje losse regels terug: eerst de
    soort ('Exploitatie'), dan de rij ('Uitgaven'), dan de drie bedragen in de
    volgorde jaarrekening, eindkredieten, initiële kredieten. Een rij die
    ontbreekt (geen investeringen voorzien) slaan we over.
    """
    treffer = re.search(rf"Actie: {code}:", tekst)
    if not treffer:
        return None
    stuk = tekst[treffer.start() : treffer.start() + 1600]
    volgende = re.search(r"\n(?:Prioritaire actie|Actie|Actieplan|Prioritair actieplan): (?!" + code + ")", stuk)
    if volgende:
        stuk = stuk[: volgende.start()]

    uit = {}
    soort = None
    regels = [r.strip() for r in stuk.split("\n") if r.strip()]
    i = 0
    while i < len(regels):
        regel = regels[i]
        if regel in ("Exploitatie", "Investeringen", "Financiering"):
            soort = regel.lower()
            i += 1
            continue
        if soort and regel in ("Uitgaven", "Ontvangsten"):
            bedragen = []
            j = i + 1
            while j < len(regels) and len(bedragen) < 3:
                waarde = bedrag(regels[j])
                if waarde is None:
                    break
                bedragen.append(waarde)
                j += 1
            if len(bedragen) == 3:
                uit.setdefault(soort, {})[regel.lower()] = dict(zip(KOLOMMEN, bedragen))
                i = j
                continue
        i += 1
    return uit or None


def actietitel(tekst, code):
    treffer = re.search(rf"Actie: {code}: ([^\n]+)", tekst)
    return " ".join(treffer.group(1).split()) if treffer else None


def saldibalans(tekst):
    """Gerealiseerde bedragen per rekeningnummer uit de proef- en saldibalans.

    Ontvangsten staan er met een minteken (het zijn creditsaldi); we draaien dat
    om zodat een opbrengst in dit bestand een positief bedrag is. De jaargang
    2023 zet het bedrag zonder euroteken, 2024 en 2025 met.
    """
    uit = {}
    for nummer, omschrijving in REKENINGEN.items():
        # rekeningnummer én omschrijving op dezelfde regel, bedrag op de volgende:
        # zo halen we de saldibalans en niet de meerjarentabel, waar hetzelfde
        # nummer op een eigen regel staat met zes jaartallen erachter
        treffer = re.search(
            rf"^{nummer}[^\S\n]+\S[^\n]*\n[^\S\n]*(-?[\d.]+,\d\d)[^\S\n]*€?", tekst, re.M
        )
        if not treffer:
            continue
        waarde = bedrag(treffer.group(1))
        if waarde is None:
            continue
        uit[nummer] = {"omschrijving": omschrijving, "gerealiseerd": round(-waarde, 2)}
    return uit


def belastingtabel(tekst, neem_rekeningkolommen):
    """Leest 'Overzicht jaarlijkse opbrengst per belastingsoort'.

    Die tabel staat zowel in het meerjarenplan en in elke aanpassing ervan als in
    de documentatie bij de jaarrekening. De kolomkop zegt per kolom wat het is:
    'Rekening 2023' is een realisatie, 'AMJP10 2026' een raming.

    Eén valstrik: in de aanpassing nr. 5 klopt het opschrift van de eerste kolom
    niet. Daar staat 'Rekening 2021' boven cijfers die in de jaarrekeningen als
    rekening 2020 terugkomen. Daarom nemen we realisaties enkel over uit de
    jaarrekeningen zelf (neem_rekeningkolommen), en uit de plandocumenten alleen
    de ramingen.

    De opmaak verschilt per jaargang: soms staan volgnummer, rekeningnummer en
    omschrijving op één regel, soms elk op een eigen regel, en soms staat er nog
    een beleidsveldcode tussen. De bedragen staan wél altijd achteraan, dus we
    nemen per rij de laatste zoveel getallen als er kolommen zijn. Zo telt de 4
    uit 'GAS 4 parkeren en autoluw' niet mee als bedrag.

    Geeft terug: {rekeningnummer: {'rekening': {jaar: bedrag}, 'raming': {...}}},
    beperkt tot de rekeningnummers die dit dashboard nodig heeft. Meerdere
    begrotingslijnen op hetzelfde rekeningnummer worden opgeteld.
    """
    kop = re.search(r"OVERZICHT JAARLIJKSE OPBRENGST PER BELASTINGSOORT(.{0,400})", tekst, re.S)
    if not kop:
        return {}
    kolommen = [
        ("rekening" if soort.lower().startswith("rekening") else "raming", int(jaar))
        for soort, jaar in re.findall(
            r"(Rekening|AMJP\d*|MJP\d*|Meerjarenplan)\s*\n?\s*(20\d\d)", kop.group(1)
        )
    ]
    if not kolommen:
        return {}

    uit = {}
    regels = [r.strip() for r in tekst.split("\n")]
    beginnen = [i for i, regel in enumerate(regels) if re.match(r"^MJP\d{6}\b", regel)]
    for tel, i in enumerate(beginnen):
        eind = beginnen[tel + 1] if tel + 1 < len(beginnen) else min(i + 12, len(regels))
        blok = " ".join(regels[i:eind])
        # onderaan elke pagina staat een voettekst met ondernemingsnummers; die
        # zou anders als laatste "bedrag" van de laatste rij gelezen worden
        voet = re.search(
            r"(Stadsbestuur|OCMW|Jaarrekening|Meerjarenplan|AMJP\d|OVERZICHT|Volgnummer|stad Mechelen)",
            blok,
        )
        if voet:
            blok = blok[: voet.start()]
        nummer = re.search(r"(?<!\d)(7\d{6})(?!\d)", blok)
        if not nummer or nummer.group(1) not in REKENINGEN:
            continue
        stukken = re.findall(r"-?\d[\d.]*(?:,\d\d)?", blok[nummer.end() :])
        bedragen = [bedrag(stuk) for stuk in stukken]
        bedragen = [waarde for waarde in bedragen if waarde is not None]
        if len(bedragen) > len(kolommen):
            # de naam stond vóór de bedragen en bevatte zelf een getal
            bedragen = bedragen[-len(kolommen) :]
        # sommige rijen laten lege cellen achteraan weg; die vullen we niet in
        rij = uit.setdefault(
            nummer.group(1),
            {"omschrijving": REKENINGEN[nummer.group(1)], "rekening": {}, "raming": {}},
        )
        for (soort, jaar), waarde in zip(kolommen, bedragen):
            if soort == "rekening" and not neem_rekeningkolommen:
                continue
            rij[soort][str(jaar)] = round(rij[soort].get(str(jaar), 0) + waarde, 2)
    return uit


def planningsbronnen():
    """De tabellen met ramingen: het meerjarenplan en elke aanpassing ervan."""
    uit = []
    for pad in glob.glob(os.path.join(BUDGETMAP, "**", "*.pdf"), recursive=True):
        naam = os.path.basename(pad).lower()
        if "belastingsoort" not in naam and "belastingssoort" not in naam:
            continue
        if "jaarrekening" in pad.lower():
            continue
        uit.append(pad)
    return sorted(uit)


def bronnaam(pad):
    """Korte naam van een planningsbron: 'AMJP5 (2021)', 'MJP 2020-2025'."""
    map_naam = os.path.basename(os.path.dirname(pad))
    jaar = re.search(r"stad_en_ocmw_(20\d\d)", pad.replace("\\", "/"))
    nummer = re.search(r"aanpassing_meerjarenplan_[\d_]*?(\d+)$", map_naam)
    if nummer:
        return f"aanpassing meerjarenplan nr. {nummer.group(1)}" + (
            f" ({jaar.group(1)})" if jaar else ""
        )
    return "meerjarenplan" + (f" ({jaar.group(1)})" if jaar else "")


def main():
    if not os.path.isdir(BUDGETMAP):
        print(f"budgetmap niet gevonden: {BUDGETMAP}")
        return 1

    uit = {
        "bron": "Jaarrekeningen stad en OCMW Mechelen (documentatie bij de jaarrekening)",
        "kolommen": {
            "initiele_kredieten": "planning: het krediet zoals het bij de start van het jaar in het meerjarenplan stond",
            "eindkredieten": "planning na de aanpassingen die de raad in de loop van het jaar goedkeurde",
            "jaarrekening": "rekening: wat er werkelijk is ontvangen of uitgegeven",
        },
        "acties": {},
        "rekeningen_per_jaar": {},
        "opbrengsten": {},
    }

    for code, uitleg in ACTIES.items():
        uit["acties"][code] = {"uitleg": uitleg, "titel": None, "jaren": {}}

    for jaar, pad in jaarrekeningen().items():
        doc = fitz.open(pad)
        tekst = "\n".join(pagina.get_text() for pagina in doc)
        print(f"-- jaarrekening {jaar}: {os.path.basename(pad)}")

        for code in ACTIES:
            blok = actieblok(tekst, code)
            if not blok:
                print(f"   ! {code} niet gevonden")
                continue
            uit["acties"][code]["jaren"][str(jaar)] = blok
            uit["acties"][code]["titel"] = uit["acties"][code]["titel"] or actietitel(tekst, code)
            exploitatie = blok.get("exploitatie", {}).get("ontvangsten")
            if exploitatie:
                print(
                    f"   {code} ontvangsten: gepland {exploitatie['initiele_kredieten']:,.0f}"
                    f" -> rekening {exploitatie['jaarrekening']:,.0f}".replace(",", ".")
                )

        rekeningen = saldibalans(tekst)
        if rekeningen:
            uit["rekeningen_per_jaar"][str(jaar)] = rekeningen
            print(f"   saldibalans: {len(rekeningen)} rekening(en)")

        tabel = belastingtabel(tekst, neem_rekeningkolommen=True)
        if tabel:
            uit["opbrengsten"][f"jaarrekening {jaar}"] = tabel
            print(f"   opbrengsttabel: {len(tabel)} rekeningnummer(s)")

    for pad in planningsbronnen():
        tekst = "\n".join(pagina.get_text() for pagina in fitz.open(pad))
        tabel = belastingtabel(tekst, neem_rekeningkolommen=False)
        if not tabel:
            continue
        naam = bronnaam(pad)
        uit["opbrengsten"][naam] = tabel
        print(f"-- {naam}: {len(tabel)} rekeningnummer(s) met GAS of parkeren")

    os.makedirs(os.path.dirname(UIT), exist_ok=True)
    with open(UIT, "w", encoding="utf-8") as bestand:
        json.dump(uit, bestand, ensure_ascii=False, indent=1)
    print(f"\n{UIT} geschreven")
    return 0


if __name__ == "__main__":
    sys.exit(main())
