# Intranet HQ

A private, self-hosted intranet homepage, packaged as an Umbrel community app. Built by Paragdise Ventures LLC. Ships with the Paragdise look by default.

- **App pipeline:** your apps on a board (Idea, Building, Testing, Submitted, Live). Tap a card to change its stage or next step. Anything untouched for 14 days gets a "Needs a look" tag.
- **Resources:** grouped links you can edit on the page.
- **Daily brief:** written once each morning (6:00 by default) from your calendar, local weather, and pipeline nudges. Saved to disk, so opening the page costs nothing.

## How the brief stays cheap

- The server gathers the facts itself. Claude only writes a short summary.
- One call a day on Haiku, `max_tokens` 300.
- Hard monthly cap (default 40 calls). Past the cap, or with no key, you get a plain brief built without Claude.
- "Refresh brief" asks before spending a call.

## Install on Umbrel

1. Create a public GitHub repo (for example `intranet-hq`) and push this folder to it.
2. (Already done for Primo689. If someone forks this, they replace the username in `paragdise-intranet-hq/docker-compose.yml` and `paragdise-intranet-hq/umbrel-app.yml`, using lowercase in the image name.)
3. Build the image: any push to `main` that touches the app or the manifest kicks off the GitHub Action. It reads the version from `umbrel-app.yml`, builds for both x86 and ARM and publishes to `ghcr.io/primo689/intranet-hq`.
4. On GitHub, open the package's settings and set visibility to **Public** so Umbrel can pull it.
5. In Umbrel: App Store, the three dots, Community App Stores, paste your repo URL, then install **Intranet HQ**. It opens on port 8484 behind your Umbrel login.
6. The first time you open it, a short setup walks you through your name, your town (looked up for you), your apps, and the optional Claude key and Google Calendar link. You can rerun it anytime from Settings.

Nothing personal lives in this repo. Your name, location, apps, key, and calendar link are all saved on your Umbrel only.

Update the BookStack link in Resources to match the port Umbrel gave it.

## Updating

Bump `version` in `umbrel-app.yml` and the image tag in `docker-compose.yml` to match, then push to `main`. The Action builds that version and Umbrel shows the update.

## Data

Everything lives in `${APP_DATA_DIR}/data` as plain JSON: `pipeline.json`, `links.json`, `settings.json`, `usage.json`, and `briefs/`. Include that folder in your Umbrel backups.

## Brand

It ships with the Paragdise look, but anyone can make it theirs in **Settings, Look**: wordmark, highlighted letter, label, tagline, three colors (main, highlight, text), and a logo upload (PNG, JPG, or WebP under 1 MB; SVG is blocked on purpose since it can carry scripts). Dark mode follows the chosen colors. "Reset look to default" brings back the Paragdise brand.

Default palette: Ocean Deep #006A7A, Tropical Teal #14BBA6, Lagoon #7DD3C7, Paradise Gold #F4C430, Warm Sand #F7E7CE, Island Night #0B2D3A.

Fonts are bundled locally so nothing loads from the internet: Playfair Display for headings and Montserrat for body text. Both are open source (SIL OFL, licenses in `app/static/fonts`).

Uploaded logos are stored in `${APP_DATA_DIR}/data/brand`.

## Run locally

```
cd app
pip install -r requirements.txt
DATA_DIR=./data gunicorn -w 1 --threads 4 -b 127.0.0.1:8484 server:app
```
