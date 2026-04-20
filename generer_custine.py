# generer_custine.py
# Custine — Sync calendrier AirBnB → Infomaniak

import warnings
import requests
import os
from datetime import datetime, timedelta
import time

warnings.filterwarnings("ignore")

GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

AIRBNB_ICAL         = "https://www.airbnb.fr/calendar/ical/48697144.ics?t=0fb51bd9065343db9f7192482c68b170"
INFOMANIAK_CAL_ID   = 2130614

def get_token():
    if GITHUB_ACTIONS:
        return os.getenv("INFOMANIAK_MAIL_TOKEN")
    from config import INFOMANIAK_MAIL_TOKEN
    return INFOMANIAK_MAIL_TOKEN

def lire_ical(url):
    print("📡 Téléchargement AirBnB Custine...")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    lignes_brutes = r.text.splitlines()
    lignes = []
    for ligne in lignes_brutes:
        if ligne.startswith(" ") or ligne.startswith("\t"):
            if lignes: lignes[-1] += ligne.strip()
        else:
            lignes.append(ligne)
    resas = []
    resa  = {}
    for ligne in lignes:
        if ligne == "BEGIN:VEVENT":
            resa = {}
        elif ligne.startswith("DTSTART"):
            resa["debut"] = datetime.strptime(ligne.split(":")[1][:8], "%Y%m%d")
        elif ligne.startswith("DTEND"):
            resa["fin"] = datetime.strptime(ligne.split(":")[1][:8], "%Y%m%d")
        elif ligne.startswith("SUMMARY"):
            resa["titre"] = ligne.split(":", 1)[1] if ":" in ligne else ""
        elif ligne == "END:VEVENT":
            if resa.get("debut") and resa.get("fin"):
                if "Reserved" in resa.get("titre", "") or "CLOSED" in resa.get("titre", ""):
                    resas.append(dict(resa))
            resa = {}
    return resas

def sync_custine():
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # Lire les réservations AirBnB
    resas = lire_ical(AIRBNB_ICAL)
    aujourd_hui = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    resas = [r for r in resas if r["fin"] >= aujourd_hui]

    # Récupérer les événements existants
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
                "calendar_id": INFOMANIAK_CAL_ID,
                "from": debut + " 00:00:00",
                "to":   fin   + " 00:00:00",
            }
        )
        raw = r.json().get("data", [])
        events += raw if isinstance(raw, list) else raw.get("events", [])
        time.sleep(2)

    # Supprimer les anciens
    for e in events:
        requests.delete(
            f"https://api.infomaniak.com/1/calendar/pim/event/{e['id']}",
            headers=headers
        )
        time.sleep(1)

    # Recréer
    time.sleep(5)
    for r in resas:
        requests.post(
            "https://api.infomaniak.com/1/calendar/pim/event",
            headers=headers,
            json={
                "title":          "Réservation Custine",
                "start":          r["debut"].strftime("%Y-%m-%d") + " 00:00:00",
                "end":            r["fin"].strftime("%Y-%m-%d")   + " 00:00:00",
                "calendar_id":    INFOMANIAK_CAL_ID,
                "freebusy":       "busy",
                "type":           "event",
                "fullday":        True,
                "timezone_start": "Europe/Paris",
                "timezone_end":   "Europe/Paris",
            }
        )
        time.sleep(1)

    print(f"✅ Custine synchronisé : {len(resas)} réservation(s)")

sync_custine()