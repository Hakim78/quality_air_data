"""chargement de la zone gold : les dimensions d'abord, la table de faits ensuite

tout le chargement est idempotent, la cle metier mesure_id porte la contrainte
et le on conflict do nothing fait le reste, je peux rejouer un lot sans doublon
"""

from datetime import date

import pandas as pd
from psycopg2.extras import execute_values

from . import bdd


def charger_gold(df: pd.DataFrame, run_id: str) -> dict:
    if df.empty:
        return {"nb_inseres": 0, "nb_ignores": 0}

    # les nan pandas ne passent pas en sql, je les remets a null
    df = df.astype(object).where(pd.notnull(df), None)

    with bdd.connexion() as conn, conn.cursor() as cur:
        _charger_dim_date(cur, df)
        capteurs = _charger_dim_capteur(cur, df)
        localisations = _charger_dim_localisation(cur, df)
        polluants = _lire_dim_polluant(cur)

        lignes = [
            (
                int(l.mesure_id),
                int(str(l.date_locale).replace("-", "")),
                int(l.heure_locale),
                capteurs[int(l.capteur_api_id)],
                localisations[int(l.localisation_api_id)],
                polluants[l.code_polluant],
                float(l.valeur),
                l.horodatage_utc,
                run_id,
            )
            for l in df.itertuples()
        ]

        # je compte avant et apres plutot que de me fier au rowcount,
        # execute_values decoupe en pages et le rowcount ne vaudrait que pour la derniere
        cur.execute("SELECT count(*) FROM gold.fait_mesure_air")
        avant = cur.fetchone()[0]
        execute_values(
            cur,
            """
            INSERT INTO gold.fait_mesure_air
                (mesure_id, id_date, heure_locale, id_capteur, id_localisation,
                 id_polluant, valeur_ug_m3, horodatage_utc, run_id)
            VALUES %s
            ON CONFLICT (mesure_id) DO NOTHING
            """,
            lignes,
        )
        cur.execute("SELECT count(*) FROM gold.fait_mesure_air")
        nb_inseres = cur.fetchone()[0] - avant

    return {"nb_inseres": nb_inseres, "nb_ignores": len(lignes) - nb_inseres}


def _charger_dim_date(cur, df):
    valeurs = []
    for iso in sorted(set(df["date_locale"])):
        d = date.fromisoformat(iso)
        valeurs.append((int(iso.replace("-", "")), d, d.year, d.month, d.day,
                        d.isoweekday(), d.isoweekday() >= 6))
    execute_values(
        cur,
        """
        INSERT INTO gold.dim_date (id_date, date_jour, annee, mois, jour, jour_semaine, est_weekend)
        VALUES %s
        ON CONFLICT (id_date) DO NOTHING
        """,
        valeurs,
    )


def _charger_dim_capteur(cur, df):
    capteurs = df[["capteur_api_id", "type_capteur", "fabricant"]].drop_duplicates("capteur_api_id")
    execute_values(
        cur,
        """
        INSERT INTO gold.dim_capteur (capteur_api_id, type_capteur, fabricant)
        VALUES %s
        ON CONFLICT (capteur_api_id) DO NOTHING
        """,
        [(int(l.capteur_api_id), l.type_capteur, l.fabricant) for l in capteurs.itertuples()],
    )
    cur.execute("SELECT capteur_api_id, id_capteur FROM gold.dim_capteur")
    return dict(cur.fetchall())


def _charger_dim_localisation(cur, df):
    localisations = df[
        ["localisation_api_id", "latitude", "longitude", "altitude", "en_interieur", "pays"]
    ].drop_duplicates("localisation_api_id")
    execute_values(
        cur,
        """
        INSERT INTO gold.dim_localisation
            (localisation_api_id, latitude, longitude, altitude, en_interieur, pays)
        VALUES %s
        ON CONFLICT (localisation_api_id) DO NOTHING
        """,
        [
            (int(l.localisation_api_id), l.latitude, l.longitude, l.altitude,
             bool(l.en_interieur), l.pays)
            for l in localisations.itertuples()
        ],
    )
    cur.execute("SELECT localisation_api_id, id_localisation FROM gold.dim_localisation")
    return dict(cur.fetchall())


def _lire_dim_polluant(cur):
    cur.execute("SELECT code_api, id_polluant FROM gold.dim_polluant")
    return dict(cur.fetchall())
