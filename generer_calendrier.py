# generer_calendrier.py
# Konak Gwinver — Génère calendrier_prestataires.html + .ics

import warnings
import requests
import csv
import io
import json
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")

AIRBNB_ICAL  = "https://www.airbnb.fr/calendar/ical/50521285.ics?t=7c5371b4a5ee43ae8516110449d3fd45"
BOOKING_ICAL = "https://ical.booking.com/v1/export/t/27f1af14-7ccd-4175-8421-08a4b8132bda.ics"
GREENGO_ICAL = "https://calendars.greengo.voyage/calendar/greengo-icalendar/fffaa45c-3093-408a-95c4-92f2811c3672.ics"
SHEETS_CSV   = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQkgs-a_GuintVIJofGGwKzpRLbr1d208HkP8O_62gkI-vQFLPPdq2REww7MLJKidqft8KYiSh6Zyfl/pub?gid=653745516&single=true&output=csv"

MOIS = {
    "janv.": 1, "févr.": 2, "mars": 3, "avr.": 4,
    "mai": 5, "juin": 6, "juil.": 7, "août": 8,
    "sept.": 9, "oct.": 10, "nov.": 11, "déc.": 12
}


def lire_calendrier(url, source):
    print(f"📡 Téléchargement {source}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    lignes_brutes = response.text.splitlines()
    lignes = []
    for ligne in lignes_brutes:
        if ligne.startswith(" ") or ligne.startswith("\t"):
            if lignes: lignes[-1] += ligne.strip()
        else:
            lignes.append(ligne)
    reservations = []
    resa = {}
    for ligne in lignes:
        if ligne == "BEGIN:VEVENT":
            resa = {"source": source}
        elif ligne.startswith("DTSTART"):
            resa["debut"] = datetime.strptime(ligne.split(":")[1][:8], "%Y%m%d")
        elif ligne.startswith("DTEND"):
            resa["fin"] = datetime.strptime(ligne.split(":")[1][:8], "%Y%m%d")
        elif ligne.startswith("SUMMARY"):
            resa["titre"] = ligne.split(":", 1)[1] if ":" in ligne else ""
        elif ligne.startswith("DESCRIPTION:"):
            resa["note"] = ligne[12:]
        elif ligne == "END:VEVENT":
            if resa.get("debut") and resa.get("fin"):
                reservations.append(dict(resa))
            resa = {}
    return reservations


def detecter_doublons(reservations):
    doublons_indices = set()
    for i in range(len(reservations)):
        for j in range(i + 1, len(reservations)):
            a, b = reservations[i], reservations[j]
            if a["source"] != b["source"]:
                if a["debut"] < b["fin"] and a["fin"] > b["debut"]:
                    doublons_indices.add(j)
    return [r for i, r in enumerate(reservations) if i not in doublons_indices]


def lire_google_sheets():
    print("📡 Téléchargement Google Sheets...")
    response = requests.get(SHEETS_CSV)
    response.encoding = "utf-8"
    lignes = response.text.splitlines()
    return list(csv.DictReader(io.StringIO("\n".join(lignes[2:]))))


def parser_date_sheets(texte):
    try:
        parties = texte.strip().split()
        jour  = int(parties[1])
        mois  = MOIS.get(parties[2], 0)
        annee = int(parties[3])
        if mois == 0: return None
        return datetime(annee, mois, jour)
    except:
        return None


def short_nom(nom):
    if not nom: return ""
    p = nom.strip().split()
    return p[0] + " " + p[-1][0] + "." if len(p) >= 2 else nom


def formater_sejour(sejour):
    prenom_nom = sejour.get("Prénom, Nom", "")
    adultes    = sejour.get("Nombre adultes", "").strip()
    enfants    = sejour.get("Nombre Enfants", "").strip()
    animaux    = sejour.get("Animaux", "").strip()
    source     = sejour.get("Source", "").strip()
    #nom = short_nom(prenom_nom)
    nom = prenom_nom

    details = []
    if adultes.isdigit(): details.append(f"{adultes} adulte{'s' if int(adultes)>1 else ''}")
    if enfants.isdigit(): details.append(f"{enfants} enfant{'s' if int(enfants)>1 else ''}")
    if animaux: details.append("🐕")
    parties = [nom] + details
    label = " - ".join(parties)
    return f"{label} [{source}]" if source else label


def generer_ics(evenements):
    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Konak Gwinver//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Konak Gwinver - Le Stang",
        "X-WR-TIMEZONE:Europe/Paris",
    ]
    for e in evenements:
        debut   = datetime.strptime(e["debut"], "%Y-%m-%d")
        fin     = datetime.strptime(e["fin"],   "%Y-%m-%d")
        uid     = f"{e['debut']}-{e['fin']}-{e['type']}@konak-gwinver"
        summary = e["nom"] if e["nom"] else ("Réservation" if e["type"] == "resa" else "Indisponible")
        lignes += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART;VALUE=DATE:{debut.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{fin.strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DTSTAMP:{datetime.now().strftime('%Y%m%dT%H%M%SZ')}",
            "END:VEVENT",
        ]
    lignes.append("END:VCALENDAR")
    return "\r\n".join(lignes)


# ─── CHARGEMENT ───────────────────────────────────────────────
resas = (lire_calendrier(AIRBNB_ICAL, "AirBnB") +
         lire_calendrier(BOOKING_ICAL, "Booking") +
         lire_calendrier(GREENGO_ICAL, "GreenGo"))
resas = detecter_doublons(resas)

sejours     = lire_google_sheets()
aujourd_hui = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

index_sejours = {}
for s in sejours:
    d_arrivee = parser_date_sheets(s.get("Arrivée\nJour", ""))
    d_depart  = parser_date_sheets(s.get("Départ\nJour", ""))
    if d_arrivee and d_depart and d_depart >= aujourd_hui:
        index_sejours[d_arrivee] = s

# ─── ENRICHISSEMENT ───────────────────────────────────────────
evenements = []
for r in resas:
    titre    = r.get("titre", "")
    est_resa = "Reserved" in titre or "CLOSED" in titre

    sejour = index_sejours.get(r["debut"])
    if sejour is None and est_resa:
        for delta in [1, -1]:
            sejour = index_sejours.get(r["debut"] + timedelta(days=delta))
            if sejour: break

    if sejour:
        nom        = formater_sejour(sejour)
        type_event = "resa"
    elif est_resa:
        nom        = "À compléter"
        type_event = "resa"
    else:
        nom        = ""
        type_event = "bloque"

    evenements.append({
        "debut": r["debut"].strftime("%Y-%m-%d"),
        "fin":   r["fin"].strftime("%Y-%m-%d"),
        "nom":   nom,
        "type":  type_event,
    })

evenements_json = json.dumps(evenements, ensure_ascii=False)

# ─── GÉNÉRATION ICS ───────────────────────────────────────────
with open("calendrier_prestataires.ics", "w", encoding="utf-8") as f:
    f.write(generer_ics(evenements))
print("✅ ICS généré    : calendrier_prestataires.ics")

# ─── GÉNÉRATION HTML ──────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Konak Gwinver — Calendrier</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap');
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'DM Sans', sans-serif; background: #F6F4EF; color: #2C2C2A; min-height: 100vh; padding: 2rem; }}
  .container {{ max-width: 1100px; margin: 0 auto; }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem; }}
  .header-left h1 {{ font-size: 30px; font-weight: 600; color: #2C2C2A; }}
  .header-left p  {{ font-size: 13px; color: #888780; margin-top: 3px; }}
  .nav {{ display: flex; align-items: center; gap: 10px; }}
  .nav-btn {{ background: white; border: 1px solid #D3D1C7; border-radius: 8px; padding: 8px 18px; cursor: pointer; font-size: 18px; font-family: inherit; color: #2C2C2A; transition: background .15s; }}
  .nav-btn:hover {{ background: #EEECEA; }}
  .month-label {{ font-size: 20px; font-weight: 500; min-width: 160px; text-align: center; }}
  .day-labels {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 4px; }}
  .day-label {{ text-align: center; font-size: 16px; color: #888780; padding: 6px 0; font-weight: 500; }}
.cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; overflow: hidden; }}  .day {{ min-height: 120px; border-radius: 8px; padding: 6px 0; background: white; overflow: visible; position: relative; border: 1px solid #EEECEA; }}
  .day.other-month {{ opacity: 0.25; }}
  .day.today {{ border: 2px solid #378ADD; }}
  .day-num {{ font-size: 16px; color: #888780; padding: 0 8px; margin-bottom: 3px; font-weight: 500; }}
  .legend {{ display: flex; gap: 20px; margin-top: 1.5rem; flex-wrap: wrap; }}
  .legend-item {{ display: flex; align-items: center; gap: 8px; font-size: 16px; color: #5F5E5A; }}
  .legend-dot {{ width: 28px; height: 14px; border-radius: 7px; }}
  .updated {{ font-size: 14px; color: #B4B2A9; margin-top: 1.5rem; text-align: right; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="header-left">
      <h1>🏠 Konak Gwinver - Le Stang</h1>
      <p>Calendrier réservations</p>
    </div>
    <div class="nav">
      <button class="nav-btn" onclick="changeMonth(-1)">&#8592;</button>
      <span class="month-label" id="month-label"></span>
      <button class="nav-btn" onclick="changeMonth(1)">&#8594;</button>
    </div>
  </div>
  <div class="day-labels" id="day-labels"></div>
  <div class="cal-grid" id="cal-grid"></div>
  <div class="legend">
    <div class="legend-item"><div class="legend-dot" style="background:#9FE1CB;"></div> Réservation</div>
    <div class="legend-item"><div class="legend-dot" style="background:#D3D1C7;"></div> Indisponible</div>
  </div>
  <div class="updated">Mis à jour le {datetime.now().strftime("%d/%m/%Y à %Hh%M")}</div>
</div>

<script>
const JOURS    = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
const MOIS_NOM = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
const reservations = {evenements_json};
const COLORS = {{ resa: {{ bg:'#9FE1CB', text:'#085041' }}, bloque: {{ bg:'#D3D1C7', text:'#444441' }} }};

let currentYear  = new Date().getFullYear();
let currentMonth = new Date().getMonth();

function d0(date) {{ const d = new Date(date); d.setHours(0,0,0,0); return d; }}
function ts(date) {{ return d0(date).getTime(); }}

function render() {{
  document.getElementById('month-label').textContent = MOIS_NOM[currentMonth] + ' ' + currentYear;
  document.getElementById('day-labels').innerHTML = JOURS.map(j => `<div class="day-label">${{j}}</div>`).join('');
  const grid = document.getElementById('cal-grid');
  grid.innerHTML = '';

  const first = new Date(currentYear, currentMonth, 1);
  const last  = new Date(currentYear, currentMonth+1, 0);
  let startDow = first.getDay();
  startDow = startDow === 0 ? 6 : startDow - 1;

  const cells = [];
  for (let i = 0; i < startDow; i++)
    cells.push({{ date: new Date(currentYear, currentMonth, -startDow+i+1), inMonth: false }});
  for (let d = 1; d <= last.getDate(); d++)
    cells.push({{ date: new Date(currentYear, currentMonth, d), inMonth: true }});
  while (cells.length % 7 !== 0)
    cells.push({{ date: new Date(currentYear, currentMonth+1, cells.length-startDow-last.getDate()+1), inMonth: false }});

  const today = new Date(); today.setHours(0,0,0,0);
  const cellEls = cells.map(cell => {{
    const el = document.createElement('div');
    el.className = 'day' + (!cell.inMonth ? ' other-month' : '');
    if (d0(cell.date).getTime() === today.getTime()) el.classList.add('today');
    el.innerHTML = `<div class="day-num">${{cell.date.getDate()}}</div>`;
    grid.appendChild(el);
    return el;
  }});

const GAP = 4, BAR_H = 28, BASE_TOP = 34, TRACK_H = 32;

  reservations.forEach((r, ri) => {{
    const tDebut = ts(new Date(r.debut));
    const tFin   = ts(new Date(r.fin));
    const c      = COLORS[r.type];
    const label  = r.nom || (r.type === 'bloque' ? 'Indisponible' : '');
    const track  = ri % 2;
    const top    = BASE_TOP + track * TRACK_H;

    // Pour chaque ligne de la grille, trouver le premier idx du séjour
    // (arrivée ou mid) pour y placer le label
    const labelByRow = {{}};
    cells.forEach((cell, idx) => {{
      if (!cell.inMonth) return;
      const t   = ts(cell.date);
      const row = Math.floor(idx / 7);
      // inclure le jour d'arrivée (demi-case droite) et les jours mid
      if (t >= tDebut && t < tFin && !(row in labelByRow)) {{
        labelByRow[row] = idx;
      }}
    }});

    cells.forEach((cell, idx) => {{
      if (!cell.inMonth) return;
      const t   = ts(cell.date);
      const col = idx % 7;
      const row = Math.floor(idx / 7);

      let role = 'none';
      if (t === tDebut)                role = 'arrive';
      else if (t === tFin)             role = 'depart';
      else if (t > tDebut && t < tFin) role = 'mid';
      if (role === 'none') return;

      // Barre colorée
      const bar = document.createElement('div');
      bar.title = label;
      bar.style.cssText = `position:absolute;top:${{top}}px;height:${{BAR_H}}px;background:${{c.bg}};z-index:3;cursor:default;`;

      if (role === 'arrive') {{
        bar.style.left         = '50%';
        bar.style.right        = col === 6 ? '0' : (-GAP) + 'px';
        bar.style.borderRadius = '10px 0 0 10px';
      }} else if (role === 'depart') {{
        bar.style.left         = col === 0 ? '0' : (-GAP) + 'px';
        bar.style.right        = '50%';
        bar.style.borderRadius = '0 10px 10px 0';
      }} else {{
        bar.style.left         = col === 0 ? '0' : (-GAP) + 'px';
        bar.style.right        = col === 6 ? '0' : (-GAP) + 'px';
        bar.style.borderRadius = '0';
      }}
      cellEls[idx].appendChild(bar);

      // Label : premier idx du séjour sur cette ligne
   if (labelByRow[row] === idx) {{
        const txt = document.createElement('div');
        txt.textContent = label;
        txt.title = label;
        txt.style.cssText = `position:absolute;top:${{top + 3}}px;` +
          (role === 'arrive' ? `left:calc(50% + 6px);` : `left:6px;`) +
          `height:${{BAR_H - 6}}px;line-height:${{BAR_H - 6}}px;` +
          `font-size:14px;font-weight:500;color:${{c.text}};` +
          `white-space:nowrap;overflow:visible;z-index:5;pointer-events:none;`;
        cellEls[idx].appendChild(txt);
      }}
    }});
  }});
}}

function changeMonth(dir) {{
  currentMonth += dir;
  if (currentMonth > 11) {{ currentMonth = 0; currentYear++; }}
  if (currentMonth < 0)  {{ currentMonth = 11; currentYear--; }}
  render();
}}

render();
</script>
</body>
</html>"""

with open("calendrier_prestataires.html", "w", encoding="utf-8") as f:
    f.write(html)
print("✅ HTML généré   : calendrier_prestataires.html")
print(f"   {len(evenements)} événements intégrés")