# Semaine 2 - Parseurs de configuration et de metadonnees

## 1. Objectif de la semaine

La semaine 2 relie de vrais fichiers DHTOL aux modeles de donnees de la
semaine 1.

L'application doit detecter automatiquement :

```text
Quels boards appartiennent au test ?
Quelle zone et quelle position possede chaque board ?
Le test tourne-t-il en mode HV ou MV ?
Combien de temps le test etait-il planifie ?
Quelle duree de stress chaque board a-t-il stockee ?
Quelle version de firmware a ete utilisee ?
```

Chemin de traitement :

```text
JSON + MTPX + DATA
        ↓
      Parseurs
        ↓
TestRun, ZoneData, Board et BoardMetadata
```

## 2. Configuration de test JSON

Fichier :

```text
parsers/config_json.py
```

Le parseur JSON lit :

- nom du test
- zone
- ovenplan
- slot ou position
- nom DUT
- hardware target
- load board et DUT board
- mode de temperature

Exemple :

```json
{
  "Zone": "A",
  "Slot": "1",
  "DUT": "88_1_2",
  "HW Target": "01be8edd"
}
```

Resultat :

```text
controller_id = 88
zone          = A
position      = 1
dut_name      = 88_1_2
hw_target     = 01be8edd
```

L'ID controleur et la position restent separes. Le controleur `88` peut etre a
la position `1`. Dans des systemes de test futurs, d'autres zones et d'autres
IDs de controleur pourront etre utilises.

## 3. Noms DUT libres

Tous les tests n'utilisent pas un nom comme :

```text
58_1_2
```

Le dossier d'exemple `Same LOT DUTs` utilise :

```text
aa
bb
cc
dd
```

Ces noms sont aussi valides. Si aucune ID controleur numerique n'est contenue
dans le nom DUT :

```text
controller_id = None
```

Zone, position, nom DUT et hardware target restent tout de meme disponibles.
Dans l'interface, l'ID controleur manquante apparait comme `—`.

## 4. Detection HV et MV

Le mode est lu depuis le code du plan de test :

```lua
f_MV = false
```

Correspondance :

| Valeur config | Mode | T0 | T1 |
|---|---|---|---|
| `f_MV = false` | HV | Interrupteur low-side | Interrupteur high-side |
| `f_MV = true` | MV | Interrupteur low-side | DUT board |

Le fichier log possede les memes colonnes `t0` et `t1` dans les deux modes.
Seule la signification physique de `t1` change.

Le parseur stocke donc :

```python
TempMode.HV
```

ou :

```python
TempMode.MV
```

La detection des glitches peut continuer a travailler sur les colonnes brutes.
Les diagrammes utiliseront plus tard le mode pour choisir le bon libelle.

## 5. MTPX et duree de test planifiee

Fichier :

```text
parsers/mtpx.py
```

La duree de test planifiee se trouve typiquement dans le template :

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

Le parseur evalue uniquement des expressions mathematiques sures :

- addition
- soustraction
- multiplication
- division
- nombres positifs et negatifs
- parentheses

Aucun code Python arbitraire n'est execute.

Exemple :

```text
1001 x 3600 = 3.603.600 secondes
```

Cela correspond a :

```text
1001 heures
```

## 6. Fichiers DATA

Fichier :

```text
parsers/board_data.py
```

Chaque board possede un fichier `.data` avec des informations de test et de
firmware.

Valeurs lues :

- `Test Info.Seconds`
- version du firmware

Exemple :

```json
{
  "Test Info": {
    "Seconds": 2305183.4
  },
  "HW History": [
    {
      "HW Info": {
        "version": {
          "fw": "9.0"
        }
      }
    }
  ]
}
```

Resultat :

```text
Duree de stress journalisee = Test Info.Seconds
Version du firmware         = HW History[-1].HW Info.version.fw
```

Le hostname, l'adresse IP, l'adresse MAC, la version hardware et les cycles ne
sont pas stockes. Ces valeurs ne sont pas une base de decision pour l'analyse
DHTOL actuelle.

Les secondes stockees sont utilisees comme duree de stress journalisee :

```text
Duree de stress journalisee = Test Info.Seconds
```

Les valeurs negatives ou invalides sont remplacees par `0`.

## 7. Duree de post-stress

Avec la duree planifiee depuis MTPX et la duree de stress journalisee depuis
DATA, le post-stress mathematique peut etre determine :

```text
Post-stress mathematique
= max(0, duree de test planifiee - duree de stress journalisee)
```

Exemple :

```text
Planifie :       10 heures
Test journalise : 8 heures
Difference :      2 heures
```

Cette difference est d'abord seulement mathematique. Si le board a vraiment
continue a etre alimente apres le dernier log board, cela sera verifie plus
tard avec les donnees de courant PSU/EL ou host.

## 8. Detection des campagnes de test

Fichier :

```text
parsers/folder_loader.py
```

Un dossier peut contenir plusieurs configurations :

- test principal
- configuration de temperature alternative
- test single-board
- systemcheck
- sous-dossiers avec d'autres essais

Ces fichiers ne doivent pas etre fusionnes dans une mauvaise campagne de test.

Le loader groupe selon :

- sous-dossier
- famille de test
- nom de zone
- temperature et parametres de test

Les zones A, B et C de la meme famille de test peuvent etre chargees ensemble.
Des temperatures differentes ou des sous-dossiers differents restent des
campagnes de test separees.

Tailles prises en charge :

```text
1 zone  x 8 boards  = 8 boards
3 zones x 8 boards  = 24 boards
```

## 9. Gestion des erreurs

Les parseurs ne doivent pas interrompre toute l'analyse a cause d'un seul
fichier defectueux.

Exemples :

- fichier JSON endommage -> avertissement
- fichier MTPX manquant -> duree planifiee absente
- entree ovenplan invalide -> entree ignoree
- fichier DATA manquant -> duree de stress reste `0`
- designation DUT libre -> board reste utilisable

Les avertissements sont collectes dans le `TestRun`, puis affiches plus tard
dans l'interface.

## 10. Tests

La semaine 2 possede des tests automatises pour :

- ovenplan et zone
- detection HV/MV
- noms DUT libres
- calcul MTPX securise
- informations hardware DATA
- plusieurs campagnes de test separees
- dossiers de test imbriques
- trois zones avec 24 boards
- groupement de fichiers board quotidiens

Commande de test :

```bash
pytest -q
```

## 11. Resultat de la semaine 2

Apres la semaine 2, l'application peut generer automatiquement une description
structuree de test depuis un dossier de test inconnu :

```text
Campagne de test
├── duree de test planifiee
├── temperature du four
├── Zone A
│   ├── Position 1
│   ├── Position 2
│   └── ...
├── Zone B
└── Zone C
```

C'est la base pour la semaine 3 :

- lire les logs board
- lire les donnees de courant depuis les logs host
- detecter les erreurs
- analyser les glitches de temperature
- confirmer le vrai post-stress via chute de courant
