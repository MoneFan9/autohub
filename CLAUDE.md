# AutoHub

Django 5 + PostgreSQL. Tests : `pytest` (Postgres requis).

- Logique métier dans `rentals/services.py` et `payments/services.py`, appelée par les vues web et l'API : ne pas la dupliquer dans les vues.
- Avant toute modification d'un gabarit (`templates/`), du CSS (`static/css/app.css`) ou d'un parcours utilisateur, charger la compétence `ux-ui` (`.claude/skills/ux-ui/SKILL.md`) et suivre son process de vérification (captures 1280 px et 375 px).
