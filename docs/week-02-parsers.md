# Woche 2 – Konfigurations- und Metadatenparser

## 1. Wochenziel

Woche 2 verbindet reale DHTOL-Dateien mit den Datenmodellen aus Woche 1.

Die Anwendung soll automatisch erkennen:

```text
Welche Boards gehören zum Test?
Welche Zone und Position besitzt jedes Board?
Läuft der Test im HV- oder MV-Modus?
Wie lange war der Test geplant?
Wie viel Stresszeit wurde je Board gespeichert?
Welche Hardware- und Firmwareversion wurde verwendet?
```

Verarbeitungsweg:

```text
JSON + MTPX + DATA
        ↓
      Parser
        ↓
TestRun, ZoneData, Board und BoardMetadata
```

## 2. JSON-Testkonfiguration

Datei:

```text
parsers/config_json.py
```

Der JSON-Parser liest:

- Testname
- Zone
- Ovenplan
- Slot beziehungsweise Position
- DUT-Name
- Hardware-Target
- Load-Board und DUT-Board
- Temperaturmodus

Beispiel:

```json
{
  "Zone": "A",
  "Slot": "1",
  "DUT": "88_1_2",
  "HW Target": "01be8edd"
}
```

Ergebnis:

```text
controller_id = 88
zone          = A
position      = 1
dut_name      = 88_1_2
hw_target     = 01be8edd
```

Controller-ID und Position bleiben getrennt. Controller `88` kann auf Position
`1` stehen. Bei späteren Testsystemen können weitere Zonen und andere
Controller-IDs verwendet werden.

## 3. Freie DUT-Namen

Nicht jeder Test verwendet einen Namen wie:

```text
58_1_2
```

Der Beispielordner `Same LOT DUTs` verwendet:

```text
aa
bb
cc
dd
```

Diese Namen sind ebenfalls gültig. Falls keine numerische Controller-ID im
DUT-Namen enthalten ist:

```text
controller_id = None
```

Zone, Position, DUT-Name und Hardware-Target bleiben trotzdem verfügbar. In
der Oberfläche erscheint die fehlende Controller-ID als `—`.

## 4. HV- und MV-Erkennung

Der Modus wird aus dem Testplan-Code gelesen:

```lua
f_MV = false
```

Zuordnung:

| Config-Wert | Modus | T0 | T1 |
|---|---|---|---|
| `f_MV = false` | HV | Low-Side-Schalter | High-Side-Schalter |
| `f_MV = true` | MV | Low-Side-Schalter | DUT-Board |

Die Logdatei besitzt in beiden Modi dieselben Spalten `t0` und `t1`. Nur die
physikalische Bedeutung von `t1` ändert sich.

Der Parser speichert deshalb:

```python
TempMode.HV
```

oder:

```python
TempMode.MV
```

Glitch-Erkennung kann weiterhin auf den Rohspalten arbeiten. Diagramme
verwenden den Modus später für die richtige Beschriftung.

## 5. MTPX und geplante Testzeit

Datei:

```text
parsers/mtpx.py
```

Die geplante Testzeit steht typischerweise im Template:

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

Der Parser wertet nur sichere mathematische Ausdrücke aus:

- Addition
- Subtraktion
- Multiplikation
- Division
- positive und negative Zahlen
- Klammern

Beliebiger Python-Code wird nicht ausgeführt.

Beispiel:

```text
1001 × 3600 = 3.603.600 Sekunden
```

Das entspricht:

```text
1001 Stunden
```

## 6. DATA-Dateien

Datei:

```text
parsers/board_data.py
```

Jedes Board besitzt eine `.data`-Datei mit Test- und Hardwareinformationen.

Gelesene Werte:

- `Test Info.Seconds`
- Anzahl Zyklen
- Hostname
- IP-Adresse
- MAC-Adresse
- Hardwareversion
- Firmwareversion

Beispiel:

```json
{
  "Test Info": {
    "Cycles": 0,
    "Seconds": 2305183.4
  }
}
```

Die gespeicherten Sekunden werden als Log-Stresszeit verwendet:

```text
Log-Stresszeit = Test Info.Seconds
```

Negative oder ungültige Werte werden auf `0` gesetzt.

## 7. Nachbelastungszeit

Mit geplanter Zeit aus MTPX und Log-Stresszeit aus DATA kann die rechnerische
Nachbelastung bestimmt werden:

```text
Rechnerische Nachbelastung
= max(0, geplante Testzeit − Log-Stresszeit)
```

Beispiel:

```text
Geplant:       10 Stunden
Geloggter Test: 8 Stunden
Differenz:      2 Stunden
```

Diese Differenz ist zunächst nur rechnerisch. Ob das Board nach dem letzten
Board-Log tatsächlich weiter bestromt wurde, wird später mit PSU-/EL- oder
Host-Stromdaten geprüft.

## 8. Testlauferkennung

Datei:

```text
parsers/folder_loader.py
```

Ein Ordner kann mehrere Konfigurationen enthalten:

- Haupttest
- alternative Temperaturkonfiguration
- Single-Board-Test
- Systemcheck
- Unterordner mit weiteren Versuchen

Diese Dateien dürfen nicht zu einem falschen Testlauf zusammengeführt werden.

Der Loader gruppiert nach:

- Unterordner
- Testfamilie
- Zonenname
- Temperatur und Testparameter

Zonen A, B und C derselben Testfamilie können gemeinsam geladen werden.
Unterschiedliche Temperaturen oder Unterordner bleiben getrennte Testläufe.

Unterstützte Größen:

```text
1 Zone  × 8 Boards  = 8 Boards
3 Zonen × 8 Boards  = 24 Boards
```

## 9. Fehlerbehandlung

Parser sollen bei einer fehlerhaften Datei nicht die gesamte Analyse
abbrechen.

Beispiele:

- beschädigte JSON-Datei → Warnung
- fehlende MTPX-Datei → geplante Zeit fehlt
- ungültiger Ovenplan-Eintrag → Eintrag wird übersprungen
- fehlende DATA-Datei → Stresszeit bleibt `0`
- freie DUT-Bezeichnung → Board bleibt nutzbar

Warnungen werden im `TestRun` gesammelt und später in der Oberfläche
angezeigt.

## 10. Tests

Woche 2 besitzt automatisierte Tests für:

- Ovenplan und Zone
- HV-/MV-Erkennung
- freie DUT-Namen
- sichere MTPX-Berechnung
- DATA-Hardwareinformationen
- mehrere getrennte Testläufe
- verschachtelte Testordner
- drei Zonen mit 24 Boards
- Gruppierung täglicher Boarddateien

Testbefehl:

```bash
pytest -q
```

## 11. Ergebnis von Woche 2

Nach Woche 2 kann die Anwendung aus einem unbekannten Testordner automatisch
eine strukturierte Testbeschreibung erzeugen:

```text
Testlauf
├── geplante Testzeit
├── Ofentemperatur
├── Zone A
│   ├── Position 1
│   ├── Position 2
│   └── ...
├── Zone B
└── Zone C
```

Damit ist die Grundlage für Woche 3 vorhanden:

- Board-Logs einlesen
- TDMS-Stromdaten einlesen
- Fehler erkennen
- Temperatur-Glitches analysieren
- tatsächliche Nachbelastung über Stromabfall bestätigen
