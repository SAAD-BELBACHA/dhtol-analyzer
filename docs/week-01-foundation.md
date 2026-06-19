# Woche 1 – Fundament: Datenmodelle und Konfiguration

## 1. Wochenziel

In Woche 1 wurde noch keine Datei geparst und noch keine Benutzeroberfläche
gebaut. Zuerst entstand die gemeinsame Sprache des Projekts.

Alle späteren Module benötigen dieselben Begriffe:

```text
Messdateien → Parser → Datenmodelle → Analyse → Visualisierung
```

Parser erzeugen strukturierte Objekte. Analysen lesen und bewerten diese
Objekte. Die Oberfläche zeigt ihre Werte an.

Ohne gemeinsame Datenmodelle würden Parser, Analyse und Oberfläche eigene
Feldnamen und Strukturen verwenden. Das führt schnell zu Tippfehlern,
unterschiedlichen Bedeutungen und schwer auffindbaren Fehlern.

## 2. Erkenntnisse aus echten Testdaten

Der Beispielordner enthält:

- eine Zone: Zone A
- acht Board-Positionen: 1–8
- Controller-IDs: 88–95
- geplante Testzeit: `1001*3600` Sekunden
- Board-Laufzeiten von ungefähr 640,33 Stunden

Wichtige Modellkorrektur:

```text
Controller-ID ≠ globale Board-Position
```

Controller `88` ist nicht „Board 88 von 24“. Er steht im Beispieltest auf
Position 1 der Zone A.

Darum speichert das Modell getrennt:

```text
controller_id = 88
zone          = A
position      = 1
dut_name      = 88_1_2
```

Diese Trennung unterstützt sowohl den aktuellen Test mit acht Boards als auch
spätere Testordner mit drei Zonen und insgesamt 24 Boards.

## 3. Warum `dataclass`?

Eine Dataclass ist ein Bauplan für strukturierte Daten.

Statt eines freien Dictionaries:

```python
board = {
    "controller_id": 88,
    "position": 1,
}
```

verwenden wir ein definiertes Objekt:

```python
board = Board(
    controller_id=88,
    zone=Zone.A,
    position=1,
    dut_name="88_1_2",
    hw_target="01be8edd",
    nenn_strom_a=2.0,
)
```

Vorteile:

- erlaubte Felder sind sichtbar
- erwartete Datentypen sind dokumentiert
- Editor kann beim Schreiben helfen
- Tippfehler in Feldnamen werden schneller erkannt
- Objekte lassen sich leichter testen

## 4. Warum `Enum`?

Enums definieren feste erlaubte Werte.

Beispiel:

```python
class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"
```

Ohne Enum könnte versehentlich `"AA"` oder `"zone-a"` gespeichert werden.
Mit `Zone.A` bleibt Bedeutung eindeutig.

Verwendete Enums:

| Enum | Zweck |
|---|---|
| `FaultType` | OC, OV, OT, Network, GERR |
| `Zone` | A, B oder C |
| `Status` | Grün, Gelb oder Rot |
| `TempMode` | HVoltage oder MVoltage |

## 5. Messmodell

`Measurement` beschreibt genau eine Messzeile aus einem Board-Log.

Gespeichert werden:

- Zeitstempel
- Eingangsspannung
- Board-Strom
- Gate-Differenzspannung
- DUT-Ausgangsspannung
- Board-Ausgangsspannung
- Low-Side-Spannung
- Temperaturen T0 und T1
- Glitch-Flags für beide Temperatursensoren

Glitch-Werte werden später nicht gelöscht. Originalwert bleibt erhalten und
erhält nur ein Flag:

```python
t1_glitch = True
```

Damit bleiben Rohdaten für Diagnose nachvollziehbar.

## 6. Fehlermodell

`Fault` speichert:

- Fehlertyp
- Zeitpunkt
- Echt/Fake-Entscheidung
- wer Entscheidung getroffen hat

`is_real` besitzt drei mögliche Zustände:

```text
True  → echter DUT-Ausfall
False → Scheinfehler
None  → Entscheidung noch offen
```

Der dritte Zustand ist wichtig. Bei OC, OV, OT und GERR entscheidet später ein
Engineer. `False` dürfte nicht als Standard verwendet werden, weil das bereits
eine fachliche Entscheidung wäre.

## 7. Statusmodell

Board-Status wird nicht separat gespeichert. Er wird aus Fehlern und Glitches
berechnet:

```text
Rot   → mindestens ein bestätigter echter Fehler
Gelb  → Fehler oder Glitch vorhanden, aber kein echter Fehler bestätigt
Grün  → kein Fehler und kein Glitch
```

