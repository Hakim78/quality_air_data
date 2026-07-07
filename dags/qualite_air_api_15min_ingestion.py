"""pipeline lakehouse qualite de l'air, api sensor.community vers bronze silver gold

toutes les 15 minutes je recupere la fenetre courante de mesures en france,
je l'archive telle quelle en bronze, je la normalise, je passe les cinq regles
qualite avec quarantaine, puis je charge la zone gold seulement si le taux de
conformite depasse le seuil. l'historique se construit run apres run, c'est
l'accumulation orchestree qui donne sa profondeur au dashboard.

trois chemins demontrables :
  nominal, tout est vert et gold est alimente
  echec qualite, dag vert mais chargement saute et lignes en quarantaine
    (passer la variable qualite_air_pm_max a 1 pour le forcer)
  echec technique, dag rouge sur api injoignable
    (passer qualite_air_api_url vers un hote inexistant pour le forcer)
"""

import logging
from datetime import timedelta

import pendulum
import requests
from airflow.sdk import Variable, dag, get_current_context, task

from include.qualite_air import bdd, extract, load, quality, stockage, transform

DAG_ID = "qualite_air_api_15min_ingestion"

journal = logging.getLogger(__name__)


@dag(
    dag_id=DAG_ID,
    description="ingestion des mesures de particules fines sensor.community, france entiere",
    schedule="*/15 * * * *",
    start_date=pendulum.datetime(2026, 7, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "hakim"},
    tags=["lakehouse", "qualite_air"],
)
def qualite_air_api_15min_ingestion():

    @task.sensor(poke_interval=30, timeout=180, mode="poke")
    def wait_for_qualite_air_api() -> bool:
        # je verifie que l'api repond avant de lancer la suite,
        # si elle reste muette le sensor finit en echec et le dag passe rouge
        url = Variable.get("qualite_air_api_url")
        try:
            reponse = requests.get(url, timeout=10, stream=True)
            disponible = reponse.ok
            reponse.close()
        except requests.RequestException:
            disponible = False
        return disponible

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(minutes=3))
    def fetch_qualite_air_api() -> list[dict]:
        # retries pertinents ici, une api publique peut tousser temporairement
        url = Variable.get("qualite_air_api_url")
        enregistrements = extract.recuperer_fenetre(url)
        journal.info("api ok, %s enregistrements dans la fenetre", len(enregistrements))
        # la fenetre de 5 minutes pese moins d'un mo, ca passe en xcom,
        # au dela je ferais transiter un chemin minio a la place
        return enregistrements

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(minutes=3))
    def archive_raw_to_bronze(enregistrements: list[dict]) -> str:
        # copie fidele en bronze, nommage tracable date puis run_id
        contexte = get_current_context()
        cle = f"qualite_air/{contexte['ds']}/{contexte['run_id']}.json"
        stockage.deposer_json_bronze(enregistrements, cle)
        journal.info("bronze archive sous %s", cle)
        return cle

    @task(execution_timeout=timedelta(minutes=3))
    def transform_qualite_air_records(enregistrements: list[dict]) -> list[dict]:
        # pas de retries, rejouer le meme calcul sur les memes donnees ne change rien
        lignes = transform.normaliser(enregistrements)
        journal.info("transformation: %s lignes de particules", len(lignes))
        return lignes

    @task(execution_timeout=timedelta(minutes=3))
    def check_qualite_air_quality(lignes: list[dict]) -> dict:
        # cette tache ne charge rien, elle mesure et elle trace,
        # la decision de charger appartient au branchement d'apres
        contexte = get_current_context()
        run_id = contexte["run_id"]
        pm_max = float(Variable.get("qualite_air_pm_max"))
        fraicheur_max = int(Variable.get("qualite_air_fraicheur_max_minutes"))

        valides, rejets, rapport = quality.appliquer_regles(lignes, pm_max, fraicheur_max)

        annee, mois, jour = contexte["ds"].split("-")
        prefixe = f"annee={annee}/mois={mois}/jour={jour}"
        cle_silver = None
        if valides:
            cle_silver = stockage.deposer_parquet_silver(
                valides, f"qualite_air/mesures/{prefixe}/{run_id}.parquet")
        cle_quarantaine = None
        if rejets:
            # rien ne disparait en silence, les rejets partent en quarantaine avec leurs motifs
            cle_quarantaine = stockage.deposer_parquet_silver(
                rejets, f"qualite_air/quarantaine/{prefixe}/{run_id}.parquet")

        bdd.journaliser_qualite(DAG_ID, run_id, rapport)
        journal.info("qualite: %s/%s valides, taux %s%%, quarantaine %s",
                     rapport["nb_valides"], rapport["nb_total"],
                     rapport["taux_conformite"], cle_quarantaine or "vide")
        return {"rapport": rapport, "cle_silver": cle_silver, "cle_quarantaine": cle_quarantaine}

    @task.branch(execution_timeout=timedelta(minutes=1))
    def choose_loading_branch(retour_qualite: dict) -> str:
        # le retour est le task_id de la branche a suivre, l'autre sera skippee
        seuil = float(Variable.get("conformite_seuil_pct"))
        if retour_qualite["rapport"]["taux_conformite"] >= seuil:
            return "load_qualite_air_to_gold"
        return "log_quality_alert"

    @task(retries=2, retry_delay=timedelta(minutes=1), execution_timeout=timedelta(minutes=3))
    def load_qualite_air_to_gold(retour_qualite: dict) -> dict:
        # les retries sont sans risque puisque le chargement est idempotent
        contexte = get_current_context()
        cle_silver = retour_qualite["cle_silver"]
        if not cle_silver:
            return {"nb_inseres": 0, "nb_ignores": 0}
        df = stockage.lire_parquet_silver(cle_silver)
        resultat = load.charger_gold(df, contexte["run_id"])
        journal.info("gold: %s lignes inserees, %s ignorees car deja presentes",
                     resultat["nb_inseres"], resultat["nb_ignores"])
        return resultat

    @task(execution_timeout=timedelta(minutes=1))
    def log_quality_alert(retour_qualite: dict) -> None:
        # branche d'alerte du chemin d'echec qualite, le dag reste vert
        rapport = retour_qualite["rapport"]
        journal.warning(
            "qualite insuffisante, aucun chargement gold: taux %s%%, %s lignes rejetees, quarantaine %s",
            rapport["taux_conformite"], rapport["nb_rejets"],
            retour_qualite["cle_quarantaine"] or "vide")

    @task(trigger_rule="none_failed_min_one_success", execution_timeout=timedelta(minutes=1))
    def write_ingestion_summary(cle_bronze: str, retour_qualite: dict) -> None:
        # bilan du run dans meta.ingestion_log quel que soit le chemin pris,
        # d'ou la trigger rule, une des deux branches est forcement skippee
        contexte = get_current_context()
        resultat_gold = contexte["ti"].xcom_pull(task_ids="load_qualite_air_to_gold")
        statut = "charge" if resultat_gold else "alerte_qualite"
        resultat_gold = resultat_gold or {"nb_inseres": 0, "nb_ignores": 0}
        bdd.journaliser_ingestion(
            dag_id=DAG_ID,
            run_id=contexte["run_id"],
            objet_bronze=cle_bronze,
            objet_silver=retour_qualite["cle_silver"],
            rapport=retour_qualite["rapport"],
            nb_inseres=resultat_gold["nb_inseres"],
            nb_ignores=resultat_gold["nb_ignores"],
            statut=statut,
        )
        journal.info("bilan ecrit dans meta.ingestion_log, statut %s", statut)

    api_disponible = wait_for_qualite_air_api()
    brut = fetch_qualite_air_api()
    api_disponible >> brut

    cle_bronze = archive_raw_to_bronze(brut)
    lignes = transform_qualite_air_records(brut)
    retour_qualite = check_qualite_air_quality(lignes)

    branche = choose_loading_branch(retour_qualite)
    charge = load_qualite_air_to_gold(retour_qualite)
    alerte = log_quality_alert(retour_qualite)
    bilan = write_ingestion_summary(cle_bronze, retour_qualite)

    branche >> charge
    branche >> alerte
    charge >> bilan
    alerte >> bilan


qualite_air_api_15min_ingestion()
