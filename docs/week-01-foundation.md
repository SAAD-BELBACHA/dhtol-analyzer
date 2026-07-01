# Semaine 1 - Fondation : modeles de donnees et configuration

## 1. Objectif de la semaine

Pendant la semaine 1, aucun fichier n'a encore ete parse et aucune interface
utilisateur n'a encore ete construite. La premiere etape a ete de creer le
langage commun du projet.

Tous les modules futurs ont besoin des memes notions :

```text
Fichiers de mesure -> Parseurs -> Modeles de donnees -> Analyse -> Visualisation
```

Les parseurs produisent des objets structures. Les analyses lisent et evaluent
ces objets. L'interface affiche leurs valeurs.

Sans modeles de donnees communs, les parseurs, l'analyse et l'interface
utiliseraient leurs propres noms de champs et leurs propres structures. Cela
provoque vite des fautes de frappe, des significations differentes et des
erreurs difficiles a trouver.

## 2. Enseignements tires de vraies donnees de test

Le dossier d'exemple contient :

- une zone : Zone A
- huit positions de board : 1-8
- IDs de controleur : 88-95
- duree de test planifiee : `1001*3600` secondes
- durees de fonctionnement des boards d'environ 640,33 heures

Correction importante du modele :

```text
ID controleur != position globale du board
```

Le controleur `88` n'est pas le "board 88 sur 24". Dans le test d'exemple, il
se trouve a la position 1 de la zone A.

Le modele stocke donc les valeurs separement :

```text
controller_id = 88
zone          = A
position      = 1
dut_name      = 88_1_2
```

Cette separation prend en charge le test actuel avec huit boards, mais aussi
des dossiers de test futurs avec trois zones et 24 boards au total.

## 3. Pourquoi `dataclass` ?

Une dataclass est un plan pour des donnees structurees.

Au lieu d'un dictionnaire libre :

```python
board = {
    "controller_id": 88,
    "position": 1,
}
```

nous utilisons un objet defini :

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

Avantages :

- les champs autorises sont visibles
- les types de donnees attendus sont documentes
- l'editeur peut aider pendant l'ecriture
- les fautes de frappe dans les noms de champs sont reperees plus vite
- les objets sont plus faciles a tester

## 4. Pourquoi `Enum` ?

Les enums definissent des valeurs autorisees fixes.

Exemple :

```python
class Zone(Enum):
    A = "A"
    B = "B"
    C = "C"
```

Sans enum, `"AA"` ou `"zone-a"` pourraient etre stockes par erreur. Avec
`Zone.A`, la signification reste claire.

Enums utilisees :

| Enum | But |
|---|---|
| `FaultType` | OC, OV, OT, Network, GERR |
| `Zone` | A, B ou C |
| `Status` | Vert, Jaune ou Rouge |
| `TempMode` | HVoltage ou MVoltage |

## 5. Modele de mesure

`Measurement` decrit exactement une ligne de mesure issue d'un log de board.

Valeurs stockees :

- horodatage
- tension d'entree
- courant du board
- tension differentielle de gate
- tension de sortie DUT
- tension de sortie du board
- tension low-side
- temperatures T0 et T1
- flags de glitch pour les deux capteurs de temperature

Les valeurs de glitch ne seront pas supprimees plus tard. La valeur originale
reste conservee et recoit seulement un flag :

```python
t1_glitch = True
```

Les donnees brutes restent ainsi tracables pour le diagnostic.

## 6. Modele d'erreur

`Fault` stocke :

- type d'erreur
- instant
- decision vrai/faux
- auteur de la decision

`is_real` possede trois etats possibles :

```text
True  -> vraie defaillance DUT
False -> erreur apparente
None  -> decision encore ouverte
```

Le troisieme etat est important. Pour OC, OV, OT et GERR, un engineer decide
plus tard. `False` ne doit pas etre utilise comme valeur par defaut, car ce
serait deja une decision metier.

## 7. Modele de statut

Le statut d'un board n'est pas stocke separement. Il est calcule a partir des
erreurs et des glitches :

```text
Rouge -> au moins une vraie erreur confirmee
Jaune -> erreur ou glitch present, mais aucune vraie erreur confirmee
Vert  -> aucune erreur et aucun glitch
```

Exemples :

