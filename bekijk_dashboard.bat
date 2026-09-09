@echo off
rem Bekijk het GASAM-proefstuk lokaal: opent de browser en start zo nodig een serverje.
rem Het dashboard werkt ook met een gewone dubbelklik op dist\index.html;
rem dit script is er voor wie liefst een http-adres heeft (http://localhost:8791).
cd /d "%~dp0dist"
start "" "http://localhost:8791/index.html"
python -m http.server 8791
