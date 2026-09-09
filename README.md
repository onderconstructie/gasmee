# GAS mee met Mechelen

Een dashboard over de Mechelse GAS-handhaving: wat de ANPR-camera's aan de autoluwe zones
vaststellen, wat er naast die camera's beboet wordt, en wat de stad aan GAS plant en int.

Live: **https://gasmee.asgaupaust.be**
Hoe het werkt (bronnen, controle, voorbehoud): [techniek.html](https://gasmee.asgaupaust.be/techniek.html)

Onderdeel van [asgaupaust.be](https://asgaupaust.be).

## Zelf draaien

```
python build.py
```

Dat giet de cijfers uit `data/` in `template.html` en schrijft `dist/index.html`, één
zelfstandig bestand zonder server of databank. `python steekproef_cijfers.py` telt daarna
een steekproef van de cijfers na tegen de bron-pdf's.

## Publiceren

Elke push naar `main` publiceert `dist/` naar GitHub Pages. Zet de hook eenmalig aan na
het klonen:

```
git config core.hooksPath .githooks
```

## Licentie

Code onder de MIT-licentie. De kaartgegevens komen van OpenStreetMap (ODbL), de
straatfoto's waarmee cameraposities zijn nagekeken van Panoramax (CC BY-SA 4.0), en de
lettertypes staan onder de Open Font License.
