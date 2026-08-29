# Phit

A small local web app that connects to your Garmin Connect account, lists
your recent runs, and lets you pick two of them to compare side by side
(pace, heart rate, cadence, elevation) to see whether you're improving.

It uses the unofficial [`garminconnect`](https://pypi.org/project/garminconnect/)
Python library, since Garmin does not offer a public API for personal use.
Your credentials never leave your machine except to talk to Garmin's own
servers.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # then edit .env with your Garmin email/password
```

## Run

```bash
cd backend
python app.py
```

Open http://localhost:5000.

- On first load the app tries to auto-connect using the credentials in `.env`.
- If your account has MFA enabled, you'll be prompted for the code in the browser.
- After a successful login, session tokens are cached under the path in
  `GARMIN_TOKEN_STORE` (default `~/.phit/garmin_tokens`) so you won't need to
  log in again on every restart.
- If you'd rather not put credentials in `.env`, leave it blank and enter
  them directly in the "Connect to Garmin" form instead (kept in memory for
  that session only).

## Using it

1. The **Recent runs** table lists your latest running activities (road,
   trail, track, treadmill) with distance, duration, pace, average heart
   rate, and elevation gain.
2. Check exactly two runs and click **Compare selected runs**.
3. The comparison view shows both runs side by side plus the change between
   them — green means faster/lower effort, red means slower/higher effort,
   for pace, duration, and heart rate.

## Project layout

```
backend/
  app.py            Flask app and API routes
  garmin_client.py  Garmin Connect login + data shaping
  requirements.txt
frontend/
  index.html
  app.js
  style.css
.env.example
```
