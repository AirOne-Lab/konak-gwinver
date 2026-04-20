#!/usr/bin/env python3
# agent_server.py — Serveur Flask pour l'agent Konak Gwinver

from flask import Flask, request, jsonify, send_from_directory
import anthropic
import requests
import csv
import io
import os
import sys
import subprocess
import time
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

try:
    from config import ANTHROPIC_API_KEY, INFOMANIAK_MAIL_TOKEN
except ImportError:
    ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY")
    INFOMANIAK_MAIL_TOKEN = os.getenv("INFOMANIAK_MAIL_TOKEN")


app = Flask(__name__)

SHEETS_CSV        = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQkgs-a_GuintVIJofGGwKzpRLbr1d208HkP8O_62gkI-vQFLPPdq2REww7MLJKidqft8KYiSh6Zyfl/pub?gid=653745516&single=true&output=csv"
INFOMANIAK_CAL_ID = 2128878

SYSTEM_PROMPT = """Tu es l'assistant de gestion de la location saisonnière Konak Gwinver - Le Stang, en Finistère Sud (Bretagne), propriété d'Erwan Gringoire.

Tu as accès en temps réel aux réservations (Google Sheets), aux événements du calendrier Infomaniak (avec leurs IDs), et tu peux créer, modifier ou supprimer des blocages.

RÈGLES ABSOLUES :
1. Avant toute action, tu DOIS présenter un récapitulatif complet et demander une confirmation explicite. Tu n'agis JAMAIS sans que l'utilisateur ait dit "oui", "confirme", "go" ou "ok".
2. Si l'année n'est pas précisée et qu'il y a un doute, demande toujours l'année.
3. Avant de créer un blocage, vérifie dans les événements existants qu'il n'y a pas de doublon sur les mêmes dates.
4. Tout titre de blocage DOIT commencer par "Perso - " suivi du motif (ex: "Perso - Travaux", "Perso - Famille"). Ne jamais omettre le préfixe "Perso - ".
5. Pour modifier ou supprimer, utilise toujours l'ID de l'événement fourni dans le contexte.

ACTIONS — utilise ces formats UNIQUEMENT après confirmation explicite :

Créer :
ACTION: CREATE_BLOCAGE
{"titre": "Perso - xxx", "debut": "YYYY-MM-DD", "fin": "YYYY-MM-DD"}

Modifier :
ACTION: UPDATE_BLOCAGE
{"id": 123456, "titre": "Perso - xxx", "debut": "YYYY-MM-DD", "fin": "YYYY-MM-DD"}

Supprimer :
ACTION: DELETE_BLOCAGE
{"id": 123456}

Tu réponds toujours en français, de manière concise et pratique."""


def lire_reservations():
    try:
        response = requests.get(SHEETS_CSV)
        response.encoding = "utf-8"
        lignes  = response.text.splitlines()
        sejours = list(csv.DictReader(io.StringIO("\n".join(lignes[2:]))))
        result  = []
        for s in sejours:
            nom     = s.get("Prénom, Nom", "").strip()
            arrivee = s.get("Arrivée\nJour", "").strip()
            depart  = s.get("Départ\nJour", "").strip()
            source  = s.get("Source", "").strip()
            adultes = s.get("Nombre adultes", "").strip()
            enfants = s.get("Nombre Enfants", "").strip()
            if nom and arrivee:
                result.append(f"- {nom} | Arrivée: {arrivee} | Départ: {depart} | {adultes} adultes {enfants} enfants | Source: {source}")
        return "\n".join(result) if result else "Aucune réservation trouvée"
    except Exception as e:
        return f"Erreur lecture Sheets: {e}"


def lire_evenements_infomaniak():
    headers = {"Authorization": f"Bearer {INFOMANIAK_MAIL_TOKEN}", "Content-Type": "application/json"}
    events  = []
    tranches = [
        ("2026-01-01", "2026-03-31"),
        ("2026-04-01", "2026-06-30"),
        ("2026-07-01", "2026-09-30"),
        ("2026-10-01", "2026-12-31"),
    ]
    for debut, fin in tranches:
        r   = requests.get(
            "https://api.infomaniak.com/1/calendar/pim/event",
            headers=headers,
            params={"calendar_id": INFOMANIAK_CAL_ID, "from": debut + " 00:00:00", "to": fin + " 00:00:00"}
        )
        raw = r.json().get("data", [])
        events += raw if isinstance(raw, list) else raw.get("events", [])
        print(f"DEBUG GET {debut}: status={r.status_code} data={str(r.json())[:200]}")
        time.sleep(1)
    return events


