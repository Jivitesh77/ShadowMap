# ShadowMap

A live map of how safe each street is at night, for IIIT Guwahati and the surrounding area.
It routes people along the safest path, explains the route in plain words, and watches over them until they arrive.

Full specification: [BLUEPRINT.md](BLUEPRINT.md) · Build plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) · Progress: [docs/SPRINT_STATUS.md](docs/SPRINT_STATUS.md)

## Start the app

You need two terminal windows: one for the backend (the server), one for the frontend (the screens).

**Terminal 1 — backend**

```bash
cd ~/Projects/shadowmap/backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Wait for `Application startup complete.`

**Terminal 2 — frontend**

```bash
cd ~/Projects/shadowmap/frontend
npm run dev
```

Then open **http://localhost:5173** in your browser. The sidebar (or the bottom tabs on a phone-sized window) switches between Walker, Sentinel, Trusted contact, Police and City.

To stop either one: click its terminal and press `Ctrl + C`.

## First-time setup (already done on the tech lead's laptop)

```bash
cd ~/Projects/shadowmap/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env

cd ~/Projects/shadowmap/frontend
npm install
```

## Run the tests

```bash
cd ~/Projects/shadowmap/backend && .venv/bin/pytest
cd ~/Projects/shadowmap/frontend && npm run build
```

## Secrets

Keys go only in `backend/.env`, which is never saved to git. Never put keys in the frontend, in docs, or in chat.
