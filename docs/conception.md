# Document de conception

Produit avant toute ligne de code, comme demande dans l'enonce. Quatre volets :
architecture data, diagramme du pipeline, modele gold en etoile, formulation du probleme
metier (cette derniere est detaillee dans [cadrage_metier.md](cadrage_metier.md)).

## 1. Schema d'architecture data

```mermaid
flowchart LR
    api[API sensor.community<br>fenetre 5 min, JSON, sans cle]

    subgraph orchestration[Airflow 3.3, LocalExecutor]
        dag[DAG qualite_air_api_15min_ingestion<br>TaskFlow, toutes les 15 min]
    end

    subgraph minio[MinIO stockage objet]
        bronze[(bucket bronze<br>JSON brut)]
        silver[(bucket silver<br>parquet nettoye)]
        quarantaine[(bucket silver<br>prefixe quarantaine)]
    end

    subgraph pg[PostgreSQL metier]
        gold[(schema gold<br>etoile)]
        meta[(schema meta<br>logs)]
    end

    pgairflow[(PostgreSQL dedie<br>metadata Airflow)]
    metabase[Metabase<br>dashboard coureurs]

    api --> dag
    dag --> bronze
    dag --> silver
    dag --> quarantaine
    dag --> gold
    dag --> meta
    dag -.metadata.-> pgairflow
    gold --> metabase
```

Choix structurants :

- Trois zones distinctes. Bronze : la reponse API brute, format d'origine JSON, append only,
  rejouable. Silver : donnees normalisees et typees en parquet, partitionnees a la mode hive
  (`annee=AAAA/mois=MM/jour=JJ`), avec un prefixe `quarantaine/` qui recoit les lignes
  rejetees et leurs motifs. Gold : PostgreSQL, modele en etoile, consomme par Metabase.
