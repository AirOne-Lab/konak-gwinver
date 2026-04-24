# generer_calendrier.py
# Konak Gwinver — Génère calendrier_reservations.html + .ics

import warnings
import requests
import csv
import io
import json
import subprocess
import os
from datetime import datetime, timedelta

import imaplib
import email as email_lib
import email.header
import re
import gspread
from google.oauth2.service_account import Credentials

warnings.filterwarnings("ignore")

from lire_email import extraire_infos_airbnb, ajouter_dans_sheets, formater_date, determiner_annee, MOIS_EMAIL, JOURS_FR, MOIS_FR, NOMS_KONAK

GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

AIRBNB_ICAL   = "https://www.airbnb.fr/calendar/ical/50521285.ics?t=7c5371b4a5ee43ae8516110449d3fd45"
BOOKING_ICAL  = "https://ical.booking.com/v1/export/t/27f1af14-7ccd-4175-8421-08a4b8132bda.ics"
GREENGO_ICAL  = "https://calendars.greengo.voyage/calendar/greengo-icalendar/fffaa45c-3093-408a-95c4-92f2811c3672.ics"
BLOCAGES_ICAL = "https://sync.infomaniak.com/calendars/EG06668/05054034-6697-481d-a546-c246c41eb8b4?export"
SHEETS_CSV    = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQkgs-a_GuintVIJofGGwKzpRLbr1d208HkP8O_62gkI-vQFLPPdq2REww7MLJKidqft8KYiSh6Zyfl/pub?gid=653745516&single=true&output=csv"

INFOMANIAK_CALENDAR_ID = 2128878

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
    nom = prenom_nom
    details = []
    if adultes.isdigit(): details.append(f"{adultes} adulte{'s' if int(adultes)>1 else ''}")
    if enfants.isdigit(): details.append(f"{enfants} enfant{'s' if int(enfants)>1 else ''}")
    if animaux: details.append("🐕")
    parties = [nom] + details
    label = " - ".join(parties)
    return f"{label} [{source}]" if source else label


def generer_ics(evenements):
    evenements_ics = [e for e in evenements if e["type"] in ("resa", "bloque")]
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


def sync_infomaniak(evenements):

    for e in evenements:
        if e["type"] not in ("resa",):
            continue
        
    if GITHUB_ACTIONS:
        token = os.getenv("INFOMANIAK_MAIL_TOKEN")
    else:
        from config import INFOMANIAK_MAIL_TOKEN
        token = INFOMANIAK_MAIL_TOKEN

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Récupérer les événements existants par tranches de 3 mois
    import time
    events = []
    tranches = [
        ("2026-01-01", "2026-03-31"),
        ("2026-04-01", "2026-06-30"),
        ("2026-07-01", "2026-09-30"),
        ("2026-10-01", "2026-12-31"),
        ("2027-01-01", "2027-03-31"),
        ("2027-04-01", "2027-06-30"),
        ("2027-07-01", "2027-09-30"),
        ("2027-10-01", "2027-12-31"),
    ]
    for debut, fin in tranches:
        r = requests.get(
            "https://api.infomaniak.com/1/calendar/pim/event",
            headers=headers,
            params={
                "calendar_id": INFOMANIAK_CALENDAR_ID,
                "from": debut + " 00:00:00",
                "to":   fin   + " 00:00:00",
            }
        )
        raw = r.json().get("data", [])
        events += raw if isinstance(raw, list) else raw.get("events", [])
        time.sleep(2)

    # Supprimer les événements existants créés par le script
    TITRES_SCRIPT = ["À compléter"]
    KEYWORDS_SCRIPT = ["adulte", "enfant", "🐕", "[Airbnb]", "[Booking]", "[GreenGo]", "[Karin Minor]", "[Direct]", "À compléter"]
    for e in events:
        titre = e.get("title", "")
        if titre in TITRES_SCRIPT or any(k in titre for k in KEYWORDS_SCRIPT):
            requests.delete(
                f"https://api.infomaniak.com/1/calendar/pim/event/{e['id']}",
                headers=headers
            )
            time.sleep(2)

    # Recréer tous les événements
    for e in evenements:
        if e["type"] != "resa":
            continue
        titre = e["nom"] if e["nom"] else "À compléter"
        resp = requests.post(
            "https://api.infomaniak.com/1/calendar/pim/event",
            headers=headers,
            json={
                "title":          titre,
                "start":          e["debut"] + " 00:00:00",
                "end":            e["fin"]   + " 00:00:00",
                "calendar_id":    INFOMANIAK_CALENDAR_ID,
                "freebusy":       "busy",
                "type":           "event",
                "fullday":        True,
                "timezone_start": "Europe/Paris",
                "timezone_end":   "Europe/Paris",
            }
        )
        time.sleep(2)
 

    nb_resas = len([e for e in evenements if e["type"] == "resa"])
    print(f"✅ Infomaniak synchronisé : {nb_resas} réservation(s)")

