# generer_custine.py
# Custine — Sync calendrier AirBnB → Infomaniak avec détails

import warnings
import requests
import os
import json
import imaplib
import email as email_lib
from datetime import datetime, timedelta
import time

warnings.filterwarnings("ignore")

GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"

AIRBNB_ICAL         = "https://www.airbnb.fr/calendar/ical/48697144.ics?t=0fb51bd9065343db9f7192482c68b170"
INFOMANIAK_CAL_ID   = 2130614
CUSTINE_DATA_FILE   = "custine_reservations.json"
NOMS_CUSTINE        = ["Custine", "rue Custine", "Paris 18", "75018", "magnifique 2 pièces", "coeur"]

def get_token():
    if GITHUB_ACTIONS:
        return os.getenv("INFOMANIAK_MAIL_TOKEN")
    from config import INFOMANIAK_MAIL_TOKEN
    return INFOMANIAK_MAIL_TOKEN

def lire_reservations_custine():
    """Charge les réservations depuis le fichier JSON local"""
    if os.path.exists(CUSTINE_DATA_FILE):
        with open(CUSTINE_DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def sauvegarder_reservation_custine(code, infos):
    """Sauvegarde une réservation dans le fichier JSON"""
    data = lire_reservations_custine()
    data[code] = infos
    with open(CUSTINE_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def lire_emails_custine():
    """Parse les emails de confirmation AirBnB pour Custine"""
    try:
        if GITHUB_ACTIONS:
            mail_password = os.getenv("INFOMANIAK_MAIL_PASSWORD")
        else:
            from config import INFOMANIAK_MAIL_PASSWORD
            mail_password = INFOMANIAK_MAIL_PASSWORD
        
        # Import de la fonction de parsing
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from lire_email import extraire_infos_airbnb
        
        mail = imaplib.IMAP4_SSL("mail.infomaniak.com")
        mail.login("konak-gwinver@ik.me", mail_password)
        mail.select("INBOX")
        
        _, messages = mail.search(None, 'ALL')
        nb = 0
        data_existante = lire_reservations_custine()
        
        for num in messages[0].split():
            _, data = mail.fetch(num, '(RFC822)')
            msg = email_lib.message_from_bytes(data[0][1])
            parts = email_lib.header.decode_header(msg['Subject'])
            sujet = "".join(p.decode(c or 'utf-8', errors='ignore') if isinstance(p, bytes) else p for p, c in parts)
            
        # Pour Custine, on accepte les forwards pour avoir l'historique
        # if "Fwd:" in sujet or "Tr:" in sujet or "RE:" in sujet:
        #     continue
            
            if "Réservation confirmée" not in sujet:
                continue
            
            corps = ""
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    corps = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    break
            
            # Vérifier si c'est Custine
            if not any(n in corps for n in NOMS_CUSTINE):
                continue
            
            infos = extraire_infos_airbnb(corps)
            code = infos.get("code", "")
            
            if not code or code in data_existante:
                continue
            
            # Sauvegarder
            sauvegarder_reservation_custine(code, infos)
            nb += 1
            print(f"✅ Email Custine traité : {infos.get('nom')} ({code})")
        
        mail.logout()
        if nb > 0:
            print(f"✅ {nb} nouvelle(s) réservation(s) Custine ajoutée(s)")
    
    except Exception as e:
        print(f"⚠️ Emails Custine : {e}")

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
    
    # Lire emails pour enrichir les données
    lire_emails_custine()
    
    # Charger les données des réservations
    reservations_data = lire_reservations_custine()

    # 🆕 DEBUG
    print(f"💾 JSON chargé : {len(reservations_data)} réservation(s)")
    for code, infos in reservations_data.items():
        print(f"   {code}: {infos.get('nom')} - {infos.get('arrivee_jour')}/{infos.get('arrivee_mois')}")

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

    # Recréer avec détails enrichis
    time.sleep(5)
    for r in resas:
        titre_ical = r.get("titre", "")
        titre = "Réservation Custine"
        print(f"🔍 Cherche resa pour {r['debut'].day}/{r['debut'].month}")  # DEBUG

        # Chercher dans les données par date d'arrivée
        for code, infos in reservations_data.items():
            arrivee_jour = infos.get("arrivee_jour")
            arrivee_mois = infos.get("arrivee_mois")
            print(f"   Compare avec {code}: {arrivee_jour}/{arrivee_mois}")  # DEBUG

            if arrivee_jour and arrivee_mois:
                if r["debut"].day == arrivee_jour and r["debut"].month == arrivee_mois:
                    print(f"   ✅ MATCH TROUVÉ ! {code}")  # 🆕 DEBUG
                    nom = infos.get("nom", "")
                    adultes = infos.get("adultes", 0)
                    enfants = infos.get("enfants", 0)
                    
                    details = []
                    if adultes:
                        details.append(f"{adultes} adulte{'s' if adultes > 1 else ''}")
                    if enfants:
                        details.append(f"{enfants} enfant{'s' if enfants > 1 else ''}")
                    
                    if details:
                        titre = f"{nom} - {' - '.join(details)} [Custine]"
                    else:
                        titre = f"{nom} [Custine]"
                    break
        
        # Fallback sur titre iCal si pas trouvé dans les données
        if titre == "Réservation Custine" and "Reserved for" in titre_ical:
            nom = titre_ical.replace("Reserved for", "").strip()
            titre = f"{nom} [Custine]"
        
        # 🆕 DEBUG - Afficher le titre final
        print(f"   📝 Titre final : {titre}")      
        
        resp = requests.post(
            "https://api.infomaniak.com/1/calendar/pim/event",
            headers=headers,
            json={
                "title":          titre,
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

        # 🆕 DEBUG - Vérifier le status
        print(f"   Status POST: {resp.status_code}")
        time.sleep(1)

    print(f"✅ Custine synchronisé : {len(resas)} réservation(s)")

sync_custine()