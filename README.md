# AutoHub

Place de marché de location et de vente de véhicules au Gabon, Django 5 + PostgreSQL. Chacun crée un compte : il réserve une voiture, ou devient vendeur/loueur et publie ses véhicules. La plateforme prélève une commission (`PLATFORM_FEE_RATE`, 2 % par défaut) sur chaque location ; rien sur les ventes (les acheteurs contactent le vendeur).

Montants en francs CFA (XAF, sans centimes), fuseau Africa/Libreville. Chaque loueur choisit ses moyens de paiement :

- **Airtel Money / Moov Money** : « demande de paiement » envoyée au numéro du client, qui la valide sur son téléphone ; le véhicule reste bloqué `PENDING_PAYMENT_MINUTES` (15) minutes, puis la demande expire.
- **Carte** : paiement immédiat.
- **Espèces** : rien en ligne ; le loueur encaisse à la remise des clés après vérification du permis et de la pièce d'identité.

La caution est toujours remise au loueur au départ (case « J'ai reçu… » obligatoire) et rendue au retour sans dommage. Les paiements sont simulés (`FakeProvider`) tant qu'aucun agrégateur n'est branché : un numéro finissant par 0000 ou la carte 4000 0000 0000 0002 simulent un refus.

## Lancer

```bash
docker compose up -d db          # ou un PostgreSQL 16 local
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo       # affiche le mot de passe du compte « agent »
# python manage.py reset_demo --oui  # efface vendeurs et membres de démo, flotte, réservations et recharge la démo
python manage.py runserver
```

| URL | Contenu |
|---|---|
| `/` | recherche par dates, ville, catégorie, énergie, budget |
| `/vehicules/<id>/` | fiche, devis détaillé, réservation et paiement (compte requis) |
| `/reservation/<ref>/paiement/` | validation d'une demande Mobile Money |
| `/occasions/`, `/occasions/<id>/` | annonces de vente, contact direct du vendeur (appel, WhatsApp) |
| `/compte/` | inscription, connexion, mes réservations, devenir vendeur |
| `/espace-vendeur/` | tableau de bord du loueur : gains, commission, départs, retours, états des lieux |
| `/espace-vendeur/vehicules/`, `/profil/`, `/planning/` | ses véhicules, ses moyens de paiement et lieux de remise, son planning |
| `/api/` | API REST (catalogue, devis public ; réservation pour un membre connecté ; actions du loueur sur ses réservations) |
| `/admin/` | administration complète |

Tests : `pytest` (Postgres requis, la contrainte anti-chevauchement est testée en base).

## Choix techniques

- Une réservation active ne peut pas en chevaucher une autre sur le même véhicule : contrainte `EXCLUDE USING gist` en base, en plus du contrôle applicatif.
- Le cycle de vie est porté par `rentals/services.py` : `create_booking` → `pay_and_confirm` → `start_rental` → `complete_rental` (ou `cancel_booking`). Les vues web et l'API l'appellent toutes les deux.
- Un véhicule a deux drapeaux indépendants, `is_rentable` et `is_for_sale` : il peut passer de la location à la vente sans ressaisie.
- Paiement derrière une interface (`payments/providers.py`). `FakeProvider` en V1, carte `4000 0000 0000 0002` = refus. Stripe en V2.
- Retour avec dommages : véhicule envoyé à l'atelier, caution conservée.
- Un formulaire public ne modifie jamais un client existant : l'email doit correspondre au même permis et à la même date de naissance.

## Sécurité et exploitation

| Sujet | Fonctionnement |
|---|---|
| Rôles | Membre : réserve et suit ses locations. Vendeur : ne voit et ne gère que ses véhicules et ses réservations. Superutilisateur (propriétaire de la plateforme) : vue globale et seul accès à l'admin. |
| Double authentification | Obligatoire pour l'admin. Le propriétaire l'active une fois sur `/compte/securite/`, puis l'admin demande mot de passe + code. |
| Tentatives de connexion | 5 échecs sur un même identifiant (quelle que soit l'IP) ou depuis une même IP : blocage 15 minutes (django-axes), sur la connexion du site et l'admin. |
| Mots de passe | Chaque membre change le sien sur `/compte/mot-de-passe/`. |
| Erreurs | Journal sur la sortie standard (logs Vercel). Sentry s'active si `SENTRY_DSN` est défini. |
| Prévisualisations | Utilisent `PREVIEW_DATABASE_URL` (branche Neon `preview`). Sans elle, aucune migration ni donnée de démo n'est écrite depuis une prévisualisation. |
| CI | GitHub Actions : migrations à jour, `check --deploy`, tests sur Postgres 16, à chaque push et demande de fusion. |

## Hors V1

Vente en ligne (offres, reprise, financement), signature électronique, application mobile d'état des lieux, Stripe, tarification dynamique, multi-tenant.
