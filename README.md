# DHTOL Analyzer

Projet d'apprentissage pour l'evaluation automatique de campagnes de test DHTOL.

## Etat actuel : semaine 2

Fondation et parseurs de fichiers termines :

- modeles de donnees communs
- modele de statut Vert/Jaune/Rouge
- duree de stress planifiee et journalisee
- calcul de la duree de post-stress
- valeurs de configuration centrales
- prise en charge de 1 a 3 zones avec jusqu'a 8 boards chacune
- configuration de test JSON et ovenplan
- detection automatique HV/MV via `f_MV`
- duree de test planifiee depuis MTPX
- duree de fonctionnement du board et version du firmware depuis DATA
- separation de plusieurs campagnes de test dans le meme dossier

Documentation :

- [Semaine 1 - Fondation](docs/week-01-foundation.md)
- [Semaine 2 - Parseurs de configuration et de metadonnees](docs/week-02-parsers.md)

## Logique de post-stress

```text
Duree de post-stress = max(0, duree de test planifiee - duree de stress journalisee)
```

Exemple issu d'une vraie campagne de test :

```text
Duree de test planifiee :       1001,000 h
Duree de stress journalisee :    640,327 h
Duree de post-stress :           360,673 h
```

L'analyse PSU/EL ulterieure doit confirmer si le DUT est vraiment reste sous
stress pendant cette periode.

## Plan mensuel

- Semaine 1 : modeles de donnees et configuration - termine
- Semaine 2 : parseurs JSON, MTPX et DATA - termine
- Semaine 3 : parseurs LOG/TDMS et analyse
- Semaine 4 : interface Streamlit, graphes et tests globaux

Les donnees brutes restent locales et ne sont pas envoyees grace a `.gitignore`.
