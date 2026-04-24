#!/usr/bin/env python3
# Debug de l'email Gautier Machelon

import sys
sys.path.insert(0, '/Users/airone/Documents/Konak-Bot/konak-gwinver')  # À MODIFIER

from config import INFOMANIAK_MAIL_PASSWORD
import imaplib
import email as email_lib
from datetime import datetime
from lire_email import extraire_infos_airbnb, determiner_annee

print("🔍 Debug email Gautier Machelon\n")

# Connexion email
mail = imaplib.IMAP4_SSL("mail.infomaniak.com")
mail.login("konak-gwinver@ik.me", INFOMANIAK_MAIL_PASSWORD)
mail.select("INBOX")

# Chercher les emails avec "Réservation confirmée"
_, messages = mail.search(None, 'ALL')

print(f"📧 {len(messages[0].split())} email(s) dans INBOX\n")

for num in messages[0].split():
    _, data = mail.fetch(num, '(RFC822)')
    msg = email_lib.message_from_bytes(data[0][1])
    
    # Décoder le sujet
    parts = email_lib.header.decode_header(msg['Subject'])
    sujet = "".join(p.decode(c or 'utf-8', errors='ignore') if isinstance(p, bytes) else p for p, c in parts)
    
    # Chercher "Gautier Machelon"
    if "Gautier" not in sujet and "HMK3DDMMJ9" not in sujet:
        continue
    
    print(f"📨 Email trouvé !")
    print(f"   Sujet: {sujet}")
    
    # Date d'envoi
    date_str = msg['Date']
    print(f"   Date envoi: {date_str}")
    
    # Extraire le corps
    corps = ""
    for part in msg.walk():
        if part.get_content_type() == "text/plain":
            corps = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            break
    
    # Parser les infos
    infos = extraire_infos_airbnb(corps)
    
    print(f"\n🔍 Infos extraites:")
    print(f"   Nom: {infos.get('nom')}")
    print(f"   Code: {infos.get('code')}")
    print(f"   Arrivée: jour {infos.get('arrivee_jour')} mois {infos.get('arrivee_mois')}")
    print(f"   Départ: jour {infos.get('depart_jour')} mois {infos.get('depart_mois')}")
    
    # Calculer l'année
    annee_a = determiner_annee(infos.get("arrivee_mois", 0))
    annee_d = determiner_annee(infos.get("depart_mois", 0))
    
    print(f"\n📅 Années déterminées:")
    print(f"   Arrivée: {infos.get('arrivee_jour')}/{infos.get('arrivee_mois')}/{annee_a}")
    print(f"   Départ: {infos.get('depart_jour')}/{infos.get('depart_mois')}/{annee_d}")
    
    arrivee = datetime(annee_a, infos["arrivee_mois"], infos["arrivee_jour"])
    depart = datetime(annee_d, infos["depart_mois"], infos["depart_jour"])
    
    print(f"\n⏰ Dates complètes:")
    print(f"   Arrivée: {arrivee}")
    print(f"   Départ: {depart}")
    print(f"   Aujourd'hui: {datetime.now()}")
    
    if depart < datetime.now():
        print(f"\n❌ Cette réservation est PASSÉE (départ: {depart.strftime('%Y-%m-%d')})")
    else:
        print(f"\n✅ Cette réservation est FUTURE")
    
    print("\n" + "="*60)
    break

mail.close()
mail.logout()
