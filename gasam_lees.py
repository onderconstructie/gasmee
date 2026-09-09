"""Leeshulp voor de GASAM-jaarverslagen.

De jaarverslagen zijn Word-exports naar pdf. De cijfers zitten op drie plaatsen,
elk met hun eigen valstrik:

1. In de lopende tekst ("In 2021 werden er in totaal 35913 vaststellingen
   verwerkt"). Betrouwbaar, maar de formulering wisselt per jaargang.
2. In echte tabellen ("Tabel 1: Aantal vaststellingen per jaar"). De tekstlaag
   geeft die kolom per kolom terug, niet rij per rij.
3. In Excel-grafieken. Daar staan de waarden wél als tekst in de pdf, maar de
   volgorde in de tekstlaag zegt niets: enkel de x-positie van elk label vertelt
   bij welke staaf het hoort. Vandaar maandreeks() en staafreeks(): die sorteren
   de getallen op x en koppelen ze aan de categorie-labels op dezelfde x.

Let op: bij een deel van de grafieken (jaargangen 2019-2021, grafiek "aantal
vaststellingen per camera") zijn de categorie-labels géén tekst maar beeld. De
getallen komen dan uit de pdf, de namen uit camera_labels.json. De controle is
dat de som van de staven het gepubliceerde totaal moet halen.
"""

import re

import fitz

MAANDEN = ["jan", "feb", "maa", "apr", "mei", "juni", "jul", "aug", "sep", "okt", "nov", "dec"]


def open_verslag(pad):
    return fitz.open(pad)


def paginatekst(doc, nr):
    """Tekst van pagina nr (1-gebaseerd, zoals in de pdf-nummering hier)."""
    return doc[nr - 1].get_text()


def spans(doc, nr):
    """Alle tekstfragmenten van een pagina met hun positie: (x, y, tekst)."""
    uit = []
    for blok in doc[nr - 1].get_text("dict")["blocks"]:
        for lijn in blok.get("lines", []):
            for span in lijn["spans"]:
                tekst = span["text"].strip()
                if tekst:
                    uit.append((span["bbox"][0], span["bbox"][1], tekst))
    return uit


def getalspans(doc, nr, maxcijfers=7):
    """Getal-labels van een pagina als (x, y, waarde).

    Word plakt naburige staaflabels soms samen in één tekstfragment ('2917 2833',
    en in de grafiek per camera van 2021 zelfs zonder spatie: '19161607' zijn in
    werkelijkheid de staven 1916 en 1607). Daarom lezen we hier op tekenniveau en
    knippen we een fragment door zodra er een gat tussen twee tekens valt dat
    groter is dan een half teken. De x-positie van elk stuk is wat het aan een
    staaf bindt.
    """
    uit = []
    for blok in doc[nr - 1].get_text("rawdict")["blocks"]:
        for lijn in blok.get("lines", []):
            for span in lijn["spans"]:
                # alleen fragmenten die niets anders dan cijfers bevatten: zo
                # blijven zinnen ("In 2021 werden er ...") en bijschriften
                # ("Totaal: 35913") buiten de grafieklezing
                inhoud = "".join(t["c"] for t in span["chars"])
                if re.search(r"[^\d\s., ]", inhoud):
                    continue
                groepen, huidig = [], []
                vorige_rand = None
                for teken in span["chars"]:
                    x0, _, x1, _ = teken["bbox"]
                    letter = teken["c"]
                    gat = x0 - vorige_rand if vorige_rand is not None else 0
                    breedte = max(x1 - x0, 0.1)
                    if letter.isspace() or gat > breedte * 0.5:
                        if huidig:
                            groepen.append(huidig)
                        huidig = []
                    if not letter.isspace():
                        huidig.append(teken)
                    vorige_rand = x1
                if huidig:
                    groepen.append(huidig)
                for groep in groepen:
                    waarde = _getal("".join(t["c"] for t in groep), maxcijfers)
                    if waarde is None:
                        continue
                    x0 = groep[0]["bbox"][0]
                    x1 = groep[-1]["bbox"][2]
                    uit.append(((x0 + x1) / 2, groep[0]["bbox"][1], waarde))
    return uit


def _getal(tekst, maxcijfers=7):
    """'1.234' of '1 234' of '35913' -> int, anders None."""
    schoon = tekst.replace(".", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"\d{1,%d}" % maxcijfers, schoon):
        return int(schoon)
    return None