def creer_blocage(titre, debut, fin):
    headers = {"Authorization": f"Bearer {INFOMANIAK_MAIL_TOKEN}", "Content-Type": "application/json"}
    r = requests.post(
        "https://api.infomaniak.com/1/calendar/pim/event",
        headers=headers,
        json={
            "title": titre, "start": debut + " 00:00:00", "end": fin + " 00:00:00",
            "calendar_id": INFOMANIAK_CAL_ID, "freebusy": "busy", "type": "event",
            "fullday": True, "timezone_start": "Europe/Paris", "timezone_end": "Europe/Paris",
        }
    )
    if r.status_code == 200:
        return r.json().get("data", {}).get("id")
    return None


def modifier_blocage(event_id, titre, debut, fin):
    headers = {"Authorization": f"Bearer {INFOMANIAK_MAIL_TOKEN}", "Content-Type": "application/json"}
    r = requests.put(
        f"https://api.infomaniak.com/1/calendar/pim/event/{event_id}",
        headers=headers,
        json={
            "title": titre, "start": debut + " 00:00:00", "end": fin + " 00:00:00",
            "calendar_id": INFOMANIAK_CAL_ID, "freebusy": "busy", "type": "event",
            "fullday": True, "timezone_start": "Europe/Paris", "timezone_end": "Europe/Paris",
        }
    )
    return r.status_code == 200


def supprimer_blocage(event_id):
    headers = {"Authorization": f"Bearer {INFOMANIAK_MAIL_TOKEN}", "Content-Type": "application/json"}
    r = requests.delete(f"https://api.infomaniak.com/1/calendar/pim/event/{event_id}", headers=headers)
    return r.status_code in [200, 204]


def regenerer_calendrier():
    try:
        subprocess.Popen(["python3.11", os.path.join(BASE_DIR, "generer_calendrier.py")])
        return True
    except Exception as e:
        print(f"Erreur régénération: {e}")
        return False


def executer_action(reply):
    actions = ["CREATE_BLOCAGE", "UPDATE_BLOCAGE", "DELETE_BLOCAGE"]
    resultats = []
    
    for action in actions:
        for m in re.finditer(rf'ACTION: {action}\s*\n\s*(\{{.*?\}})', reply, re.DOTALL):
            try:
                params = json.loads(m.group(1))
                if action == "CREATE_BLOCAGE":
                    event_id = creer_blocage(params["titre"], params["debut"], params["fin"])
                    resultats.append(f"✅ Blocage créé (ID: {event_id})" if event_id else "❌ Erreur création")
                elif action == "UPDATE_BLOCAGE":
                    ok = modifier_blocage(params["id"], params["titre"], params["debut"], params["fin"])
                    resultats.append("✅ Blocage modifié" if ok else "❌ Erreur modification")
                elif action == "DELETE_BLOCAGE":
                    ok = supprimer_blocage(params["id"])
                    resultats.append("✅ Blocage supprimé" if ok else "❌ Erreur suppression")
                regenerer_calendrier()
            except Exception as e:
                resultats.append(f"❌ Erreur: {e}")

    if resultats:
        # Supprimer toutes les lignes ACTION: de la réponse
        reply = re.sub(r'ACTION: \w+\s*\n\s*\{.*?\}', '', reply, flags=re.DOTALL).strip()
        reply += "\n\n" + "\n".join(resultats)

    return reply


@app.route('/')
def index():
    return send_from_directory(BASE_DIR, 'agent.html')


@app.route('/chat', methods=['POST'])
def chat():
    data    = request.json
    message = data.get('message', '')
    history = data.get('history', [])

    reservations = lire_reservations()
    events       = lire_evenements_infomaniak()
    events_txt   = "\n".join([
        f"- ID:{e['id']} | {e.get('title','')} | {e.get('start','')[:10]} → {e.get('end','')[:10]}"
        for e in events
    ]) or "Aucun événement"

    context = f"""Données actuelles Konak Gwinver :

RÉSERVATIONS (Google Sheets) :
{reservations}

ÉVÉNEMENTS CALENDRIER INFOMANIAK (IDs disponibles pour modification/suppression) :
{events_txt}

Date du jour : {__import__('datetime').datetime.now().strftime('%A %d %B %Y')}"""

    messages = []
    for h in history[-10:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": f"{context}\n\nMessage : {message}"})

    client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=messages
    )
    reply = executer_action(response.content[0].text)

    return jsonify({"reply": reply})


if __name__ == '__main__':
    print("🤖 Agent Konak Gwinver démarré sur http://localhost:5000")
    port = int(os.getenv("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)