# Calcul des tracks (anti-superposition)
def calculer_tracks(evenements):
    tracks = []
    for i, e in enumerate(evenements):
        debut_i = datetime.strptime(e["debut"], "%Y-%m-%d")
        fin_i   = datetime.strptime(e["fin"],   "%Y-%m-%d")
        track_utilises = set()
        for j, prev in enumerate(evenements[:i]):
            debut_j = datetime.strptime(prev["debut"], "%Y-%m-%d")
            fin_j   = datetime.strptime(prev["fin"],   "%Y-%m-%d")
            if debut_i < fin_j and fin_i > debut_j:
                track_utilises.add(tracks[j])
        track = 0
        while track in track_utilises:
            track += 1
        tracks.append(track)
    return tracks



def push_github():
    try:
        repo_path = "/Users/airone/Documents/Konak-Bot"
        subprocess.run(["git", "-C", repo_path, "add",
            "calendrier_reservations.html",
            "calendrier_reservations.ics"], check=True)
        subprocess.run(["git", "-C", repo_path, "commit", "-m",
            f"Mise à jour calendrier {datetime.now().strftime('%d/%m/%Y %H:%M')}"], check=True)
        subprocess.run(["git", "-C", repo_path, "push", "--force", "origin", "main"], check=True)
        print("✅ GitHub mis à jour")
    except subprocess.CalledProcessError as e:
        print(f"⚠️  GitHub : rien à pousser ou erreur ({e})")





def lire_nouveaux_emails():
    try:
        from config import INFOMANIAK_MAIL_PASSWORD
        SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds  = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
        gc     = gspread.authorize(creds)
        from lire_email import get_google_ws
        ws = get_google_ws()        
        codes  = set(ws.col_values(1))

        mail = imaplib.IMAP4_SSL("mail.infomaniak.com")
        mail.login("konak-gwinver@ik.me", INFOMANIAK_MAIL_PASSWORD)
        mail.select("INBOX")
        _, messages = mail.search(None, 'ALL')
        nb = 0
        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg   = email_lib.message_from_bytes(data[0][1])
            parts = email.header.decode_header(msg['Subject'])
            sujet = "".join(p.decode(c or 'utf-8', errors='ignore') if isinstance(p, bytes) else p for p, c in parts)
            if "Réservation confirmée" not in sujet:
                continue
            corps = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    corps = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
            NOMS_KONAK = ["À l'abri des regards", "Konak", "Stang", "au bord de l'océan"]
            if not any(n in corps for n in NOMS_KONAK):
                continue
            infos = extraire_infos_airbnb(corps)
            code  = infos.get("code", "")
            if not code or code in codes:
                continue
            ajouter_dans_sheets(ws, infos)
            nb += 1
        mail.logout()
        print(f"✅ Emails traités : {nb} nouvelle(s) réservation(s) ajoutée(s)")
    except Exception as e:
        print(f"⚠️  Emails : {e}")




# ─── CHARGEMENT ───────────────────────────────────────────────
resas = (lire_calendrier(AIRBNB_ICAL,  "AirBnB") +
         lire_calendrier(BOOKING_ICAL, "Booking") +
         lire_calendrier(GREENGO_ICAL, "GreenGo"))
resas = detecter_doublons(resas)

