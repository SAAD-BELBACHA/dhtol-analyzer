# Semaine 2 - Parseurs de configuration et de métadonnées

## 1. Objectif de la semaine

La semaine 2 relie de vrais fichiers DHTOL aux modèles de données légers de la
semaine 1.

Le code lit trois types de fichiers :

```text
JSON → configuration de test et ovenplan
MTPX → durée de test planifiée
DATA → durée de stress journalisée du board et version firmware
```

L'état public reste volontairement petit. Le code LOG, TDMS, Streamlit et
glitch ne fait pas encore partie de cet état GitHub.

## 2. Bibliothèques utilisées

Seulement la bibliothèque standard plus `pytest` pour les tests :

| Bibliothèque | Utilisation |
|---|---|
| `json` | charger les fichiers JSON, MTPX et DATA |
| `re` | chercher zone, ID DUT, `f_MV` et stop-time fallback |
| `pathlib.Path` | gérer les chemins de fichiers de manière portable |
| `dataclasses` | représenter les résultats des parseurs comme objets clairs |
| `enum` | valeurs fixes pour zone et mode de température |
| `ast` | évaluer sûrement les expressions mathématiques MTPX |
| `operator` | opérations autorisées `+`, `-`, `*`, `/` |
| `pytest` | tests automatisés |

`requirements.txt` contient donc seulement :

```text
pytest>=8.0
```

## 3. Configuration de test JSON

Fichier :

```text
parsers/config_json.py
```

Le parseur lit :

- nom du test ;
- zone ;
- liste des instruments ;
- ovenplan ;
- slot ou position ;
- nom DUT ;
- hardware target ;
- load board ;
- DUT board ;
- uC-FSM ;
- mode HV/MV via `f_MV`.

Exemple :

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

Résultat :

```text
test_name     = run_A_test
zone          = A
temp_mode     = MVoltage
controller_id = 88
position      = 1
dut_name      = 88_1_2
hw_target     = 01be8edd
```

### Noms DUT libres

Tous les tests n'utilisent pas des noms comme `88_1_2`.

Ceci est aussi valide :

```json
{
  "Zone": "A",
  "Slot": "2",
  "DUT": "aa",
  "HW Target": "target-aa"
}
```

Résultat :

```text
controller_id = None
position      = 2
dut_name      = aa
```

## 4. Détection HV et MV

Le mode se trouve dans le code du plan de test :

```lua
f_MV = false
```

Correspondance :

| Valeur | Mode |
|---|---|
| `f_MV = false` | `TempMode.HV` |
| `f_MV = true` | `TempMode.MV` |
| absent | `TempMode.HV` par défaut |

Le parseur parcourt les chaînes imbriquées dans `Testplans`. Il reste donc
indépendant de la profondeur exacte du code dans le JSON.

## 5. MTPX et durée de test planifiée

Fichier :

```text
parsers/mtpx.py
```

Contenu typique :

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

Sortie :

```text
planned_test_seconds = 3603600
```

### Pourquoi pas `eval()` ?

`templateValue` est du texte. Ceci serait dangereux :

```python
eval("1001*3600")
```

Le parseur utilise donc `ast` et autorise seulement :

- nombres ;
- parenthèses ;
- addition ;
- soustraction ;
- multiplication ;
- division.

Cet exemple est accepté :

```text
1001*3600
```

Cet exemple est refusé :

```text
__import__('os').system('echo no')
```

## 6. Fichiers DATA

Fichier :

```text
parsers/board_data.py
```

La semaine 2 stocke seulement :

- `Test Info.Seconds` ;
- dernière version firmware depuis `HW History[-1].HW Info.version.fw`.

Exemple :

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

Résultat :

```text
log_stress_seconds = 123.5
firmware_version   = 9.0
```

Volontairement non stockés :

- `Cycles` ;
- `hostname` ;
- `IP` ;
- `MAC` ;
- version hardware `hw`.

Raison : ces valeurs ne sont pas utilisées dans l'état actuel de l'analyse.
Elles pourront être réintroduites plus tard si une analyse en a vraiment
besoin.

## 7. Gestion des erreurs

Les parseurs ne doivent pas s'arrêter brutalement à cause d'un seul fichier
endommagé.

Comportement :

- fichier JSON endommagé → `ParsedConfig` vide plus avertissement ;
- fichier MTPX manquant ou endommagé → `None` ;
- fichier DATA manquant ou endommagé → `None` ;
- entrée ovenplan invalide → entrée ignorée ;
- nom DUT libre → valide, `controller_id = None`.

## 8. Tests

Fichier :

```text
tests/test_week_02_parsers.py
```

Les tests vérifient :

- ovenplan JSON ;
- zones A/B/C ;
- détection HV/MV ;
- noms DUT libres ;
- avertissement pour JSON endommagé ;
- calcul MTPX sûr ;
- refus d'une expression MTPX exécutable ;
- durée de stress DATA ;
- version firmware DATA ;
- suppression des champs DATA inutilisés dans `BoardMetadata`.

Commande de test :

```bash
pytest -q
```

## 9. Résultat de la semaine 2

Après la semaine 2, le code peut transformer des fichiers individuels de
configuration et de métadonnées en objets Python sûrs :

```text
JSON → ParsedConfig + OvenplanEntry
MTPX → durée de test planifiée en secondes
DATA → BoardMetadata avec durée de stress + firmware
```

Prochaines étapes :

- reconnaître les dossiers de test appartenant à la même campagne ;
- lire les logs board ;
- lire les données de courant TDMS ;
- détecter les défauts ;
- analyser les glitches de température ;
- construire l'interface Streamlit.