- La metadata db d'Airflow vit dans une base PostgreSQL dediee (`postgres-airflow`),
  jamais melangee a la base metier (`postgres-metier`). SQLite est exclu : le DAG comporte
  des taches independantes executables en parallele (archivage bronze et transformation
  partent toutes les deux de l'ingestion), d'ou LocalExecutor.
- Metabase stocke sa configuration dans sa propre base `metabase` sur l'instance metier,
  et lit les donnees dans le schema gold uniquement.

## 2. Diagramme du pipeline

```mermaid
flowchart TD
    sensor[wait_for_qualite_air_api<br>sensor, poke 30s, timeout 180s] --> fetch
    fetch[fetch_qualite_air_api<br>retries 2, retry_delay 1 min, timeout 3 min] --> archive
    fetch --> transfo
    archive[archive_raw_to_bronze<br>JSON brut vers MinIO bronze]
    transfo[transform_qualite_air_records<br>normalisation, 1 ligne par polluant] --> check
    check[check_qualite_air_quality<br>5 regles, silver + quarantaine, meta.quality_log] --> branche
    branche{choose_loading_branch<br>taux conformite vs seuil} -->|taux >= seuil| charge
    branche -->|taux < seuil| alerte
    charge[load_qualite_air_to_gold<br>dimensions puis faits, on conflict do nothing] --> bilan
    alerte[log_quality_alert<br>le dag reste vert, donnees en quarantaine] --> bilan
    archive --> bilan
    bilan[write_ingestion_summary<br>trigger none_failed_min_one_success<br>meta.ingestion_log]
```

Les trois chemins exiges et la maniere de les demontrer :

| Chemin | Declencheur pour la demo | Resultat attendu |
|---|---|---|
| Nominal | rien a changer, run planifie ou manuel | tout vert, gold alimente, une branche skippee (normal) |
| Echec qualite | variable `qualite_air_pm_max` a 1 | dag vert, `load` skippee, lignes en quarantaine dans silver, alerte loggee |
| Echec technique | variable `qualite_air_api_url` vers un hote inexistant | sensor en echec apres 180 s, dag rouge |

Doctrine de robustesse appliquee :

- retries et retry_delay sur les taches d'entree sortie (`fetch`, `archive`, `load`) :
  une API ou un service de stockage peut tousser temporairement.
- pas de retries sur `transform` et `check` : rejouer un calcul deterministe sur les memes
  donnees ne change rien.
- execution_timeout explicite sur toutes les taches, en plus du timeout HTTP de 10 s dans
  le code : deux filets independants.
- le chargement gold est idempotent, donc ses retries sont sans risque de doublon.
- XCom ne transporte que du petit : la fenetre JSON fait moins d'un mega octet, les chemins
  d'objets MinIO et les rapports qualite. Le volumineux vit dans MinIO.
- logging a deux niveaux : les logs Airflow par tache dans l'interface, et les logs metier
  transverses dans `meta.ingestion_log` (une ligne par run) et `meta.quality_log` (une ligne
  par regle et par run).

## 3. Modele gold : schema en etoile

Grain de la table de faits : une mesure d'un polluant par un capteur a un instant donne.

```mermaid
erDiagram
    dim_date ||--o{ fait_mesure_air : id_date
    dim_capteur ||--o{ fait_mesure_air : id_capteur
    dim_localisation ||--o{ fait_mesure_air : id_localisation
    dim_polluant ||--o{ fait_mesure_air : id_polluant

    fait_mesure_air {
        bigint mesure_id PK "cle metier API, porte l'idempotence"
        integer id_date FK
        smallint heure_locale "0 a 23, heure de Paris, sert la question quand courir"
        integer id_capteur FK
        integer id_localisation FK
        integer id_polluant FK
        numeric valeur_ug_m3
        timestamptz horodatage_utc
        text run_id "tracabilite vers le run Airflow"
    }
    dim_date {
        integer id_date PK "format AAAAMMJJ"
        date date_jour
        smallint annee
        smallint mois
        smallint jour
        smallint jour_semaine
        boolean est_weekend
    }
    dim_capteur {
        integer id_capteur PK
        bigint capteur_api_id UK
        text type_capteur
        text fabricant
    }
    dim_localisation {
        integer id_localisation PK
        bigint localisation_api_id UK
        numeric latitude
        numeric longitude
        numeric altitude
        boolean en_interieur
        text pays
    }
    dim_polluant {
        integer id_polluant PK
        text code_api UK "P0, P1, P2"
        text libelle "PM1, PM10, PM2.5"
        numeric seuil_oms_24h "le dashboard compare a ce seuil"
    }
```

Justifications :

- `heure_locale` est portee par le fait (dimension degeneree) parce que la question metier
  est une question de creneau horaire : l'agregation par heure est le coeur du dashboard.
- le seuil OMS vit dans `dim_polluant` : le dashboard compare les mesures au seuil par une
  jointure, sans valeur en dur dans les requetes.
- `dim_localisation` conserve `en_interieur` : un capteur d'interieur ne dit rien de l'air
  d'un parcours de course, le dashboard filtre dessus.
- idempotence : `mesure_id` (identifiant de la valeur cote API) est cle primaire, le
  chargement fait `INSERT ... ON CONFLICT (mesure_id) DO NOTHING`. Les doublons sont deja
  ecartes en silver par la regle unicite, la contrainte SQL reste en filet de securite.
  Les requetes de preuve sont dans [../sql/verification_idempotence.sql](../sql/verification_idempotence.sql).

## 4. Les cinq regles qualite

Appliquees au passage bronze vers silver, chacune comptee et loggee separement dans
`meta.quality_log`. Une ligne rejetee part en quarantaine avec ses motifs.

| Regle | Controle concret sur ces donnees |
|---|---|
| completude | identifiants, horodatage, coordonnees et valeur presents |
| exactitude | valeur castable en nombre, entre 0 et `qualite_air_pm_max` (defaut 999, le SDS011 sature a 999.9 qui est son code d'erreur connu), coordonnees GPS plausibles, point 0,0 rejete |
| coherence | pas d'horodatage dans le futur, et PM2.5 inferieur ou egal a PM10 sur un meme releve, l'inverse trahit un capteur qui deraille |
| fraicheur | horodatage plus recent que `qualite_air_fraicheur_max_minutes` (defaut 60) au moment du run |
| unicite | pas de doublon d'identifiant API ni de doublon capteur + instant + polluant dans le lot |

## 5. Conventions de nommage

| Objet | Convention | Application ici |
|---|---|---|
| DAG | domaine + processus + frequence | `qualite_air_api_15min_ingestion` |
| Taches | verbe + objet + contexte | `fetch_qualite_air_api`, `check_qualite_air_quality`, `load_qualite_air_to_gold` |
| Tables de faits | prefixe `fait_` | `gold.fait_mesure_air` |
| Dimensions | prefixe `dim_`, cle `id_` | `gold.dim_date`, `id_date` |
| Logs | schema `meta` | `meta.ingestion_log`, `meta.quality_log` |
| Objets bronze | domaine/date/run | `qualite_air/2026-07-07/<run_id>.json` |
| Objets silver | partitionnement hive | `qualite_air/mesures/annee=2026/mois=07/jour=07/<run_id>.parquet` |
| Quarantaine | meme partitionnement | `qualite_air/quarantaine/annee=2026/mois=07/jour=07/<run_id>.parquet` |
