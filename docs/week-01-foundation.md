# Semaine 1 - Fondation : modèles de données légers pour les parseurs

## 1. Objectif de la semaine

La semaine 1 crée uniquement les objets Python communs dont les parseurs de la
semaine 2 ont réellement besoin.

Le premier état public doit rester petit :

```text
JSON / MTPX / DATA
        ↓
      Parseurs
        ↓
Zone, TempMode, OvenplanEntry, ParsedConfig, BoardMetadata
```

Sont volontairement exclus :

- interface Streamlit ;
- séries temporelles des logs board ;
- lecteur TDMS ;
- modèle de défaut/statut ;
- analyse des glitches de température ;
- analyse du courant PSU/EL.

Ces parties suivent plus tard, quand elles sont aussi utilisées par du vrai
code.

## 2. Pourquoi des dataclasses ?

Les parseurs ne doivent pas renvoyer des dictionnaires libres.

Dictionnaire libre :

```python
entry = {
    "zone": "A",
    "position": 1,
    "dut_name": "88_1_2",
}
```

Modèle structuré :

```python
entry = OvenplanEntry(
    controller_id=88,
    position=1,
    zone=Zone.A,
    dut_name="88_1_2",
    hw_target="01be8edd",
)
```

Avantages :

- les noms de champs sont visibles ;
- les types sont documentés ;
- les tests peuvent vérifier précisément le résultat ;
- le résultat du parseur reste stable ;
- l'analyse ultérieure n'a pas besoin de connaître la structure JSON brute.

## 3. Pourquoi des enums ?

Les enums limitent les valeurs autorisées.

```python
class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"
```

Ainsi, les parseurs ne stockent pas par erreur des valeurs comme `"zone-a"` ou
`"AA"`.

Enums actives :

| Enum | But |
|---|---|
| `Zone` | Zone du four A, B ou C |
| `TempMode` | Fonctionnement HV ou MV |

## 4. Controller ID et position

Les vrais noms DUT peuvent ressembler à ceci :

```text
88_1_2
```

Seul le premier nombre est lu comme controller ID :

```text
controller_id = 88
```

La position dans le four vient du champ ovenplan `Slot` :

```text
position = 1
```

Important :

```text
Controller ID != position du board
```

Dans l'exemple, le contrôleur `88` se trouve à la position `1`. Cette séparation
évite plus tard les mauvaises attributions de boards.

Les noms DUT libres restent autorisés :

```text
aa
bb
cc
```

Dans ce cas :

```text
controller_id = None
```

La zone, la position, le nom DUT et le hardware target restent tout de même
disponibles.

## 5. Modèles

### `OvenplanEntry`

Une entrée du JSON ovenplan :

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

Contenu complet d'une configuration de test JSON, dans la limite des besoins de
la semaine 2 :

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

`warnings` collecte les problèmes lisibles sans interrompre immédiatement toute
l'analyse.

### `BoardMetadata`

La semaine 2 ne stocke depuis `.data` que les valeurs actuellement utilisées :

```python
@dataclass
class BoardMetadata:
    log_stress_seconds: float = 0.0
    firmware_version: str = ""
    source_path: Optional[Path] = None
```

Non stockés :

- hostname ;
- adresse IP ;
- adresse MAC ;
- version hardware ;
- cycles.

Ces champs existent parfois dans `.data`, mais ne servent pas de base de
décision pour l'évaluation DHTOL actuelle.

## 6. Durée de stress planifiée et journalisée

La durée de test planifiée vient plus tard de MTPX :

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

La durée de stress journalisée du board vient de DATA :

```json
{
  "Test Info": {
    "Seconds": 2305178.5626702309
  }
}
```

Le post-stress mathématique reste documenté comme règle du projet :

```text
Durée de post-stress = max(0, durée de test planifiée - durée de stress journalisée)
```

Le code des semaines 1 et 2 stocke les deux valeurs brutes. La confirmation du
post-stress via les données de courant suit plus tard.

## 7. Protection des données brutes

Les dossiers de mesure peuvent être très volumineux. Les données brutes n'ont
pas leur place dans le repository.

`.gitignore` bloque donc :

```text
*.tdms
*.tdms_index
*.log
*.data
*.store
*.mtpx
```

GitHub contient uniquement le code source, les tests et la documentation.

## 8. Résultat de la semaine 1

Terminé :

- modèles de données légers pour les parseurs ;
- valeurs de zone claires A/B/C ;
- mode HV/MV sous forme d'enum ;
- controller ID et position de slot séparés ;
- `BoardMetadata` limité aux valeurs DATA utilisées ;
- protection des données brutes via `.gitignore`.

Pas encore inclus dans la semaine 1 :

- modèle de statut ;
- modèle de défaut ;
- modèle de séries temporelles `Measurement` ;
- modèles globaux `TestRun` et `ZoneData` ;
- configuration centrale d'analyse.
