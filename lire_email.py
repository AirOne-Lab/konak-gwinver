import imaplib
import email
import email.header
import re
import gspread
from datetime import datetime
from google.oauth2.service_account import Credentials

# ─── CONFIG ───────────────────────────────────────────────────
SHEET_ID   = "10iXoRnR08aqT1LOSS0sAXtAQP6HUuFlhZ13BQSKpQ6s"
SHEET_TAB  = "2025-26"
NOMS_KONAK = ["À l'abri des regards", "Konak", "Stang", "au bord de l'océan"]

MOIS_EMAIL = {
    "janv": 1, "févr": 2, "mars": 3, "avr": 4,
    "mai": 5, "juin": 6, "juil": 7, "août": 8,
    "sept": 9, "oct": 10, "nov": 11, "déc": 12
}
JOURS_FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
MOIS_FR  = ["janv.", "févr.", "mars", "avr.", "mai", "juin",
             "juil.", "août", "sept.", "oct.", "nov.", "déc."]

# ─── GOOGLE SHEETS ────────────────────────────────────────────
import os, json, tempfile

SCOPES = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_google_ws():
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write(creds_json)
            f.flush()
            creds = Credentials.from_service_account_file(f.name, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID).worksheet(SHEET_TAB)

def codes_existants():
    valeurs = ws.col_values(1)  # colonne ID
    return set(valeurs)

# ─── PARSER ───────────────────────────────────────────────────
def decoder_sujet(msg):
    parts = email.header.decode_header(msg['Subject'])
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or 'utf-8', errors='ignore'))
        else:
            result.append(part)
    return "".join(result)

def determiner_annee(mois):
    aujourd_hui = datetime.now()
    annee = aujourd_hui.year
    if mois < aujourd_hui.month:
        annee += 1
    return annee

def extraire_infos_airbnb(corps):
    infos = {}
    m = re.search(r'Réservation confirmée\s*:\s*(.+?)\s+arrive', corps)
    if not m:
        m = re.search(r'Subject:.*?:\s*(.+?)\s+arrive', corps)
    if m:
        infos["nom"] = m.group(1).strip()
    m = re.search(r'Arrivée\s+\w+\.\s+(\d+)\s+(\w+)\.?\s+(\d{2}:\d{2})', corps)
    if m:
        infos["arrivee_jour"] = int(m.group(1))
        infos["arrivee_mois"] = MOIS_EMAIL.get(m.group(2)[:4].lower(), 0)
        infos["arrivee_heure"] = m.group(3)
    m = re.search(r'Départ\s+\w+\.\s+(\d+)\s+(\w+)\.?\s+(\d{2}:\d{2})', corps)
    if m:
        infos["depart_jour"] = int(m.group(1))
        infos["depart_mois"] = MOIS_EMAIL.get(m.group(2)[:4].lower(), 0)
        infos["depart_heure"] = m.group(3)
    m = re.search(r'(\d+)\s+adulte', corps)
    if m:
        infos["adultes"] = int(m.group(1))
    m = re.search(r'(\d+)\s+enfant', corps)
    if m:
        infos["enfants"] = int(m.group(1))
    m = re.search(r'Code de confirmation\s+(\w+)', corps)
    if m:
        infos["code"] = m.group(1).strip()
    m = re.search(r'Vous gagnez\s+([\d\s,.]+\s*€)', corps)
    if m:
        infos["montant"] = m.group(1).strip()
    return infos

def formater_date(jour, mois, annee):
    d = datetime(annee, mois, jour)
    return f"{JOURS_FR[d.weekday()]} {d.day} {MOIS_FR[d.month-1]} {d.year}"

def ajouter_dans_sheets(ws, infos):
    annee_a = determiner_annee(infos.get("arrivee_mois", 0))
    annee_d = determiner_annee(infos.get("depart_mois", 0))
    arrivee = datetime(annee_a, infos["arrivee_mois"], infos["arrivee_jour"])
    depart  = datetime(annee_d, infos["depart_mois"],  infos["depart_jour"])
    nuits   = (depart - arrivee).days
    
    ligne = [
        infos.get("code", ""),
        infos.get("nom", ""),
        "",
        "",
        formater_date(infos["arrivee_jour"], infos["arrivee_mois"], annee_a),
        formater_date(infos["depart_jour"],  infos["depart_mois"],  annee_d),
        infos.get("arrivee_heure", ""),
        infos.get("depart_heure", ""),
        str(nuits),
        str(infos.get("adultes", "")),
        str(infos.get("enfants", "")),
        "",
        "", "", "",
        "", "",
        "",
        "", "",
        "",
        "",
        "Airbnb",
        "Airbnb",
    ]

    ws.append_row(ligne, value_input_option="USER_ENTERED")
    print(f"✅ Ajouté dans Sheets : {infos.get('nom')} ({infos.get('code')})")