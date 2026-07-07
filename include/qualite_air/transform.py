"""normalisation des enregistrements bruts de l'api, une ligne par mesure de polluant"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")

# les stations remontent aussi temperature et humidite, je ne garde que les particules
POLLUANTS = {"P0", "P1", "P2"}


def normaliser(bruts: list[dict]) -> list[dict]:
    lignes = []
    for enregistrement in bruts:
        capteur = enregistrement.get("sensor") or {}
        type_capteur = capteur.get("sensor_type") or {}
        localisation = enregistrement.get("location") or {}
        horodatage = _horodatage_utc(enregistrement.get("timestamp"))

        for mesure in enregistrement.get("sensordatavalues") or []:
            if mesure.get("value_type") not in POLLUANTS:
                continue
            ligne = {
                "mesure_id": mesure.get("id"),
                "releve_id": enregistrement.get("id"),
                "capteur_api_id": capteur.get("id"),
                "type_capteur": type_capteur.get("name"),
                "fabricant": type_capteur.get("manufacturer"),
                "localisation_api_id": localisation.get("id"),
                "latitude": _en_float(localisation.get("latitude")),
                "longitude": _en_float(localisation.get("longitude")),
                "altitude": _en_float(localisation.get("altitude")),
                "en_interieur": bool(localisation.get("indoor")),
                "pays": localisation.get("country"),
                "code_polluant": mesure.get("value_type"),
                "valeur_brute": mesure.get("value"),
                "valeur": _en_float(mesure.get("value")),
                "horodatage_utc": horodatage.isoformat() if horodatage else None,
                "date_locale": None,
                "heure_locale": None,
            }
            if horodatage:
                # c'est l'heure du coureur qui compte pour la question metier, donc heure de paris
                local = horodatage.astimezone(PARIS)
                ligne["date_locale"] = local.date().isoformat()
                ligne["heure_locale"] = local.hour
            lignes.append(ligne)
    return lignes


def _en_float(valeur):
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


def _horodatage_utc(brut):
    # l'api renvoie des timestamps naifs en utc au format 2026-07-07 09:02:01
    if not brut:
        return None
    try:
        return datetime.strptime(brut, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
