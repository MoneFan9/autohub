---
name: ux-ui
description: Règles UX/UI d'AutoHub (design system, parcours de réservation, accessibilité, microcopie). À charger avant toute modification d'un gabarit, du CSS ou d'un parcours utilisateur, et pour relire une interface.
---

# UX/UI AutoHub

Objectif : qu'un client réserve une voiture en moins de 2 minutes sans hésiter, et qu'un agent fasse un départ ou un retour en 3 clics. Chaque écran doit répondre à une question : « que dois-je faire maintenant ? ».

## 1. Principes

1. **Une action principale par écran.** Un seul bouton plein (`.btn`) visible à la fois ; le reste en secondaire (`.btn-ghost`) ou en lien.
2. **Le prix total d'abord.** Toujours afficher le total TTC de la période, puis le prix par jour en secondaire. Jamais de prix « à partir de » qui change au paiement.
3. **Pas de surprise.** Caution, remise et options visibles avant le paiement, avec le même montant qu'au récapitulatif.
4. **Divulgation progressive.** Les filtres avancés et les champs rares restent repliés (`<details>`) ; on montre d'abord dates et lieu.
5. **Rien d'inventé.** Pas d'avis, de note, de promo ou de garantie que le produit n'offre pas réellement.
6. **Le texte avant la décoration.** Un écran doit rester compréhensible sans CSS.

## 2. Design system (source de vérité : `static/css/app.css`)

Utiliser les variables CSS, jamais une couleur ou un espacement en dur dans un gabarit.

| Jeton | Rôle |
|---|---|
| `--ink`, `--ink-2`, `--muted` | texte principal, secondaire, tertiaire |
| `--bg`, `--surface`, `--surface-2`, `--line` | fond de page, cartes, zones en retrait, bordures |
| `--brand`, `--brand-hover`, `--brand-soft` | action principale, survol, fond léger d'accent |
| `--ok`, `--warn`, `--err` (+ `-soft`) | statuts : confirmé/disponible, attention, erreur |
| `--s-1` … `--s-8` | espacements 4, 8, 12, 16, 24, 32, 48, 64 px |
| `--r-sm`, `--r`, `--r-lg` | rayons 8, 12, 16 px |
| `--shadow-1`, `--shadow-2` | élévation carte, élévation panneau flottant |

- **Typographie** : Inter, échelle 13 / 15 / 17 / 20 / 28 / 40 px. Corps 15-16 px, interligne 1.5. Chiffres de prix en `font-variant-numeric: tabular-nums`.
- **Grille** : conteneur `.wrap` 1200 px max, gouttière 16 px sur mobile, 24 px au-delà de 768 px.
- **Icônes** : sprite `templates/_icons.html`, `<svg class="i"><use href="#i-nom"/></svg>`, toujours accompagnées d'un texte ou d'un `aria-label`.

### Composants existants (réutiliser avant d'en créer)

`.btn` / `.btn-ghost` / `.btn-danger` / `.btn-sm`, `.card`, `.vehicle-card`, `.panel`, `.badge.b-<statut>`, `.chip`, `.field` (label + champ + aide + erreur), `.steps` (sections numérotées), `.summary` (récapitulatif de prix), `.empty` (état vide), `.toolbar`, `.kpi`, `.table`.

## 3. Formulaires

- Libellé au-dessus du champ, sans deux-points, en casse normale. Jamais un placeholder à la place d'un libellé.
- Champs regroupés par étape dans des `<fieldset>` titrés : **1. Votre location**, **2. Conducteur**, **3. Paiement**.
- `autocomplete` renseigné (`given-name`, `family-name`, `email`, `tel`, `bday`, `cc-number`), `inputmode` adapté.
- Erreurs : message sous le champ concerné, en clair, qui dit comment corriger (« Le permis doit avoir au moins 2 ans »), plus un résumé en haut si plusieurs.
- Le bouton d'envoi dit ce qui va se passer et le montant : « Payer 139,65 € et réserver ».
- Mise à jour du prix en direct quand dates ou options changent (appel à `/api/bookings/quote/`), avec repli serveur sans JavaScript.

## 4. Accessibilité (WCAG 2.2 AA, non négociable)

- Contraste texte ≥ 4.5:1 (≥ 3:1 pour texte ≥ 24 px et composants d'interface).
- Focus clavier visible partout (`:focus-visible`, anneau 3 px `--brand`), ordre de tabulation logique.
- Cibles tactiles ≥ 44×44 px sur mobile.
- Un seul `h1` par page, titres hiérarchisés, `lang="fr"`, lien d'évitement « Aller au contenu ».
- Statut jamais porté par la couleur seule : badge = couleur + texte.
- Messages dynamiques (prix, erreurs) dans une zone `aria-live="polite"`.
- Respecter `prefers-reduced-motion`.

## 5. Mobile d'abord

Concevoir à 375 px puis élargir. Pas de défilement horizontal de page (tableaux larges dans un conteneur `overflow-x:auto`). Sur mobile, le récapitulatif de prix passe sous le formulaire et le bouton principal reste accessible sans chercher.

## 6. Microcopie (français)

- Vouvoiement, phrases courtes, verbes d'action sur les boutons (« Rechercher », « Réserver », « Valider le départ »).
- Nombres et dates au format français : `139,65 €`, `lun. 26 oct., 10:00`.
- États vides utiles : dire pourquoi c'est vide et proposer une action (« Aucun véhicule libre à ces dates. Essayez d'élargir la période ou de changer d'agence. »).

## 7. Back-office

Densité plus forte que le site public, mais : tableau lisible (en-têtes collants, montants alignés à droite), une action principale par ligne, actions destructives (annuler) en secondaire avec confirmation, état des lieux dans un panneau dépliable plutôt que des champs alignés sur chaque ligne.

## 8. Process de vérification avant de pousser

1. Captures Playwright à **1280 px** et **375 px** de chaque page touchée (accueil, fiche, confirmation, occasions, connexion, tableau de bord, planning) et les regarder réellement.
2. Parcours clavier complet sur le formulaire de réservation (Tab, Maj+Tab, Entrée).
3. Vérifier qu'aucune couleur codée en dur n'a été ajoutée dans les gabarits (`grep -n "#[0-9a-fA-F]\{3,6\}" templates/`).
4. `pytest` vert.
5. Relire avec la grille : action principale claire ? prix total visible ? erreurs compréhensibles ? fonctionne au clavier et sur mobile ?