def maandreeks(doc, nr):
    """De twaalf staven van een maandgrafiek, in maandvolgorde.

    Werkt door elke maandnaam op de x-as te koppelen aan het getal-label dat er
    horizontaal het dichtst bij ligt. De asschaal (0, 500, 1000, ...) staat links
    van alle staven en valt daardoor vanzelf af; voor de zekerheid gooien we de
    getallen weg die op dezelfde x-positie boven elkaar staan (dat is de as).
    """
    maandpos = {}
    for x, y, tekst in spans(doc, nr):
        sleutel = tekst.strip().lower().rstrip(".")
        if sleutel in MAANDEN and sleutel not in maandpos:
            maandpos[sleutel] = (x, y)
    if len(maandpos) < 12:
        return None

    as_y = min(y for x, y in maandpos.values())
    xen = [maandpos[m][0] for m in MAANDEN]
    afstand = (max(xen) - min(xen)) / 11
    ondergrens = min(xen) - afstand * 0.6  # links daarvan staat de asschaal

    kandidaten = [
        (x, y, waarde)
        for x, y, waarde in getalspans(doc, nr)
        if y < as_y - 2 and x > ondergrens
    ]
    kandidaten.sort()
    if len(kandidaten) == 12:
        return [k[2] for k in kandidaten]

    # minder of meer labels dan staven: koppel elk label aan de dichtste maand
    uit = {}
    for maand in MAANDEN:
        mx = maandpos[maand][0]
        dichtst = min(kandidaten, key=lambda k: abs(k[0] - mx), default=None)
        if dichtst is None or abs(dichtst[0] - mx) > afstand * 0.8:
            return None
        uit[maand] = dichtst[2]
        kandidaten.remove(dichtst)
    return [uit[m] for m in MAANDEN]


def staafwaarden(doc, nr, ymin=None, ymax=None, negeer=()):
    """Getal-labels van een staafgrafiek, van links naar rechts.

    Voor grafieken waarvan de categorie-namen als beeld in de pdf zitten. ymin en
    ymax bakenen de grafiek af; negeer bevat waarden die geen staaf zijn (zoals
    de asschaal) en die we per grafiek expliciet uitsluiten.
    """
    uit = []
    for x, y, tekst in spans(doc, nr):
        if ymin is not None and y < ymin:
            continue
        if ymax is not None and y > ymax:
            continue
        waarde = _getal(tekst)
        if waarde is None or tekst in negeer:
            continue
        uit.append((x, y, waarde, tekst))
    return sorted(uit)


def jaartabel(tekst, kop):
    """Leest een tabelletje 'Jaar | 2016 | 2017 ... / <kop> | 9904 | 9451 ...'.

    De tekstlaag geeft zo'n tabel als losse cellen terug: eerst 'Jaar' met de
    jaartallen, daarna de kop met de waarden. Een hoofdstuk bevat meerdere van
    die tabellen, en tussen de tabellen door staan taartlabels die met hetzelfde
    woord beginnen ('Verweer; 2981'). Daarom proberen we élk 'Jaar'-blok apart,
    en zoeken we de gevraagde rij enkel binnen dat blok.

    Cellen als '1547 (62%)' geven hun eerste getal; het percentage laten we vallen.
    """
    regels = [r.strip() for r in tekst.split("\n")]
    koppen = [i for i, regel in enumerate(regels) if regel.lower().startswith("jaar")]
    for begin in koppen:
        jaren, i = [], begin + 1
        while i < len(regels) and re.fullmatch(r"(19|20)\d\d", regels[i]):
            jaren.append(int(regels[i]))
            i += 1
        if len(jaren) < 2:
            continue
        for j in range(i, min(i + 40, len(regels))):
            if not regels[j].lower().startswith(kop.lower()):
                continue
            waarden = []
            for k in range(j + 1, len(regels)):
                if len(waarden) == len(jaren):
                    break
                regel = regels[k]
                # de percentages staan in dezelfde rij, soms op een eigen regel:
                # '1547' / '(62%)'. Die slaan we over, ze horen bij het getal ervoor.
                if re.fullmatch(r"\(?\d+(?:[.,]\d+)?\s*%\)?", regel):
                    continue
                stuk = regel.split()
                waarde = _getal(stuk[0]) if stuk else None
                if waarde is None:
                    if waarden:
                        break          # rij afgelopen
                    continue           # nog niets gezien: doorlezen
                waarden.append(waarde)
            if len(waarden) == len(jaren):
                return dict(zip(jaren, waarden))
    return None


def zoek_getal(tekst, patroon):
    """Eerste getal dat op een patroon volgt, punten als duizendtal weggeknipt."""
    treffer = re.search(patroon, tekst, re.I | re.S)
    if not treffer:
        return None
    return _getal(treffer.group(1))


def zoek_kommagetal(tekst, patroon):
    treffer = re.search(patroon, tekst, re.I | re.S)
    if not treffer:
        return None
    return float(treffer.group(1).replace(",", "."))
