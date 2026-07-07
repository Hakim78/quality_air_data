-- verification de l'idempotence du chargement gold
-- mode d'emploi : je note le count, je relance le meme run dans airflow
-- (clear de la tache load_qualite_air_to_gold), puis je rejoue ces requetes,
-- le count doit etre identique et les deux requetes de doublons doivent rendre zero ligne

-- 1. volumetrie de la table de faits, a comparer avant et apres rejeu
SELECT count(*) AS nb_lignes_fait
FROM gold.fait_mesure_air;

-- 2. aucun doublon sur la cle metier, la contrainte primary key le garantit
--    mais je le prouve par la requete, zero ligne attendu
SELECT mesure_id, count(*) AS occurrences
FROM gold.fait_mesure_air
GROUP BY mesure_id
HAVING count(*) > 1;

-- 3. aucun doublon fonctionnel non plus : un capteur ne mesure pas deux fois
--    le meme polluant au meme instant, zero ligne attendu
SELECT id_capteur, horodatage_utc, id_polluant, count(*) AS occurrences
FROM gold.fait_mesure_air
GROUP BY id_capteur, horodatage_utc, id_polluant
HAVING count(*) > 1;

-- 4. la preuve par les logs : sur un rejeu, nb_inseres_gold retombe a zero
--    et nb_ignores_gold porte tout le lot, le on conflict a fait son travail
SELECT run_id, statut, nb_recuperes, nb_valides, nb_rejets,
       nb_inseres_gold, nb_ignores_gold, horodatage_execution
FROM meta.ingestion_log
ORDER BY horodatage_execution DESC
LIMIT 10;

-- 5. les controles qualite du dernier run, une ligne par regle comme exige
SELECT run_id, regle, nb_controles, nb_rejets, taux_conformite, cree_le
FROM meta.quality_log
WHERE run_id = (SELECT run_id FROM meta.quality_log ORDER BY cree_le DESC LIMIT 1)
ORDER BY regle;
