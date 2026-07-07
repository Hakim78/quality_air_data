-- logs metier et techniques, c'est mon metastore artisanal
-- ingestion_log : une ligne par run, le lien entre l'objet minio et ce qui a fini en base
-- quality_log : une ligne par regle et par run, l'enonce exige des controles logges separement

CREATE TABLE IF NOT EXISTS meta.ingestion_log (
    id                    serial PRIMARY KEY,
    dag_id                text NOT NULL,
    run_id                text UNIQUE NOT NULL,
    horodatage_execution  timestamptz NOT NULL DEFAULT now(),
    objet_bronze          text,
    objet_silver          text,
    nb_recuperes          integer,
    nb_valides            integer,
    nb_rejets             integer,
    nb_inseres_gold       integer,
    nb_ignores_gold       integer,
    statut                text NOT NULL,
    message               text
);

CREATE TABLE IF NOT EXISTS meta.quality_log (
    id               serial PRIMARY KEY,
    dag_id           text NOT NULL,
    run_id           text NOT NULL,
    regle            text NOT NULL,
    nb_controles     integer NOT NULL,
    nb_rejets        integer NOT NULL,
    taux_conformite  numeric NOT NULL,
    details          jsonb,
    cree_le          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, regle)
);
