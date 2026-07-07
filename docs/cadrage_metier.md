# Note de cadrage metier : courir dans un air respirable

## 1. Domaine metier retenu

La qualite de l'air urbaine appliquee a la pratique de la course a pied en exterieur.

Les donnees sont les releves de particules fines (PM1, PM10, PM2.5) du reseau
[Sensor.Community](https://sensor.community), le plus grand reseau citoyen mondial de capteurs
de qualite de l'air. Des particuliers installent des capteurs (principalement des SDS011) qui
mesurent en continu, avec une position GPS, un type de capteur et un horodatage par releve.

- Quoi : concentrations de particules fines en microgrammes par metre cube, mesurees toutes
  les 2 a 3 minutes par des milliers de stations.
- Pour qui : les coureurs et ceux qui organisent leur pratique (clubs, applications de running).
- Dans quel but : courir augmente fortement la ventilation pulmonaire, donc la dose de
  particules inhalees. Choisir ou et quand courir est une vraie decision de sante.

## 2. Question metier

Ou et a quel moment de la journee un coureur peut il s'entrainer en Ile de France en
respirant un air conforme a la recommandation OMS (PM2.5 sous 15 microgrammes par metre cube),
et quelles zones ou creneaux horaires faut il eviter cette semaine ?

C'est une question de decision, pas d'affichage : le dashboard doit faire constater un ecart
a un seuil, une comparaison entre zones et un meilleur moment pour agir.

## 3. Destinataire imaginaire

Le coach d'un club de running francilien qui planifie chaque semaine les creneaux et lieux
d'entrainement de ses groupes. Il consulte le dashboard le dimanche soir et avant chaque
seance pour :

1. choisir le secteur de la sortie longue, dans la zone la moins exposee ;
2. placer les seances d'intensite sur les creneaux horaires historiquement les plus propres,
   car le fractionne pousse la ventilation au maximum ;
3. decider un repli en interieur si le seuil OMS est durablement depasse.

Extension naturelle du meme dashboard : l'equipe produit d'une application de running qui
voudrait recommander des creneaux et parcours a air pur.

## 4. Source de donnees (verifiee le 07/07/2026)

| Critere de l'enonce | Verification |
|---|---|
| Publique et gratuite, sans carte ni cle | Oui, aucune cle, teste en direct |
| Donnees structurees JSON | Oui, endpoint `GET https://data.sensor.community/airrohr/v1/filter/country=FR` |
| Dimension temporelle reelle | Oui, un timestamp par releve, precision a la seconde |
| Volume suffisant | Oui, plus de 1000 releves par fenetre de 5 minutes en France, dont 92 capteurs de particules actifs sur la seule Ile de France |

Decisions de perimetre :

- Ingestion France entiere (`country=FR`) : un seul appel, volume maximal, genericite.
- Analyse du dashboard sur l'Ile de France (bbox 48.5, 1.9 a 49.1, 2.9), la ou vit le
  destinataire.
- L'API live ne renvoie que les 5 dernieres minutes : la profondeur historique se construit
  par ingestion frequente orchestree par Airflow, toutes les 15 minutes. C'est precisement
  le role d'un pipeline. En option, un backfill est possible via les archives quotidiennes
  (`https://archive.sensor.community/AAAA-MM-JJ/`, un CSV par capteur, verifie).

Seuils de reference (OMS 2021, moyenne 24h) : PM2.5 a 15 et PM10 a 45 microgrammes par metre
cube. L'OMS ne publie pas de seuil horaire, j'utilise le seuil 24h comme reference prudente
pour un effort intense.

## 5. Ce que le dashboard montre (justifie par la question)

| Visualisation | Repond a | Forme Metabase |
|---|---|---|
| Carte des PM2.5 moyens par capteur, dernieres 24h, Ile de France | Ou courir, ou eviter | Grid map, latitude et longitude binnees, couleur selon la valeur |
| Heatmap heure par jour des PM2.5 moyens sur 7 jours | Quand courir, les pics de trafic matin et soir deviennent visibles | Tableau croise avec mise en forme conditionnelle |
| Indicateurs : part des releves au dessus du seuil OMS sur 24h, meilleure heure pour courir, nombre de capteurs actifs | Constat immediat et confiance dans la mesure | Cartes number |

Chaque visualisation porte un titre et une legende autoportants.

## 6. Limites assumees et consequences sur le pipeline

1. Capteurs citoyens non calibres : les SDS011 surestiment par forte humidite et certains
   renvoient des valeurs aberrantes. C'est exactement ce que traitent les cinq regles qualite
   et la quarantaine de la zone silver. Le dashboard mesure une tendance relative fiable,
   pas une conformite reglementaire.
2. Couverture spatiale inegale : une cellule sans capteur signifie pas de donnee, jamais
   air pur. L'indicateur capteurs actifs rend cette limite visible.
3. Fenetre live de 5 minutes : la valeur du dashboard croit avec l'accumulation des runs,
   c'est assume, c'est le coeur du TP.
4. Ce dashboard est un outil d'aide a la decision d'entrainement, pas un avis medical.