```text
Board normal                                  -> Vert
Capteur de temperature avec valeurs fausses   -> Jaune
Erreur OC, decision encore ouverte            -> Jaune
OC confirme comme vraie defaillance DUT       -> Rouge
```

Le calcul via `@property` evite les statuts obsoletes. Quand une decision
d'erreur change, le statut change directement lors du prochain acces.

## 8. Listes avec `default_factory`

Chaque board a besoin de ses propres listes d'erreurs et de glitches :

```python
faults: list[Fault] = field(default_factory=list)
```

`default_factory=list` cree une nouvelle liste pour chaque board.

Une liste standard partagee pourrait faire apparaitre par erreur les erreurs du
board 88 aussi sur le board 89.

## 9. Zones et campagne de test

`ZoneData` regroupe :

- Zone A, B ou C
- boards de cette zone
- plus tard courant total de zone depuis PSU/EL

`TestRun` decrit toute la campagne :

- nom du test
- duree de test planifiee
- temperature du four
- courant nominal
- zones presentes

Les zones sont stockees sous forme de liste :

```python
zones: list[ZoneData]
```

Le modele reste donc dynamique :

```text
Dossier d'exemple : 1 zone x 8 boards  = 8 boards
Configuration complete : 3 zones x 8 boards = 24 boards
```

`all_boards` produit au besoin une liste plate de tous les boards de toutes les
zones.

## 10. Duree de test planifiee

La recherche dans de vrais fichiers a donne :

```json
{
  "templateName": "stop_time",
  "templateValue": "1001*3600"
}
```

Cette valeur se trouve dans le fichier MTPX.

```text
1001 x 3600 = 3.603.600 secondes
```

Le fichier `.data` contient en revanche la duree de stress journalisee du
board :

```json
{
  "Test Info": {
    "Seconds": 2305178.5626702309
  }
}
```

Pour le board 88 :

```text
2.305.178,563 secondes = 640,327 heures
```

## 11. Logique de post-stress

Definition de ce projet :

```text
Duree de post-stress =
max(0, duree de test planifiee - duree de stress journalisee)
```

Calcul pour le board 88 :

```text
Duree de test planifiee :        3.603.600,000 s
Duree de stress journalisee :   -2.305.178,563 s
Post-stress :                    1.298.421,437 s
                                = 360,673 h
```

`max(0, ...)` evite les durees negatives si la duree de stress journalisee est
superieure a la duree de test planifiee pour des raisons techniques.

Point metier important :

Ce calcul fournit un ecart purement mathematique. Il ne prouve pas encore que
le DUT est vraiment reste sous stress pendant tout cet ecart. L'analyse PSU/EL
ulterieure doit verifier l'evolution du courant.

## 12. Configuration centrale

`config.py` rassemble les regles fixes a un seul endroit.

Exemple :

```python
TEMP_PHYS_MAX_C = 250.0
```

C'est plus comprehensible qu'un nombre cache :

```python
if temperature > 250:
```

La configuration contient :

- limites physiques de temperature
- tolerance provisoire par rapport a la consigne du four
- vitesse maximale de variation de temperature
- duree pour la detection de capteur mort
- seuils pour chute de courant
- fenetre temporelle pour correlation d'evenements
- huit boards par zone
- maximum trois zones
- hypothese que les boards peuvent se reconnecter

Beaucoup de seuils sont des valeurs initiales. De vraies donnees de mesure
doivent les confirmer ou les corriger dans les semaines suivantes.

## 13. Protection des donnees brutes dans le repository

Le dossier de mesure fait environ 38 Go. Les fichiers TDMS, LOG, DATA, STORE et
MTPX n'ont pas leur place dans Git. TDMS reste ignore comme donnee brute, mais
n'est plus lu par l'application.

`.gitignore` empeche un upload accidentel :

```text
*.tdms
*.tdms_index
*.log
*.data
*.store
*.mtpx
```

Le repository contient seulement le code source et la documentation.

## 14. Resultat de la semaine 1

Termine :

- types de base securises
- modeles de donnees
- logique de statut
- formule de post-stress
- configuration centrale
- architecture pour 8 ou 24 boards
- protection des donnees brutes

Pas encore inclus dans l'etat public de la semaine :

- parseurs de fichiers
- lecteur des courants host-log
- analyse des glitches
- attribution du courant
- interface Streamlit

Ces parties suivent progressivement pendant les semaines 2-4.