blocages_perso = lire_calendrier(BLOCAGES_ICAL, "Perso")
blocages_perso = [r for r in blocages_perso if any(
    kw in r.get("titre", "")
    for kw in ["Perso", "M&C", "JC"]
)]
resas = resas + blocages_perso

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
    titre     = r.get("titre", "")
    est_resa  = "Reserved" in titre or "CLOSED" in titre
    est_perso = r.get("source") == "Perso"

    titre_low = titre.lower()
    if "m&c - intervention" in titre_low:
        nom, type_event = "M&C - Intervention", "mc_intervention"
    elif "m&c - indispo" in titre_low:
        nom, type_event = "M&C - Indispo", "mc_indispo"
    elif "jc - intervention" in titre_low:
        nom, type_event = "JC - Intervention", "jc_intervention"
    elif "jc - indispo" in titre_low:
        nom, type_event = "JC - Indispo", "jc_indispo"
    elif est_perso:
        nom        = titre.replace("Perso - ", "").replace("Perso -", "").strip()
        type_event = "bloque"
    else:
        sejour = index_sejours.get(r["debut"])
        if sejour is None and est_resa:
            for delta in [1, -1]:
                sejour = index_sejours.get(r["debut"] + timedelta(days=delta))
                if sejour: break
        if sejour:
            nom, type_event = formater_sejour(sejour), "resa"
        elif est_resa:
            nom, type_event = "À compléter", "resa"
        else:
            nom, type_event = "", "bloque"

    evenements.append({
        "debut": r["debut"].strftime("%Y-%m-%d"),
        "fin":   r["fin"].strftime("%Y-%m-%d"),
        "nom":   nom,
        "type":  type_event,
    })


# Calcul des tracks (anti-superposition)
def calculer_tracks(evenements):
    tracks = []
    for i, e in enumerate(evenements):
        debut_i = datetime.strptime(e["debut"], "%Y-%m-%d")
        fin_i   = datetime.strptime(e["fin"],   "%Y-%m-%d")
        track_utilises = set()
        for j, prev in enumerate(evenements[:i]):
            debut_j = datetime.strptime(prev["debut"], "%Y-%m-%d")
            fin_j   = datetime.strptime(prev["fin"],   "%Y-%m-%d")
            if debut_i < fin_j and fin_i > debut_j:
                track_utilises.add(tracks[j])
        track = 0
        while track in track_utilises:
            track += 1
        tracks.append(track)
    return tracks

tracks = calculer_tracks(evenements)
for i, e in enumerate(evenements):
    e["track"] = tracks[i]


evenements_json = json.dumps(evenements, ensure_ascii=False)

# ─── GÉNÉRATION ICS ───────────────────────────────────────────
with open("calendrier_reservations.ics", "w", encoding="utf-8") as f:
    f.write(generer_ics(evenements))
