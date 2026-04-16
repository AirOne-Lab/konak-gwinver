# konak_calendrier.py
# Konak Gwinver — Calendrier unifié AirBnB + Booking + GreenGo

import warnings
import requests
import csv
import io
from datetime import datetime

# Supprimer le warning SSL
warnings.filterwarnings("ignore")

# --- Liens iCal ---
AIRBNB_ICAL  = "https://www.airbnb.fr/calendar/ical/50521285.ics?t=7c5371b4a5ee43ae8516110449d3fd45"
BOOKING_ICAL = "https://ical.booking.com/v1/export/t/27f1af14-7ccd-4175-8421-08a4b8132bda.ics"
GREENGO_ICAL = "https://calendars.greengo.voyage/calendar/greengo-icalendar/fffaa45c-3093-408a-95c4-92f2811c3672.ics"

# --- Google Sheets ---
SHEETS_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQkgs-a_GuintVIJofGGwKzpRLbr1d208HkP8O_62gkI-vQFLPPdq2REww7MLJKidqft8KYiSh6Zyfl/pub?gid=653745516&single=true&output=csv"

# --- Conversion mois français ---
MOIS = {
    "janv.": 1, "févr.": 2, "mars": 3, "avr.": 4,
    "mai": 5, "juin": 6, "juil.": 7, "août": 8,
    "sept.": 9, "oct.": 10, "nov.": 11, "déc.": 12
}


def lire_calendrier(url, source):
    print(f"📡 Téléchargement {source}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    contenu = response.text

    # Assembler les lignes continues (iCal fold/unfold)
    lignes_brutes = contenu.splitlines()
    lignes = []
    for ligne in lignes_brutes:
        if ligne.startswith(" ") or ligne.startswith("\t"):
            if lignes:
                lignes[-1] += ligne.strip()
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
            resa["titre"] = ligne.split(":", 1)[1] if ":" in ligne else "Réservation"
        elif ligne.startswith("DESCRIPTION:"):
            resa["note"] = ligne[12:]
        elif ligne == "END:VEVENT":
            if resa:
                reservations.append(resa)
    return reservations


def detecter_doublons(reservations):
    doublons_indices = set()
    doublons_info = []
    for i in range(len(reservations)):
        for j in range(i + 1, len(reservations)):
            a = reservations[i]
            b = reservations[j]
            if a["source"] != b["source"]:
                if a["debut"] < b["fin"] and a["fin"] > b["debut"]:
                    doublons_indices.add(j)
                    doublons_info.append((a, b))
    uniques = [r for i, r in enumerate(reservations) if i not in doublons_indices]
    return uniques, doublons_info


def lire_google_sheets():
    print("📡 Téléchargement Google Sheets...")
    response = requests.get(SHEETS_CSV)
    response.encoding = "utf-8"
    lignes = response.text.splitlines()
    contenu_propre = "\n".join(lignes[2:])
    lecteur = csv.DictReader(io.StringIO(contenu_propre))
    return list(lecteur)


def parser_date_sheets(texte):
    try:
        parties = texte.strip().split()
        jour = int(parties[1])
        mois = MOIS.get(parties[2], 0)
        annee = 2026 if mois >= 4 else 2027
        return datetime(annee, mois, jour)
    except:
        return None


# ─── CHARGEMENT ───────────────────────────────────────────────
resas_airbnb  = lire_calendrier(AIRBNB_ICAL,  "AirBnB")
resas_booking = lire_calendrier(BOOKING_ICAL, "Booking")
resas_greengo = lire_calendrier(GREENGO_ICAL, "GreenGo")
reservations  = resas_airbnb + resas_booking + resas_greengo

sejours = lire_google_sheets()

# ─── DÉDOUBLONNAGE ────────────────────────────────────────────
uniques, doublons = detecter_doublons(reservations)
reservations_triees = sorted(uniques, key=lambda r: r["debut"])

# ─── INDEX GOOGLE SHEETS par date d'arrivée ───────────────────
index_sejours = {}
for s in sejours:
    date = parser_date_sheets(s.get("Arrivée\nJour", ""))
    if date:
        index_sejours[date] = s

# ─── AFFICHAGE ────────────────────────────────────────────────
if doublons:
    print("\n⚠️  Doublons détectés (même résa sur plusieurs plateformes) :")
    for a, b in doublons:
        print(f"   → {b['source']} {b['debut'].strftime('%d/%m/%Y')}→{b['fin'].strftime('%d/%m/%Y')} "
              f"fusionné avec {a['source']}")

print(f"\n🏠 Konak Gwinver — {len(reservations_triees)} événements\n")
print(f"{'Début':<12} {'Fin':<12} {'Source':<10} {'Type':<25} {'Locataire / Info'}")
print("-" * 85)

for r in reservations_triees:
    debut  = r["debut"].strftime("%d/%m/%Y")
    fin    = r["fin"].strftime("%d/%m/%Y")
    sejour = index_sejours.get(r["debut"])
    if sejour:
        nom = sejour.get("Prénom, Nom", "")
        tel = sejour.get("Téléphone", "")
        info = f"{nom} | {tel}"
    else:
        info = r.get("note", "").replace("\\n", " | ")
    print(f"{debut:<12} {fin:<12} {r.get('source','?'):<10} {r.get('titre','?'):<25} {info}")