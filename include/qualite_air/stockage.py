"""acces minio pour les zones bronze et silver, je centralise le client ici"""

import io
import json
import os

import pandas as pd
from minio import Minio

BUCKET_BRONZE = os.environ.get("QUALITE_AIR_BUCKET_BRONZE", "bronze")
BUCKET_SILVER = os.environ.get("QUALITE_AIR_BUCKET_SILVER", "silver")


def client_minio() -> Minio:
    return Minio(
        os.environ.get("MINIO_ENDPOINT", "minio:9000"),
        access_key=os.environ.get("MINIO_ACCESS_KEY", "qualite_air"),
        secret_key=os.environ.get("MINIO_SECRET_KEY", "qualite_air_minio"),
        secure=os.environ.get("MINIO_SECURE", "false").lower() == "true",
    )


def deposer_json_bronze(donnees: list[dict], cle: str) -> str:
    # bronze = copie fidele de la reponse api, je ne transforme rien ici
    contenu = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    client_minio().put_object(
        BUCKET_BRONZE, cle, io.BytesIO(contenu), len(contenu),
        content_type="application/json",
    )
    return cle


def deposer_parquet_silver(lignes: list[dict], cle: str) -> str:
    df = pd.DataFrame(lignes)
    tampon = io.BytesIO()
    df.to_parquet(tampon, index=False)
    taille = tampon.getbuffer().nbytes
    tampon.seek(0)
    client_minio().put_object(
        BUCKET_SILVER, cle, tampon, taille,
        content_type="application/octet-stream",
    )
    return cle


def lire_parquet_silver(cle: str) -> pd.DataFrame:
    reponse = client_minio().get_object(BUCKET_SILVER, cle)
    try:
        return pd.read_parquet(io.BytesIO(reponse.read()))
    finally:
        reponse.close()
        reponse.release_conn()
