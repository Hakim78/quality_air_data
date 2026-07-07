"""petite api de lecture de la zone gold pour le front coureur

je ne fais que du select ici, metabase reste le dashboard officiel du tp,
ce front est le bonus oriente coureur : ou courir, quand courir
"""

import os
from contextlib import contextmanager

import psycopg2
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

DSN = os.environ.get(
    "QUALITE_AIR_PG_DSN",
    "postgresql://qualite_air:qualite_air@localhost:5433/qualite_air",
)

# perimetre d'analyse du front, l'ile de france comme dans le cadrage
LAT_MIN, LAT_MAX = 48.5, 49.1
LON_MIN, LON_MAX = 1.9, 2.9

FILTRE_IDF = """
      AND dl.en_interieur = false
      AND dl.latitude BETWEEN %(lat_min)s AND %(lat_max)s
      AND dl.longitude BETWEEN %(lon_min)s AND %(lon_max)s
"""

PARAMS_IDF = {"lat_min": LAT_MIN, "lat_max": LAT_MAX, "lon_min": LON_MIN, "lon_max": LON_MAX}

app = FastAPI(title="RunAir", docs_url=None, redoc_url=None)


@contextmanager
def connexion():
    conn = psycopg2.connect(DSN)
    try:
        yield conn
    finally:
        conn.close()


def _lignes(cur):
    colonnes = [c[0] for c in cur.description]
    return [dict(zip(colonnes, ligne)) for ligne in cur.fetchall()]


@app.get("/api/sante")
def sante():
    return {"statut": "ok"}


@app.get("/api/synthese")
def synthese():
    # les chiffres du bandeau : moyenne, part au dessus du seuil oms, meilleure heure, capteurs
    requete = f"""
    SELECT
        round(avg(f.valeur_ug_m3), 1) AS pm25_moyen_24h,
        round(100.0 * count(*) FILTER (WHERE f.valeur_ug_m3 > dp.seuil_oms_24h)
              / nullif(count(*), 0), 1) AS pct_au_dessus_seuil,
        count(DISTINCT f.id_capteur) AS capteurs_actifs,
        max(f.horodatage_utc) AS derniere_mesure
    FROM gold.fait_mesure_air f
    JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
    JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
    WHERE dp.code_api = 'P2'
      AND f.horodatage_utc >= now() - interval '24 hours'
      {FILTRE_IDF}
    """
    requete_meilleure_heure = f"""
    SELECT f.heure_locale, round(avg(f.valeur_ug_m3), 1) AS pm25
    FROM gold.fait_mesure_air f
    JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
    JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
    WHERE dp.code_api = 'P2'
      AND f.horodatage_utc >= now() - interval '7 days'
      {FILTRE_IDF}
    GROUP BY f.heure_locale
    ORDER BY avg(f.valeur_ug_m3)
    LIMIT 1
    """
    with connexion() as conn, conn.cursor() as cur:
        cur.execute(requete, PARAMS_IDF)
        resultat = _lignes(cur)[0]
        cur.execute(requete_meilleure_heure, PARAMS_IDF)
        meilleure = _lignes(cur)
    resultat["meilleure_heure"] = meilleure[0]["heure_locale"] if meilleure else None
    resultat["seuil_oms"] = 15
    return resultat


@app.get("/api/carte")
def carte():
    # un point par capteur avec sa moyenne pm2.5 des dernieres 24h, pour la heatmap
    requete = f"""
    SELECT dl.latitude AS lat, dl.longitude AS lon,
           round(avg(f.valeur_ug_m3), 1) AS pm25
    FROM gold.fait_mesure_air f
    JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
    JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
    WHERE dp.code_api = 'P2'
      AND f.horodatage_utc >= now() - interval '24 hours'
      {FILTRE_IDF}
    GROUP BY dl.latitude, dl.longitude
    """
    with connexion() as conn, conn.cursor() as cur:
        cur.execute(requete, PARAMS_IDF)
        return _lignes(cur)


@app.get("/api/creneaux")
def creneaux():
    # pm2.5 moyen par heure locale sur 7 jours, la base du bandeau quand courir
    requete = f"""
    SELECT f.heure_locale AS heure, round(avg(f.valeur_ug_m3), 1) AS pm25
    FROM gold.fait_mesure_air f
    JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
    JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
    WHERE dp.code_api = 'P2'
      AND f.horodatage_utc >= now() - interval '7 days'
      {FILTRE_IDF}
    GROUP BY f.heure_locale
    ORDER BY f.heure_locale
    """
    with connexion() as conn, conn.cursor() as cur:
        cur.execute(requete, PARAMS_IDF)
        return _lignes(cur)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
