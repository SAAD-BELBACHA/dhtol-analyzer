# Woche 1 - Fundament: schlanke Parser-Datenmodelle

## 1. Wochenziel

Woche 1 legt nur die gemeinsamen Python-Objekte an, die die Parser aus Woche 2
wirklich brauchen.

Der erste oeffentliche Stand soll klein bleiben:

```text
JSON / MTPX / DATA
        ↓
      Parser
        ↓
Zone, TempMode, OvenplanEntry, ParsedConfig, BoardMetadata
```

Nicht enthalten sind bewusst:

- Streamlit-Oberflaeche
- Board-Log-Zeitreihen
- TDMS-Leser
- Fehler-/Statusmodell
- Temperatur-Glitch-Analyse
- PSU-/EL-Stromauswertung

Diese Teile folgen spaeter, wenn sie auch durch echten Code benutzt werden.

## 2. Warum Dataclasses?

Parser sollen keine freien Dictionaries zurueckgeben.

Freies Dictionary:

```python
entry = {
    "zone": "A",
    "position": 1,
    "dut_name": "88_1_2",
}
```

Strukturiertes Modell:

```python
entry = OvenplanEntry(
    controller_id=88,
    position=1,
    zone=Zone.A,
    dut_name="88_1_2",
    hw_target="01be8edd",
)
```

Vorteile:

- Feldnamen sind sichtbar
- Typen sind dokumentiert
- Tests koennen gezielt pruefen
- Parser-Ergebnis bleibt stabil
- spaetere Analyse muss keine JSON-Rohstruktur kennen

## 3. Warum Enums?

Enums begrenzen erlaubte Werte.

```python
class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"
```

Dadurch speichern Parser nicht versehentlich Werte wie `"zone-a"` oder `"AA"`.

Aktive Enums:

| Enum | Zweck |
|---|---|
| `Zone` | Ofenzone A, B oder C |
| `TempMode` | HV- oder MV-Betrieb |

## 4. Controller-ID und Position

Echte DUT-Namen koennen so aussehen:

```text
88_1_2
```

Daraus wird nur die erste Zahl als Controller-ID gelesen:

```text
controller_id = 88
```

Die Ofenposition kommt aus dem Ovenplan-Feld `Slot`:

```text
position = 1
```

Wichtig:

```text
Controller-ID != Board-Position
```

Controller `88` steht im Beispiel auf Position `1`. Diese Trennung verhindert
spaeter falsche Board-Zuordnungen.

Freie DUT-Namen bleiben erlaubt:

```text
aa
bb
cc
```

Dann gilt:

```text
controller_id = None
```

Zone, Position, DUT-Name und Hardware-Target bleiben trotzdem vorhanden.

## 5. Modelle

### `OvenplanEntry`

Ein Eintrag aus dem JSON-Ovenplan:

```python
@dataclass
class OvenplanEntry:
    controller_id: Optional[int]
    position: int
    zone: Zone
    dut_name: str
    hw_target: str
    load_board: str = ""
    dut_board: str = ""
    uc_fsm: str = ""
```

### `ParsedConfig`

Gesamter Inhalt einer JSON-Testkonfiguration, soweit Woche 2 ihn braucht:

```python
@dataclass
class ParsedConfig:
    test_name: str
    zone: Optional[Zone]
    temp_mode: TempMode
    instruments: list[str] = field(default_factory=list)
    ovenplan_entries: list[OvenplanEntry] = field(default_factory=list)
    source_path: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
```

`warnings` sammelt lesbare Probleme, ohne die komplette Analyse sofort
abzubrechen.

### `BoardMetadata`

Woche 2 speichert aus `.data` nur Werte, die aktuell genutzt werden:

```python
@dataclass
class BoardMetadata:
    log_stress_seconds: float = 0.0
    firmware_version: str = ""
    source_path: Optional[Path] = None
```

Nicht gespeichert:

- Hostname
- IP-Adresse
- MAC-Adresse
- Hardwareversion
- Zyklen

Diese Felder stehen teilweise in `.data`, sind aber fuer die aktuelle
DHTOL-Auswertung keine Entscheidungsbasis.

## 6. Geplante und geloggte Stresszeit

Die geplante Testzeit kommt spaeter aus MTPX:

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

Die geloggte Board-Stresszeit kommt aus DATA:

```json
{
  "Test Info": {
    "Seconds": 2305178.5626702309
  }
}
```

Rechnerische Nachbelastung bleibt als Projektregel dokumentiert:

```text
Nachbelastungszeit = max(0, geplante Testzeit - geloggte Stresszeit)
```

Der Code in Woche 1/2 speichert die beiden Rohwerte. Die bestaetigte
Nachbelastung ueber Stromdaten folgt spaeter.

## 7. Rohdatenschutz

Messordner koennen sehr gross sein. Rohdaten gehoeren nicht ins Repository.

`.gitignore` blockiert deshalb:

```text
*.tdms
*.tdms_index
*.log
*.data
*.store
*.mtpx
```

GitHub enthaelt nur Quellcode, Tests und Dokumentation.

## 8. Ergebnis Woche 1

Fertig:

- schlanke Parser-Datenmodelle
- klare Zonenwerte A/B/C
- HV-/MV-Modus als Enum
- getrennte Controller-ID und Slot-Position
- BoardMetadata nur mit genutzten DATA-Werten
- Rohdatenschutz ueber `.gitignore`

Noch nicht Teil von Woche 1:

- Statusmodell
- Fault-Modell
- Measurement-Zeitreihenmodell
- TestRun-/ZoneData-Gesamtmodell
- zentrale Analyse-Konfiguration
