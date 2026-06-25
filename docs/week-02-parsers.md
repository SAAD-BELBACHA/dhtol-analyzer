# Woche 2 - Konfigurations- und Metadatenparser

## 1. Wochenziel

Woche 2 verbindet echte DHTOL-Dateien mit den schlanken Datenmodellen aus
Woche 1.

Der Code liest drei Dateitypen:

```text
JSON → Testkonfiguration und Ovenplan
MTPX → geplante Testzeit
DATA → geloggte Board-Stresszeit und Firmwareversion
```

Der oeffentliche Stand bleibt bewusst klein. LOG-, TDMS-, Streamlit- und
Glitch-Code sind noch nicht Teil dieses GitHub-Stands.

## 2. Benutzte Bibliotheken

Nur Standardbibliothek plus `pytest` fuer Tests:

| Bibliothek | Einsatz |
|---|---|
| `json` | JSON-, MTPX- und DATA-Dateien laden |
| `re` | Zone, DUT-ID, `f_MV` und Stop-Time-Fallback suchen |
| `pathlib.Path` | Dateipfade plattformunabhaengig behandeln |
| `dataclasses` | Parser-Ergebnisse als klare Objekte |
| `enum` | feste Werte fuer Zone und Temperaturmodus |
| `ast` | sichere Auswertung von MTPX-Matheausdruecken |
| `operator` | erlaubte Rechenoperationen `+`, `-`, `*`, `/` |
| `pytest` | automatisierte Tests |

`requirements.txt` enthaelt deshalb nur:

```text
pytest>=8.0
```

## 3. JSON-Testkonfiguration

Datei:

```text
parsers/config_json.py
```

Der Parser liest:

- Testname
- Zone
- Instrumentliste
- Ovenplan
- Slot beziehungsweise Position
- DUT-Name
- Hardware-Target
- Load-Board
- DUT-Board
- uC-FSM
- HV-/MV-Modus ueber `f_MV`

Beispiel:

```json
{
  "Test Name": "run_A_test",
  "Ovenplan": [
    {
      "Zone": "A",
      "Slot": "1",
      "DUT": "88_1_2",
      "HW Target": "01be8edd"
    }
  ],
  "Testplans": [
    {"functions": [{"code": "f_MV = true"}]}
  ]
}
```

Ergebnis:

```text
test_name     = run_A_test
zone          = A
temp_mode     = MVoltage
controller_id = 88
position      = 1
dut_name      = 88_1_2
hw_target     = 01be8edd
```

### Freie DUT-Namen

Nicht jeder Test nutzt Namen wie `88_1_2`.

Auch das ist gueltig:

```json
{
  "Zone": "A",
  "Slot": "2",
  "DUT": "aa",
  "HW Target": "target-aa"
}
```

Ergebnis:

```text
controller_id = None
position      = 2
dut_name      = aa
```

## 4. HV- und MV-Erkennung

Der Modus steht im Testplan-Code:

```lua
f_MV = false
```

Zuordnung:

| Wert | Modus |
|---|---|
| `f_MV = false` | `TempMode.HV` |
| `f_MV = true` | `TempMode.MV` |
| fehlt | `TempMode.HV` als Default |

Der Parser durchsucht verschachtelte Strings in `Testplans`. Dadurch ist er
unabhaengig davon, wie tief der Code im JSON liegt.

## 5. MTPX und geplante Testzeit

Datei:

```text
parsers/mtpx.py
```

Typischer Inhalt:

```json
{
  "templateValues": [
    {
      "templateName": "stop_time",
      "templateValue": "1001*3600"
    }
  ]
}
```

Ausgabe:

```text
planned_test_seconds = 3603600
```

### Warum kein `eval()`?

`templateValue` ist Text. Gefaehrlich waere:

```python
eval("1001*3600")
```

Darum nutzt der Parser `ast` und erlaubt nur:

- Zahlen
- Klammern
- Addition
- Subtraktion
- Multiplikation
- Division

Dieser Ausdruck ist erlaubt:

```text
1001*3600
```

Dieser Ausdruck wird abgelehnt:

```text
__import__('os').system('echo no')
```

## 6. DATA-Dateien

Datei:

```text
parsers/board_data.py
```

Woche 2 speichert nur:

- `Test Info.Seconds`
- letzte Firmwareversion aus `HW History[-1].HW Info.version.fw`

Beispiel:

```json
{
  "Test Info": {
    "Cycles": 2,
    "Seconds": 123.5
  },
  "HW History": [
    {
      "HW Info": {
        "hostname": "controller-88",
        "IP": "1.2.3.4",
        "MAC": "00-00",
        "version": {
          "hw": "5.0",
          "fw": "9.0"
        }
      }
    }
  ]
}
```

Ergebnis:

```text
log_stress_seconds = 123.5
firmware_version   = 9.0
```

Bewusst nicht gespeichert:

- `Cycles`
- `hostname`
- `IP`
- `MAC`
- Hardwareversion `hw`

Grund: Diese Werte werden im aktuellen Auswertestand nicht benutzt. Sie koennen
spaeter wieder eingefuehrt werden, wenn eine Analyse sie wirklich braucht.

## 7. Fehlerbehandlung

Parser sollen bei einer einzelnen kaputten Datei nicht hart abbrechen.

Verhalten:

- kaputte JSON-Datei → leeres `ParsedConfig` plus Warnung
- fehlende oder kaputte MTPX-Datei → `None`
- fehlende oder kaputte DATA-Datei → `None`
- ungueltiger Ovenplan-Eintrag → Eintrag wird uebersprungen
- freier DUT-Name → gueltig, `controller_id = None`

## 8. Tests

Datei:

```text
tests/test_week_02_parsers.py
```

Getestet wird:

- JSON-Ovenplan
- Zone A/B/C
- HV-/MV-Erkennung
- freie DUT-Namen
- Warnung bei kaputtem JSON
- sichere MTPX-Berechnung
- Ablehnung von ausfuehrbarem MTPX-Ausdruck
- DATA-Stresszeit
- DATA-Firmwareversion
- Entfernen ungenutzter DATA-Felder aus `BoardMetadata`

Testbefehl:

```bash
pytest -q
```

## 9. Ergebnis von Woche 2

Nach Woche 2 kann der Code einzelne Konfigurations- und Metadatendateien
sicher in Python-Objekte umwandeln:

```text
JSON → ParsedConfig + OvenplanEntry
MTPX → geplante Testzeit in Sekunden
DATA → BoardMetadata mit Stresszeit + Firmwareversion
```

Naechste Schritte:

- zusammengehoerige Testordner erkennen
- Board-Logs einlesen
- TDMS-Stromdaten einlesen
- Fehler erkennen
- Temperatur-Glitches analysieren
- Streamlit-Oberflaeche bauen
