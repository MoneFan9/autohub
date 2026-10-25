# Mettre AutoHub en ligne pour de vrai

Le site tourne aujourd'hui en **démonstration** : annonces fictives, paiements simulés, bandeau orange en haut de page.
Ce guide liste ce qu'il reste à faire pour l'ouvrir au public, sans créer de société dans un premier temps.

## 1. Réglages Vercel (Settings → Environment Variables, environnement Production)

| Variable | Valeur au lancement | Pourquoi |
|---|---|---|
| `ONLINE_PAYMENTS` | `off` | Aucun agrégateur de paiement n'est branché : tout se règle en espèces à la remise des clés. Ne **jamais** ouvrir au public en `demo` (les paiements y sont simulés). |
| `DEMO_DATA` | `0` | La base vide ne se recharge plus avec les annonces fictives. |
| `OPERATOR_NAME` | déjà « monefan9 » par défaut ; mettre nom et prénom réels si possible | Éditeur du site (mentions légales). |
| `CONTACT_EMAIL` | déjà `lomep610@gmail.com` par défaut | Contact public, signalements, exercice des droits sur les données. |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | fournisseur SMTP gratuit (Brevo : 300 e-mails/jour) | Mot de passe oublié, confirmations, rappels, annulations. Sans eux, aucun e-mail ne part. |
| `CRON_SECRET` | une longue chaîne aléatoire | Protège la tâche quotidienne (rappels la veille du départ, expiration des paiements en attente), lancée par Vercel à 17 h UTC (18 h à Libreville). |
| `PLATFORM_FEE_RATE` | `0` conseillé au début | Lancement gratuit : attire les premiers loueurs et évite de percevoir des revenus avant d'avoir un statut (voir § 4). Passer à `0.02` ensuite. |
| `SITE_URL` | l'adresse publique (domaine) | Liens dans les e-mails, aperçus WhatsApp/Facebook, plan du site. |

Ensuite :
- **Photos** : Storage → Create → **Blob**, puis « Connect to project » sur `autohub`. Vercel ajoute `BLOB_READ_WRITE_TOKEN` ; l'envoi de photos s'active tout seul.
- **Aperçus automatiques** : Settings → Git → décocher « Require Verified Commits ».
- **Redéployer** pour que les variables soient prises en compte.

## 2. Vider la démo

Une fois `DEMO_DATA=0` en place : `python manage.py reset_demo --oui --vide` sur la base de production
(ou demander à Claude de le faire). Les comptes réels (le vôtre) sont conservés.

## 3. Avant d'ouvrir : vérifications

- [ ] Créer un compte client et un compte loueur de test, publier un véhicule **avec photos**, réserver, recevoir les e-mails, faire départ et retour, supprimer les comptes de test.
- [ ] Relire les pages [CGU](/infos/cgu/), [confidentialité](/infos/confidentialite/), [annulation](/infos/annulation/), [mentions légales](/infos/mentions-legales/) : plus aucun « À compléter ».
- [ ] Faire relire ces textes par un juriste dès que possible (ils sont rédigés sur la base de la loi gabonaise n° 001/2011 et des usages des places de marché, mais ne remplacent pas un conseil juridique).

## 4. Statut juridique : lancer sans société

- **Au départ (commission à 0 %)** : vous éditez un site gratuit de mise en relation. Il faut surtout être identifiable (mentions légales), protéger les données (déjà en place) et retirer les annonces frauduleuses (signalements).
- **Données personnelles** : la loi n° 001/2011 prévoit des formalités auprès de la CNPDCP (Commission nationale pour la protection des données à caractère personnel) pour les traitements de données. Renseignez-vous auprès d'elle sur la déclaration à faire ; c'est gratuit.
- **Dès que vous percevez des commissions** : c'est une activité commerciale. Il faudra un statut (entreprise individuelle via le guichet unique de l'ANPI-Gabon) et, pour encaisser en ligne, un compte marchand chez un agrégateur Mobile Money / carte, qui exige généralement ce statut.

## 5. Se faire connaître

Une place de marché vit de son offre : **recrutez d'abord les loueurs, ensuite les clients.**

1. **Les 20 premiers loueurs** : garages et agences de location de Libreville, particuliers qui louent déjà via Facebook ou WhatsApp. Publiez leurs premières annonces avec eux, sur place, avec de bonnes photos (c'est ce qui convertit).
2. **WhatsApp** : chaque annonce a un bouton « Partager » avec un aperçu (photo, prix, ville). Statuts WhatsApp, groupes de quartier, chaînes WhatsApp.
3. **Facebook** : une page AutoHub, puis les groupes « voitures à vendre Libreville / Gabon » et « location voiture Libreville » : publier les annonces avec le lien.
4. **TikTok / Reels** : courtes vidéos de tour de véhicule ; le lien de la vidéo s'affiche sur l'annonce.
5. **Google** : nom de domaine (≈ 10 à 15 €/an, ex. `autohub-gabon.com`), Google Search Console avec `/sitemap.xml`, fiche Google Business.
6. **Bouche-à-oreille** : gratuité pour les loueurs pendant le lancement ; mettre en avant les loueurs fiables.

Mesurer chaque semaine : nombre d'annonces, de réservations, de signalements, délai de réponse des loueurs.
