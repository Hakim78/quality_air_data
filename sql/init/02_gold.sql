-- modele en etoile de la zone gold
-- grain de la table de faits : une mesure d'un polluant par un capteur a un instant donne

CREATE TABLE IF NOT EXISTS gold.dim_date (
    id_date        integer PRIMARY KEY,
    date_jour      date NOT NULL,
    annee          smallint NOT NULL,
    mois           smallint NOT NULL,
    jour           smallint NOT NULL,
    jour_semaine   smallint NOT NULL,
    est_weekend    boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS gold.dim_polluant (
    id_polluant    serial PRIMARY KEY,
    code_api       text UNIQUE NOT NULL,
    libelle        text NOT NULL,
    -- seuil recommande par l'oms en moyenne 24h, c'est lui que le dashboard compare
    seuil_oms_24h  numeric
);

CREATE TABLE IF NOT EXISTS gold.dim_capteur (
    id_capteur      serial PRIMARY KEY,
    capteur_api_id  bigint UNIQUE NOT NULL,
    type_capteur    text,
    fabricant       text
);

CREATE TABLE IF NOT EXISTS gold.dim_localisation (
    id_localisation      serial PRIMARY KEY,
    localisation_api_id  bigint UNIQUE NOT NULL,
    latitude             numeric(9, 6),
    longitude            numeric(9, 6),
    altitude             numeric,
    en_interieur         boolean,
    pays                 text
);

CREATE TABLE IF NOT EXISTS gold.fait_mesure_air (
    -- cle metier venant de l'api, c'est elle qui porte l'idempotence du chargement
    mesure_id        bigint PRIMARY KEY,
    id_date          integer NOT NULL REFERENCES gold.dim_date (id_date),
    heure_locale     smallint NOT NULL,
    id_capteur       integer NOT NULL REFERENCES gold.dim_capteur (id_capteur),
    id_localisation  integer NOT NULL REFERENCES gold.dim_localisation (id_localisation),
    id_polluant      integer NOT NULL REFERENCES gold.dim_polluant (id_polluant),
    valeur_ug_m3     numeric NOT NULL,
    horodatage_utc   timestamptz NOT NULL,
    run_id           text
);

CREATE INDEX IF NOT EXISTS idx_fait_mesure_air_date ON gold.fait_mesure_air (id_date);
CREATE INDEX IF NOT EXISTS idx_fait_mesure_air_polluant ON gold.fait_mesure_air (id_polluant);
CREATE INDEX IF NOT EXISTS idx_fait_mesure_air_localisation ON gold.fait_mesure_air (id_localisation);
CREATE INDEX IF NOT EXISTS idx_fait_mesure_air_horodatage ON gold.fait_mesure_air (horodatage_utc);
