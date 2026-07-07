"""les cinq regles qualite du cours, chacune comptee separement pour le log meta

une ligne peut cumuler plusieurs motifs de rejet, elle part en quarantaine des le premier
"""

from datetime import datetime, timedelta, timezone

REGLES = ["completude", "exactitude", "coherence", "fraicheur", "unicite"]

CHAMPS_REQUIS = [
    "mesure_id", "capteur_api_id", "localisation_api_id",
    "horodatage_utc", "latitude", "longitude", "code_polluant", "valeur_brute",
]

# je ne controle que la plausibilite gps, pas le perimetre geographique :
# country=FR inclut les dom tom et ce sont des mesures parfaitement valides,
# le dashboard filtre l'ile de france de son cote


def appliquer_regles(lignes: list[dict], pm_max: float, fraicheur_max_minutes: int,
                     maintenant: datetime | None = None):
    maintenant = maintenant or datetime.now(timezone.utc)
    motifs = [[] for _ in lignes]

    _controler_completude(lignes, motifs)
    _controler_exactitude(lignes, motifs, pm_max)
    _controler_coherence(lignes, motifs, maintenant)
    _controler_fraicheur(lignes, motifs, fraicheur_max_minutes, maintenant)
    _controler_unicite(lignes, motifs)

    valides, rejets = [], []
    compteurs = {regle: 0 for regle in REGLES}
    for ligne, motifs_ligne in zip(lignes, motifs):
        for regle in motifs_ligne:
            compteurs[regle] += 1
        if motifs_ligne:
            rejets.append({**ligne, "motifs_rejet": ",".join(motifs_ligne)})
        else:
            valides.append(ligne)

    nb_total = len(lignes)
    rapport = {
        "nb_total": nb_total,
        "nb_valides": len(valides),
        "nb_rejets": len(rejets),
        "taux_conformite": round(100.0 * len(valides) / nb_total, 2) if nb_total else 0.0,
        "par_regle": {
            regle: {"nb_controles": nb_total, "nb_rejets": compteurs[regle]}
            for regle in REGLES
        },
    }
    return valides, rejets, rapport


def _controler_completude(lignes, motifs):
    # les champs attendus sont ils renseignes
    for i, ligne in enumerate(lignes):
        for champ in CHAMPS_REQUIS:
            if ligne.get(champ) in (None, ""):
                motifs[i].append("completude")
                break


def _controler_exactitude(lignes, motifs, pm_max):
    # la valeur reflete t elle une realite plausible : castable, positive,
    # sous le plafond (le sds011 sature a 999.9, c'est son code d'erreur connu),
    # et des coordonnees gps possibles, le fameux point 0,0 compris
    for i, ligne in enumerate(lignes):
        ko = False
        if ligne.get("valeur_brute") not in (None, "") and ligne.get("valeur") is None:
            ko = True
        valeur = ligne.get("valeur")
        if valeur is not None and not 0 <= valeur <= pm_max:
            ko = True
        latitude = ligne.get("latitude")
        longitude = ligne.get("longitude")
        if latitude is not None and abs(latitude) > 90:
            ko = True
        if longitude is not None and abs(longitude) > 180:
            ko = True
        if latitude == 0 and longitude == 0:
            ko = True
        if ko:
            motifs[i].append("exactitude")


def _controler_coherence(lignes, motifs, maintenant):
    # deux controles : pas de mesure datee dans le futur, et pm2.5 <= pm10 sur un meme releve
    # physiquement les pm2.5 sont incluses dans les pm10, l'inverse trahit un capteur qui deraille
    tolerance_futur = maintenant + timedelta(minutes=5)
    groupes = {}
    for i, ligne in enumerate(lignes):
        if ligne.get("horodatage_utc"):
            if datetime.fromisoformat(ligne["horodatage_utc"]) > tolerance_futur:
                motifs[i].append("coherence")
        if ligne.get("code_polluant") in ("P1", "P2") and ligne.get("valeur") is not None:
            cle = (ligne.get("capteur_api_id"), ligne.get("horodatage_utc"))
            groupes.setdefault(cle, {})[ligne["code_polluant"]] = i

    for indices in groupes.values():
        if "P1" in indices and "P2" in indices:
            if lignes[indices["P2"]]["valeur"] > lignes[indices["P1"]]["valeur"]:
                for i in indices.values():
                    if "coherence" not in motifs[i]:
                        motifs[i].append("coherence")


def _controler_fraicheur(lignes, motifs, fraicheur_max_minutes, maintenant):
    # la donnee est elle a jour au moment ou je la traite
    limite = maintenant - timedelta(minutes=fraicheur_max_minutes)
    for i, ligne in enumerate(lignes):
        if ligne.get("horodatage_utc") is None:
            continue
        if datetime.fromisoformat(ligne["horodatage_utc"]) < limite:
            motifs[i].append("fraicheur")


def _controler_unicite(lignes, motifs):
    # pas de doublon d'identifiant api ni de doublon fonctionnel capteur + instant + polluant
    ids_vus, grains_vus = set(), set()
    for i, ligne in enumerate(lignes):
        doublon = False
        mesure_id = ligne.get("mesure_id")
        if mesure_id is not None:
            if mesure_id in ids_vus:
                doublon = True
            ids_vus.add(mesure_id)
        grain = (ligne.get("capteur_api_id"), ligne.get("horodatage_utc"), ligne.get("code_polluant"))
        if None not in grain:
            if grain in grains_vus:
                doublon = True
            grains_vus.add(grain)
        if doublon:
            motifs[i].append("unicite")
