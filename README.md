# Anídex

A static, mobile-first animal dex inspired by the feeling of a Pokedex.

## What it does

- Shows a region 1 dex with 80 simple animal entries
- Lets users search, open entries, and mark discoveries
- Includes a live camera scan flow in the browser
- Stores progress and demo accounts in `localStorage`
- Works as an installable PWA

## Run locally

Use any static server from the project root:

```powershell
py -m http.server 8000
```

Then open:

```text
http://127.0.0.1:8000
```

For camera testing on a real phone, use an HTTPS deployment or a secure tunnel.

## Deploy

Best simple options:

- [Render Static Site](https://render.com/docs/static-sites)
- [Netlify](https://docs.netlify.com/site-deploys/create-deploys/)

If you deploy on Render, the included `render.yaml` already points to the static build.

## Notes

- The app uses Bootstrap and a custom pixel font for the look.
- Login and progress are local-demo mode for now. We can wire Supabase auth later if you want shared accounts.
