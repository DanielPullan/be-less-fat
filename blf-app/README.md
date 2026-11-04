# Be Less Fat (the app)

Track your food and weight, with a daily calorie target, protein and fibre goals (NHS guidance) and a trend
chart. Built on **[Kanto](https://github.com/DanielPullan/Kanto)**, which brings sign-in with passkeys and
authenticator apps, users and roles, the activity log, profiles and badges, themes and celebrations.

## Run it

```bash
cd blf-app
cp .env.example .env        # then add a SECRET_KEY: python3 -c "import secrets; print(secrets.token_hex(32))"
uv run flask --app app run --port 5050       # http://127.0.0.1:5050
```

Anyone can create an account from **Sign up**. To make yourself an admin:
`uv run flask --app app set-role yourname admin` (and `global_admin` to view the app as others). The Users page
needs two-step verification on your own account: add a passkey or an authenticator app on your profile.

### Coming from the old version?

Your old database (`blf_app/blf.sqlite3`) can be copied across, accounts and all:

```bash
uv run flask --app app import-old-blf blf_app/blf.sqlite3 --admin yourname
```

Everyone signs in with their old username and password; pins are no longer used.

## Putting it on the server

Step by step for 3264.uk, alongside SecureMy.School and Johto, at blf.3264.uk (with bringing your data from
your Mac): [docs/server-setup.md](docs/server-setup.md). The files it uses are in `deploy/`.

## What's where

| Path | What it is |
|---|---|
| `settings.py` | Be Less Fat's name, roles, header links, badges, footer note (Kanto reads these) |
| `pages.py` | Today, Food, Weight, Goals and importing weights |
| `models.py` | Body details, weigh-ins and food |
| `nutrition.py` | BMI, the calorie target, protein and fibre goals, high-protein/fibre rules, the weight chart |
| `importer.py` | Reading weigh-ins exported from other apps |
| `old_data.py` | `flask import-old-blf`, copying the pre-Kanto database |
| `templates/`, `static/` | Be Less Fat's pages, icons and built CSS |
| `deploy/`, `docs/server-setup.md` | The systemd service, Apache site and nightly backup, and how to install them |
| `kanto/` | The shared framework, copied from the Kanto repo: change it there and copy it back |
| `migrations/` | Database changes (SQLite upgrades itself at startup) |

Tests: `uv run pytest`. After changing classes in a template, rebuild the CSS:
`npx tailwindcss@3.4.17 -i static/css/tailwind.src.css -o static/css/app.css --minify`.
