"""recuperation de la fenetre courante de mesures sur l'api sensor.community"""

import requests


def recuperer_fenetre(url: str, timeout: int = 10) -> list[dict]:
    # timeout http court en plus de l'execution_timeout airflow, deux filets valent mieux qu'un
    reponse = requests.get(url, timeout=timeout)
    reponse.raise_for_status()
    return reponse.json()