Beispiele:

```text
Board normal                              → Grün
Temperatursensor liefert falsche Werte    → Gelb
OC-Fehler, Entscheidung noch offen        → Gelb
OC als echter DUT-Ausfall bestätigt       → Rot
```

Berechnung über `@property` verhindert veraltete Statuswerte. Wenn sich eine
Fehlerentscheidung ändert, ändert sich Status beim nächsten Zugriff direkt mit.

## 8. Listen mit `default_factory`

Jedes Board braucht eigene Fehler- und Glitch-Listen:

```python
faults: list[Fault] = field(default_factory=list)
```

`default_factory=list` erzeugt für jedes Board eine neue Liste.

Eine gemeinsame Standardliste könnte dazu führen, dass Fehler von Board 88
versehentlich auch bei Board 89 erscheinen.

## 9. Zonen und Testlauf

`ZoneData` gruppiert:

- Zone A, B oder C
- Boards dieser Zone
- später Zonen-Gesamtstrom aus PSU/EL

`TestRun` beschreibt gesamten Test:

- Testname
- geplante Testzeit
- Ofentemperatur
- Nennstrom
- vorhandene Zonen

Zonen werden als Liste gespeichert:

```python
zones: list[ZoneData]
```

Darum funktioniert Modell dynamisch:

```text
Beispielordner: 1 Zone × 8 Boards  = 8 Boards
Voller Aufbau:  3 Zonen × 8 Boards = 24 Boards
```

`all_boards` erzeugt bei Bedarf eine flache Liste aller Boards aus allen Zonen.

## 10. Geplante Testzeit

Suche in echten Dateien ergab:

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

Dieser Wert liegt in der MTPX-Datei.

```text
1001 × 3600 = 3.603.600 Sekunden
```

Die `.data`-Datei enthält dagegen geloggte Board-Stresszeit:

```json
{
  "Test Info": {
    "Seconds": 2305178.5626702309
  }
}
```

Für Board 88:

```text
2.305.178,563 Sekunden = 640,327 Stunden
```

## 11. Nachbelastungslogik

Definition dieses Projekts:

```text
Nachbelastungszeit =
max(0, geplante Testzeit − Log-Stresszeit)
```

Rechnung Board 88:

```text
Geplante Testzeit:  3.603.600,000 s
Log-Stresszeit:    −2.305.178,563 s
Nachbelastung:      1.298.421,437 s
                   = 360,673 h
```

`max(0, ...)` verhindert negative Zeiten, falls Log-Stresszeit aus technischen
Gründen größer als geplante Testzeit ist.

Fachlich wichtig:

Diese Rechnung liefert rechnerische Lücke. Sie beweist noch nicht, dass DUT
während gesamter Lücke wirklich weiter gestresst wurde. Spätere PSU/EL-Analyse
muss Stromverlauf prüfen.

## 12. Zentrale Konfiguration

`config.py` sammelt feste Regeln an einem Ort.

Beispiel:

```python
TEMP_PHYS_MAX_C = 250.0
```

Das ist verständlicher als versteckte Zahl:

```python
if temperature > 250:
```

Konfiguration enthält:

- physikalische Temperaturgrenzen
- vorläufige Toleranz zum Ofensollwert
- maximale Temperaturänderungsrate
- Dauer für Sensor-Tod-Erkennung
- Schwellen für Stromabfall
- Zeitfenster für Ereigniskorrelation
- acht Boards pro Zone
- maximal drei Zonen
- Annahme, dass Boards reconnecten können

Viele Schwellen sind Startwerte. Echte Messdaten müssen sie in späteren Wochen
bestätigen oder korrigieren.

## 13. Rohdatenschutz im Repository

Messordner ist ungefähr 38 GB groß. TDMS-, LOG-, DATA-, STORE- und MTPX-Dateien
gehören nicht in Git.

`.gitignore` verhindert versehentlichen Upload:

```text
*.tdms
*.tdms_index
*.log
*.data
*.store
*.mtpx
```

Repository enthält nur Quellcode und Dokumentation.

## 14. Ergebnis Woche 1

Fertig:

- sichere Grundtypen
- Datenmodelle
- Statuslogik
- Nachbelastungsformel
- zentrale Konfiguration
- Architektur für 8 oder 24 Boards
- Rohdatenschutz

Noch nicht Teil des öffentlichen Wochenstands:

- Dateiparser
- TDMS-Leser
- Glitch-Analyse
- Stromattribution
- Streamlit-Oberfläche

Diese Teile folgen schrittweise in Woche 2–4.
