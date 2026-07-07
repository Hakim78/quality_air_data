-- les trois questions du dashboard metabase "courir dans un air respirable"
-- chaque bloc se colle dans une question sql native de metabase,
-- la bbox 48.5/49.1 et 1.9/2.9 delimite l'ile de france ou vit mon destinataire

-- question 1, la carte : ou courir, ou eviter
-- pm2.5 moyen par capteur sur les dernieres 24h en ile de france
-- visualisation metabase : map, type grid map, latitude et longitude en axes,
-- couleur sur pm25_moyen (ou pin map si la densite est trop faible)
SELECT
    dl.latitude,
    dl.longitude,
    round(avg(f.valeur_ug_m3), 1) AS pm25_moyen
FROM gold.fait_mesure_air f
JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
WHERE dp.code_api = 'P2'
  AND f.horodatage_utc >= now() - interval '24 hours'
  AND dl.en_interieur = false
  AND dl.latitude BETWEEN 48.5 AND 49.1
  AND dl.longitude BETWEEN 1.9 AND 2.9
GROUP BY dl.latitude, dl.longitude;

-- question 2, la heatmap temporelle : quand courir
-- pm2.5 moyen par heure locale et par jour sur 7 jours, ile de france
-- visualisation metabase : tableau croise heure en ligne, date en colonne,
-- mise en forme conditionnelle du vert au rouge sur la valeur
SELECT
    dd.date_jour,
    f.heure_locale,
    round(avg(f.valeur_ug_m3), 1) AS pm25_moyen
FROM gold.fait_mesure_air f
JOIN gold.dim_date dd ON dd.id_date = f.id_date
JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
WHERE dp.code_api = 'P2'
  AND dd.date_jour >= current_date - 7
  AND dl.en_interieur = false
  AND dl.latitude BETWEEN 48.5 AND 49.1
  AND dl.longitude BETWEEN 1.9 AND 2.9
GROUP BY dd.date_jour, f.heure_locale
ORDER BY dd.date_jour, f.heure_locale;

-- question 3, les indicateurs : le constat immediat et la confiance dans la mesure
-- part des releves au dessus du seuil oms, meilleur creneau, capteurs actifs, sur 24h
-- visualisation metabase : trois cartes number a partir de cette requete
-- (ou trois questions separees si je veux une carte par kpi)
SELECT
    round(100.0 * count(*) FILTER (WHERE f.valeur_ug_m3 > dp.seuil_oms_24h) / count(*), 1)
        AS pct_releves_au_dessus_seuil_oms,
    (SELECT f2.heure_locale
     FROM gold.fait_mesure_air f2
     JOIN gold.dim_polluant dp2 ON dp2.id_polluant = f2.id_polluant
     JOIN gold.dim_localisation dl2 ON dl2.id_localisation = f2.id_localisation
     WHERE dp2.code_api = 'P2'
       AND f2.horodatage_utc >= now() - interval '24 hours'
       AND dl2.en_interieur = false
       AND dl2.latitude BETWEEN 48.5 AND 49.1
       AND dl2.longitude BETWEEN 1.9 AND 2.9
     GROUP BY f2.heure_locale
     ORDER BY avg(f2.valeur_ug_m3)
     LIMIT 1) AS meilleure_heure_pour_courir,
    count(DISTINCT f.id_capteur) AS capteurs_actifs_24h
FROM gold.fait_mesure_air f
JOIN gold.dim_polluant dp ON dp.id_polluant = f.id_polluant
JOIN gold.dim_localisation dl ON dl.id_localisation = f.id_localisation
WHERE dp.code_api = 'P2'
  AND f.horodatage_utc >= now() - interval '24 hours'
  AND dl.en_interieur = false
  AND dl.latitude BETWEEN 48.5 AND 49.1
  AND dl.longitude BETWEEN 1.9 AND 2.9;