print("✅ ICS généré    : calendrier_reservations.ics")

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
  .cal-grid {{ display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; overflow: hidden; }}
  .day {{ min-height: 120px; border-radius: 8px; padding: 6px 0; background: white; overflow: visible; position: relative; border: 1px solid #EEECEA; }}
  .day.other-month {{ opacity: 0.25; }}
  .day.today {{ border: 2px solid #378ADD; }}
  .hatched {{ background: repeating-linear-gradient(45deg, var(--hatch-color) 0px, var(--hatch-color) 4px, transparent 4px, transparent 10px) !important; }}
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
    <div class="legend-item"><div class="legend-dot" style="background:#F5D76E;"></div> Madeleine & Claude - Intervention</div>
    <div class="legend-item"><div class="legend-dot" style="background:repeating-linear-gradient(45deg,#F1948A 0px,#F1948A 4px,rgba(255,255,255,0.4) 4px,rgba(255,255,255,0.4) 10px);"></div> Madeleine & Claude Indisponibles</div>
    <div class="legend-item"><div class="legend-dot" style="background:#7FB3D3;"></div> Jean-Christophe - Intervention</div>
    <div class="legend-item"><div class="legend-dot" style="background:repeating-linear-gradient(45deg,#F0A87B 0px,#F0A87B 4px,rgba(255,255,255,0.4) 4px,rgba(255,255,255,0.4) 10px);"></div> Jean-Christophe Indisponible</div>
  </div>
  <div class="updated">Mis à jour le {datetime.now().strftime("%d/%m/%Y à %Hh%M")}</div>
</div>

<script>
const JOURS    = ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'];
const MOIS_NOM = ['Janvier','Février','Mars','Avril','Mai','Juin','Juillet','Août','Septembre','Octobre','Novembre','Décembre'];
const reservations = {evenements_json};
const COLORS = {{
  resa:           {{ bg:'#9FE1CB', text:'#085041' }},
  bloque:         {{ bg:'#D3D1C7', text:'#444441' }},
  mc_intervention:{{ bg:'#F5D76E', text:'#7D6608' }},
  mc_indispo:     {{ bg:'#F1948A', text:'#7B241C', hatched:true }},
  jc_intervention:{{ bg:'#7FB3D3', text:'#1A5276' }},
  jc_indispo:     {{ bg:'#F0A87B', text:'#784212', hatched:true }},
}};

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

const GAP = 4, BAR_H = 26, BASE_TOP = 34, TRACK_H = 30;

  reservations.forEach((r, ri) => {{
    const tDebut = ts(new Date(r.debut));
    const tFin   = ts(new Date(r.fin));
    const c      = COLORS[r.type];
    const label  = r.nom || (r.type === 'bloque' ? 'Indisponible' : '');
   
    
    const track  = r.track || 0;
    const top    = BASE_TOP + track * TRACK_H;

    const labelByRow = {{}};
    const estJourneeUnique = tDebut === tFin - 86400000;
    cells.forEach((cell, idx) => {{
      if (!cell.inMonth) return;
      const t   = ts(cell.date);
      const row = Math.floor(idx / 7);
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

      const bar = document.createElement('div');
      bar.title = label;
      bar.style.cssText = `position:absolute;top:${{top}}px;height:${{BAR_H}}px;background:${{c.bg}};z-index:3;cursor:default;`;
      if (c.hatched) {{
          bar.style.background = `repeating-linear-gradient(45deg, ${{c.bg}} 0px, ${{c.bg}} 4px, rgba(255,255,255,0.4) 4px, rgba(255,255,255,0.4) 10px)`;
      }}
      if (role === 'arrive') {{
        if (estJourneeUnique) {{
          bar.style.left         = col === 0 ? '0' : (-GAP) + 'px';
          bar.style.right        = col === 6 ? '0' : (-GAP) + 'px';
          bar.style.borderRadius = '10px';
        }} else {{
          bar.style.left         = '50%';
          bar.style.right        = col === 6 ? '0' : (-GAP) + 'px';
          bar.style.borderRadius = '10px 0 0 10px';
        }}
      }} else if (role === 'depart') {{
        bar.style.left         = col === 0 ? '0' : (-GAP) + 'px';
        bar.style.right        = '50%';
        bar.style.borderRadius = '0 10px 10px 0';
      }} else {{
        bar.style.left         = col === 0 ? '0' : (-GAP) + 'px';
        bar.style.right        = col === 6 ? '0' : (-GAP) + 'px';
        bar.style.borderRadius = '0';
      }}
      if (role === 'depart' && estJourneeUnique) return;
      cellEls[idx].appendChild(bar);

      if (labelByRow[row] === idx) {{
        const txt = document.createElement('div');
        txt.textContent = label;
        txt.title = label;
        txt.style.cssText = `position:absolute;top:${{top + 3}}px;` +
        (role === 'arrive' && !estJourneeUnique ? `left:calc(50% + 6px);` : `left:6px;`) +
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

with open("calendrier_reservations.html", "w", encoding="utf-8") as f:
    f.write(html)
print("✅ HTML généré   : calendrier_reservations.html")
print(f"   {len(evenements)} événements intégrés")

# ─── PUSH GITHUB ──────────────────────────────────────────────
if not GITHUB_ACTIONS:
    push_github()

# ─── SYNC INFOMANIAK ──────────────────────────────────────────
sync_infomaniak(evenements)

lire_nouveaux_emails()
