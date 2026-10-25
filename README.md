# AutoHub V1

Location et vente de véhicules, Django 5 + PostgreSQL.

## Lancer

```bash
docker compose up -d db          # ou un PostgreSQL 16 local
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo       # affiche le mot de passe du compte « agent »
python manage.py runserver
```

| URL | Contenu |
|---|---|
| `/` | recherche par dates, agence, catégorie, énergie, budget |
| `/vehicules/<id>/` | fiche, devis détaillé, réservation et paiement |
| `/occasions/` | véhicules de la flotte mis en vente |
| `/agence/` | tableau de bord : KPIs, départs, retours, états des lieux |
| `/agence/planning/` | planning de flotte sur 14 jours |
| `/api/` | API REST (catalogue, devis, réservations, actions d'agence) |
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
| Rôles | Groupe « Agence » : espace agence uniquement. Superutilisateur (propriétaire) : seul à accéder à l'admin. |
| Double authentification | Obligatoire pour l'admin. Le propriétaire l'active une fois sur `/agence/securite/`, puis l'admin demande mot de passe + code. |
| Tentatives de connexion | 5 échecs sur un même identifiant (quelle que soit l'IP) ou depuis une même IP : blocage 15 minutes (django-axes), sur l'espace agence et l'admin. |
| Mots de passe | Chaque membre d'agence change le sien sur `/agence/mot-de-passe/`. |
| Erreurs | Journal sur la sortie standard (logs Vercel). Sentry s'active si `SENTRY_DSN` est défini. |
| Prévisualisations | Utilisent `PREVIEW_DATABASE_URL` (branche Neon `preview`). Sans elle, aucune migration ni donnée de démo n'est écrite depuis une prévisualisation. |
| CI | GitHub Actions : migrations à jour, `check --deploy`, tests sur Postgres 16, à chaque push et demande de fusion. |

## Hors V1

Vente en ligne (offres, reprise, financement), signature électronique, application mobile d'état des lieux, Stripe, tarification dynamique, multi-tenant.
