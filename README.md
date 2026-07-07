# Courir dans un air respirable

Pipeline lakehouse complet sur la qualite de l'air : ingestion de l'API publique
[Sensor.Community](https://sensor.community) toutes les 15 minutes, zones bronze, silver
avec quarantaine et gold en etoile, orchestration Airflow en TaskFlow, dashboard Metabase.

La question metier : ou et a quel moment de la journee un coureur peut il s'entrainer en
Ile de France en respirant un air conforme a la recommandation OMS (PM2.5 sous 15 ug/m3),
et quelles zones ou creneaux faut il eviter cette semaine ?

Le detail du cadrage est dans [docs/cadrage_metier.md](docs/cadrage_metier.md), la conception
(architecture, pipeline, etoile, regles qualite) dans [docs/conception.md](docs/conception.md).

## Livrables demandes et ou les trouver

| Livrable | Emplacement |
|---|---|
| Document de conception | [docs/conception.md](docs/conception.md) |
| Environnement fonctionnel | [docker-compose.yml](docker-compose.yml), demarrage ci dessous |
| Demonstration des 3 chemins du DAG | procedure ci dessous, captures dans [docs/captures/](docs/captures/) |
| Requetes SQL de verification d'idempotence | [sql/verification_idempotence.sql](sql/verification_idempotence.sql) |
| Dashboard Metabase | procedure de connexion ci dessous, requetes dans [sql/metabase_questions.sql](sql/metabase_questions.sql) |
| Note de cadrage metier | [docs/cadrage_metier.md](docs/cadrage_metier.md) |

## Prerequis

- Docker Desktop (ou docker engine + compose v2), 4 Go de memoire minimum alloues
- les ports 8080 (Airflow), 3000 (Metabase), 9000 et 9001 (MinIO), 5433 (Postgres metier) libres
- une connexion internet (API publique et installation des dependances python au premier demarrage)

## Demarrage

```bash
docker compose up airflow-init
docker compose up -d
```

Le premier demarrage telecharge les images et installe quelques dependances python dans les
conteneurs Airflow, comptez quelques minutes. Ensuite :

| Service | URL | Identifiants |
|---|---|---|
| Airflow | http://localhost:8080 | airflow / airflow |
| Metabase | http://localhost:3000 | creation du compte au premier acces |
| Console MinIO | http://localhost:9001 | qualite_air / qualite_air_minio |
| Postgres metier | localhost:5433 | qualite_air / qualite_air, base qualite_air |

## Premiere execution

1. Ouvrir Airflow, activer le DAG `qualite_air_api_15min_ingestion` (bouton pause a gauche).
2. Il se declenche toutes les 15 minutes, ou immediatement avec le bouton trigger.
3. Suivre le run dans la vue graph : sensor, fetch, archivage bronze et transformation en
   parallele, controle qualite, branchement, chargement gold, bilan.
4. Laisser tourner : chaque run ajoute une fenetre de mesures, le dashboard gagne en
   profondeur au fil des heures.

## Demonstration des trois chemins

Chemin nominal, rien a changer :

1. Trigger manuel du DAG, tout passe au vert.
2. La tache `log_quality_alert` apparait skippee, c'est le comportement normal du branchement.
3. Verifier le chargement : `docker compose exec postgres-metier psql -U qualite_air -d qualite_air -c "SELECT count(*) FROM gold.fait_mesure_air;"`

Chemin echec qualite, le DAG reste vert et la donnee part en quarantaine :

1. Dans Airflow, menu Admin puis Variables, passer `qualite_air_pm_max` de 999 a `1`
   (presque toutes les mesures depassent 1 ug/m3, la regle exactitude les rejette).
2. Trigger le DAG. Le taux de conformite tombe sous le seuil de 50, le branchement part
   vers `log_quality_alert`, `load_qualite_air_to_gold` est skippee, le DAG finit vert.
3. Constater la quarantaine dans la console MinIO, bucket silver, prefixe
   `qualite_air/quarantaine/`, et les compteurs par regle :
   `docker compose exec postgres-metier psql -U qualite_air -d qualite_air -c "SELECT regle, nb_rejets, taux_conformite FROM meta.quality_log ORDER BY cree_le DESC LIMIT 5;"`
4. Remettre `qualite_air_pm_max` a `999`.

Chemin echec technique, le DAG passe rouge :

1. Dans Admin puis Variables, remplacer `qualite_air_api_url` par
   `https://api-inexistante.exemple.invalid/airrohr/v1/filter/country=FR`.
2. Trigger le DAG. Le sensor ne recoit jamais de reponse, il echoue apres son timeout de
   180 secondes, le DAG finit rouge.
3. Remettre l'URL d'origine :
   `https://data.sensor.community/airrohr/v1/filter/country=FR`.

Remarque : relancer `docker compose up -d` reexecute l'init et remet les variables aux
valeurs par defaut, pratique pour repartir propre apres les demos.

## Verification de l'idempotence

Les requetes commentees sont dans [sql/verification_idempotence.sql](sql/verification_idempotence.sql) :

```bash
docker compose exec postgres-metier psql -U qualite_air -d qualite_air -f /sql/verification_idempotence.sql
```

Procedure de preuve : noter le count de `gold.fait_mesure_air`, puis dans Airflow ouvrir le
dernier run, tache `load_qualite_air_to_gold`, bouton clear (elle se rejoue sur le meme lot
silver), et repasser les requetes. Le count est identique, les requetes de doublons rendent
zero ligne, et dans `meta.ingestion_log` le rejeu montre `nb_inseres_gold` a 0 avec tout le
lot en `nb_ignores_gold`.

## Dashboard Metabase

1. Ouvrir http://localhost:3000, creer le compte administrateur.
2. Ajouter la base de donnees : type PostgreSQL, hote `postgres-metier`, port `5432`,
   base `qualite_air`, utilisateur `qualite_air`, mot de passe `qualite_air`.
3. Creer trois questions en SQL natif avec les requetes de
   [sql/metabase_questions.sql](sql/metabase_questions.sql) :
   la carte des zones (grid map sur latitude, longitude, couleur selon pm25_moyen),
   la heatmap heure par jour (tableau croise avec mise en forme conditionnelle),
   les indicateurs (cartes number : part au dessus du seuil OMS, meilleure heure, capteurs actifs).
4. Les assembler dans un dashboard "Courir dans un air respirable", chaque carte titree.

Il faut laisser le pipeline tourner quelques heures pour que la heatmap horaire ait du relief,
la carte et les indicateurs parlent des le premier run.

## Arborescence

```
quality_air_data/
    docker-compose.yml          l'environnement complet, adapte du compose officiel airflow 3.3.0
    dags/
        qualite_air_api_15min_ingestion.py    le dag taskflow, le quoi et le quand
    include/qualite_air/        le comment, testable sans airflow
        extract.py              appel de l'api
        transform.py            normalisation, une ligne par polluant
        quality.py              les cinq regles, motifs de rejet
        load.py                 dimensions puis faits, on conflict do nothing
        stockage.py             client minio, bronze json et silver parquet
        bdd.py                  connexion postgres et logs meta
    sql/
        init/                   schemas, etoile, logs, seed, executes au premier demarrage
        verification_idempotence.sql
        metabase_questions.sql
    docs/
        cadrage_metier.md       partie 1 de l'enonce
        conception.md           partie 3, produite avant le code
        captures/               les captures des trois chemins
```

## Variables Airflow

Posees par `airflow-init`, modifiables dans Admin puis Variables :

| Variable | Defaut | Role |
|---|---|---|
| qualite_air_api_url | https://data.sensor.community/airrohr/v1/filter/country=FR | source de donnees |
| conformite_seuil_pct | 50 | seuil du branchement qualite |
| qualite_air_pm_max | 999 | borne haute de la regle exactitude, le SDS011 sature a 999.9 |
| qualite_air_fraicheur_max_minutes | 60 | age maximal d'un releve pour la regle fraicheur |

## Depannage

- Port deja pris : liberer 8080, 3000, 9000, 9001 ou 5433, ou changer le mapping dans le compose.
- Les conteneurs airflow redemarrent en boucle au premier lancement : verifier la memoire
  allouee a Docker, 4 Go minimum.
- Le DAG n'apparait pas : attendre la fin de l'installation pip du premier demarrage,
  puis verifier `docker compose logs airflow-dag-processor`.
- Repartir de zero : `docker compose down -v` puis les deux commandes de demarrage.
