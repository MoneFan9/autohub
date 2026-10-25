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

## Hors V1

Vente en ligne (offres, reprise, financement), signature électronique, application mobile d'état des lieux, Stripe, tarification dynamique, multi-tenant.
