"""connexion au postgres metier et ecriture des logs dans le schema meta"""

import os

import psycopg2
from psycopg2.extras import Json

DSN_DEFAUT = "postgresql://qualite_air:qualite_air@postgres-metier:5432/qualite_air"


def connexion():
    return psycopg2.connect(os.environ.get("QUALITE_AIR_PG_DSN", DSN_DEFAUT))


def journaliser_qualite(dag_id: str, run_id: str, rapport: dict) -> None:
    # une ligne par regle, l'enonce exige des controles appliques et logges separement
    # le on conflict permet de rejouer un run sans dupliquer les lignes de log
    with connexion() as conn, conn.cursor() as cur:
        for regle, compteur in rapport["par_regle"].items():
            nb_controles = compteur["nb_controles"]
            nb_rejets = compteur["nb_rejets"]
            taux = round(100.0 * (nb_controles - nb_rejets) / nb_controles, 2) if nb_controles else 0.0
            cur.execute(
                """
                INSERT INTO meta.quality_log
                    (dag_id, run_id, regle, nb_controles, nb_rejets, taux_conformite, details)
                VALUES
                    (%(dag_id)s, %(run_id)s, %(regle)s, %(nb_controles)s, %(nb_rejets)s, %(taux)s, %(details)s)
                ON CONFLICT (run_id, regle) DO UPDATE SET
                    nb_controles = EXCLUDED.nb_controles,
                    nb_rejets = EXCLUDED.nb_rejets,
                    taux_conformite = EXCLUDED.taux_conformite,
                    details = EXCLUDED.details
                """,
                {
                    "dag_id": dag_id,
                    "run_id": run_id,
                    "regle": regle,
                    "nb_controles": nb_controles,
                    "nb_rejets": nb_rejets,
                    "taux": taux,
                    "details": Json({"taux_conformite_global": rapport["taux_conformite"]}),
                },
            )


def journaliser_ingestion(dag_id: str, run_id: str, objet_bronze: str | None,
                          objet_silver: str | None, rapport: dict,
                          nb_inseres: int, nb_ignores: int, statut: str,
                          message: str = "") -> None:
    with connexion() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meta.ingestion_log
                (dag_id, run_id, objet_bronze, objet_silver, nb_recuperes, nb_valides,
                 nb_rejets, nb_inseres_gold, nb_ignores_gold, statut, message)
            VALUES
                (%(dag_id)s, %(run_id)s, %(objet_bronze)s, %(objet_silver)s, %(nb_recuperes)s,
                 %(nb_valides)s, %(nb_rejets)s, %(nb_inseres)s, %(nb_ignores)s, %(statut)s, %(message)s)
            ON CONFLICT (run_id) DO UPDATE SET
                objet_bronze = EXCLUDED.objet_bronze,
                objet_silver = EXCLUDED.objet_silver,
                nb_recuperes = EXCLUDED.nb_recuperes,
                nb_valides = EXCLUDED.nb_valides,
                nb_rejets = EXCLUDED.nb_rejets,
                nb_inseres_gold = EXCLUDED.nb_inseres_gold,
                nb_ignores_gold = EXCLUDED.nb_ignores_gold,
                statut = EXCLUDED.statut,
                message = EXCLUDED.message,
                horodatage_execution = now()
            """,
            {
                "dag_id": dag_id,
                "run_id": run_id,
                "objet_bronze": objet_bronze,
                "objet_silver": objet_silver,
                "nb_recuperes": rapport["nb_total"],
                "nb_valides": rapport["nb_valides"],
                "nb_rejets": rapport["nb_rejets"],
                "nb_inseres": nb_inseres,
                "nb_ignores": nb_ignores,
                "statut": statut,
                "message": message,
            },
        )
