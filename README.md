# ShadowMap

A live map of how safe each street is at night, for IIIT Guwahati and the surrounding area.
It routes people along the safest path, explains the route in plain words, and watches over them until they arrive.

Full specification: [BLUEPRINT.md](BLUEPRINT.md) · Build plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) · Progress: [docs/SPRINT_STATUS.md](docs/SPRINT_STATUS.md)

## Start the app

One command starts everything (backend server + frontend screens):

```bash
cd ~/Projects/shadowmap
./start.sh
```

Then open **http://localhost:5173** in your browser.
Press `Ctrl + C` once in that terminal to stop everything.

Notes:
- `http://localhost:8000` is the backend. It has no screens; it only answers the app's data requests.
- If you see "Port ... is already in use", ShadowMap is already running in another terminal — use that one, or stop it there first.

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
