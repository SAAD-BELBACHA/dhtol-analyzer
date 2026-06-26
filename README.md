# DHTOL Analyzer

Projet d'apprentissage pour l'évaluation automatique de campagnes de test
DHTOL.

## État actuel : semaine 2

La fondation et les parseurs de fichiers sont terminés :

- modèles de données légers pour les résultats des parseurs ;
- durée de stress planifiée et durée de stress journalisée ;
- logique de post-stress mathématique documentée ;
- prise en charge des zones A, B et C ;
- configuration de test JSON et ovenplan ;
- détection automatique HV/MV via `f_MV` ;
- durée de test planifiée depuis MTPX ;
- durée de fonctionnement du board et version du firmware depuis DATA.

Documentation :

- [Semaine 1 - Fondation](docs/week-01-foundation.md)
- [Semaine 2 - Parseurs de configuration et de métadonnées](docs/week-02-parsers.md)

## Logique de post-stress

```text
Durée de post-stress = max(0, durée de test planifiée - durée de stress journalisée)
```

Exemple issu d'une vraie campagne de test :

```text
Durée de test planifiée :       1001,000 h
Durée de stress journalisée :    640,327 h
Durée de post-stress :           360,673 h
```

L'analyse PSU/EL ultérieure doit confirmer si le DUT est vraiment resté sous
stress pendant cette période.

## Plan mensuel

- Semaine 1 : modèles de données légers pour les parseurs - terminé
- Semaine 2 : parseurs JSON, MTPX et DATA - terminé
- Semaine 3 : parseurs LOG/TDMS et analyse
- Semaine 4 : interface Streamlit, graphes et tests globaux

Les données brutes restent locales et ne sont pas envoyées grâce à `.gitignore`.
