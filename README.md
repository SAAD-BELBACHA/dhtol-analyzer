# DHTOL Analyzer

Lernprojekt zur automatischen Auswertung von DHTOL-Testläufen.

## Aktueller Stand: Woche 2

Fundament und Dateiparser fertig:

- gemeinsame Datenmodelle
- Statusmodell Grün/Gelb/Rot
- geplante und geloggte Stresszeit
- Berechnung der Nachbelastungszeit
- zentrale Konfigurationswerte
- Unterstützung für 1–3 Zonen mit jeweils bis zu 8 Boards
- JSON-Testkonfiguration und Ovenplan
- automatische HV-/MV-Erkennung über `f_MV`
- geplante Testzeit aus MTPX
- Board-Laufzeit und Hardwaredaten aus DATA

Dokumentation:

- [Woche 1 – Fundament](docs/week-01-foundation.md)
- [Woche 2 – Konfigurations- und Metadatenparser](docs/week-02-parsers.md)

## Nachbelastungslogik

```text
Nachbelastungszeit = max(0, geplante Testzeit − Log-Stresszeit)
```

Beispiel aus echtem Testlauf:

```text
Geplante Testzeit:  1001,000 h
Log-Stresszeit:      640,327 h
Nachbelastungszeit:  360,673 h
```

Die spätere PSU/EL-Analyse muss bestätigen, ob DUT während dieser Zeit
tatsächlich weiter unter Stress stand.

## Monatsplan

- Woche 1: Datenmodelle und Konfiguration — abgeschlossen
- Woche 2: JSON-, MTPX- und DATA-Parser — abgeschlossen
- Woche 3: LOG-/TDMS-Parser und Analyse
- Woche 4: Streamlit-Oberfläche, Graphen und Gesamttests

Rohdaten bleiben lokal und werden durch `.gitignore` nicht hochgeladen.
