# Anidex Day 1

A lightweight Flask prototype for an animal discovery app inspired by a Pokédex.

## Features

- Responsive animal card grid
- Animal detail pages
- Login, signup, and profile pages
- Local progress tracking for guests
- Database-backed progress for signed-in users
- Search by name, habitat, category, or region
- Live camera scan flow

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Then open `http://127.0.0.1:5000`.

## Run on phone with camera

If you want the simplest no-warning path for mobile camera access, install Cloudflare Tunnel on Windows:

```powershell
winget install --id Cloudflare.cloudflared
```

Then run:

```powershell
.\run_tunnel.bat
```

That starts the local Flask server and prints a trusted `https://*.trycloudflare.com` URL. Open that URL on your phone and the camera button should work without the local `Not secure` warning.

If you only want the local network version, use:

```powershell
.\run_http.bat
```

If you want the self-signed HTTPS version instead, use:

```powershell
.\run_https.bat
```

## Public deploy

Best public setup:

- Host the Flask app on [Render](https://render.com/docs/deploy-flask)
- Store users and progress in [Supabase Postgres](https://supabase.com/docs/guides/database)

Render deploy settings:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`

Environment variables to set on Render:

- `DATABASE_URL` = your Supabase Postgres connection string
- `ANIDEX_SECRET_KEY` = a long random secret

Notes:

- Render web services must bind to `0.0.0.0` and use the `PORT` value provided by Render.
- The deployed site will be served over HTTPS, so friends should not see the browser `Not secure` warning.
- Local SQLite still works when `DATABASE_URL` is not set, which is useful for development.
