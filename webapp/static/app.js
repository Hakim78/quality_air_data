// tout le front tient ici : la carte leaflet, les stats et le bandeau des creneaux
// je lis les trois endpoints de l'api et je colore selon le seuil oms

const SEUIL_OMS = 15;

function couleur(pm25) {
  if (pm25 <= SEUIL_OMS) return "#2e9e4f";
  if (pm25 <= 30) return "#e8a100";
  return "#d63b2f";
}

async function chargerJson(url) {
  const reponse = await fetch(url);
  if (!reponse.ok) throw new Error(url + " a repondu " + reponse.status);
  return reponse.json();
}

function initCarte(points) {
  const carte = L.map("carte", { scrollWheelZoom: false }).setView([48.86, 2.35], 11);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 18,
  }).addTo(carte);

  if (!points.length) return;

  // la couche de chaleur donne la lecture d'ensemble, l'intensite suit la concentration
  const chaleur = points.map(p => [p.lat, p.lon, Math.min(p.pm25 / 40, 1)]);
  L.heatLayer(chaleur, { radius: 32, blur: 24, maxZoom: 13 }).addTo(carte);

  // et un point precis par capteur pour le detail au clic
  points.forEach(p => {
    L.circleMarker([p.lat, p.lon], {
      radius: 6,
      color: "#ffffff",
      weight: 1.5,
      fillColor: couleur(p.pm25),
      fillOpacity: 0.95,
    })
      .bindPopup("<strong>" + p.pm25 + " ug/m3</strong> de PM2.5 en moyenne sur 24h"
        + (p.pm25 <= SEUIL_OMS ? "<br>sous le seuil OMS, ca court" : "<br>au dessus du seuil OMS"))
      .addTo(carte);
  });
}

function afficherStats(s) {
  document.getElementById("stat-pm25").textContent = s.pm25_moyen_24h ?? "--";
  document.getElementById("stat-seuil").textContent =
    s.pct_au_dessus_seuil == null ? "--" : s.pct_au_dessus_seuil + "%";
  document.getElementById("stat-heure").textContent =
    s.meilleure_heure == null ? "--" : s.meilleure_heure + "h";
  document.getElementById("stat-capteurs").textContent = s.capteurs_actifs ?? "--";
}

function afficherCreneaux(creneaux, meilleureHeure) {
  const parHeure = Object.fromEntries(creneaux.map(c => [c.heure, c.pm25]));
  const bloc = document.getElementById("creneaux");
  for (let h = 0; h < 24; h++) {
    const cellule = document.createElement("div");
    cellule.className = "creneau" + (h === meilleureHeure ? " meilleur" : "");
    const valeur = parHeure[h];
    const case_ = document.createElement("div");
    if (valeur == null) {
      case_.className = "creneau-case vide-case";
      case_.textContent = "-";
    } else {
      case_.className = "creneau-case";
      case_.style.background = couleur(valeur);
      case_.textContent = valeur;
    }
    const heure = document.createElement("span");
    heure.className = "creneau-heure";
    heure.textContent = h + "h";
    cellule.appendChild(case_);
    cellule.appendChild(heure);
    bloc.appendChild(cellule);
  }
}

async function demarrer() {
  try {
    const [synthese, points, creneaux] = await Promise.all([
      chargerJson("/api/synthese"),
      chargerJson("/api/carte"),
      chargerJson("/api/creneaux"),
    ]);
    initCarte(points);
    afficherStats(synthese);
    afficherCreneaux(creneaux, synthese.meilleure_heure);
    if (!points.length && !creneaux.length) {
      document.getElementById("vide").hidden = false;
    }
  } catch (erreur) {
    console.error(erreur);
    document.getElementById("vide").hidden = false;
  }
}

demarrer();
