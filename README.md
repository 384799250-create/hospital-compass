# Hospital Compass MVP

Hospital Compass is a hospital-information navigation demonstration. It does not provide diagnosis, treatment, efficacy, or “best hospital” claims.

## Demo-data limits

Every displayed hospital record is labelled **DEMO DATA**. The records are in-memory examples, are not a directory of real hospitals, and must be verified with official sources before use. The matching form is not medical advice. Symptom text is processed only for the request and is neither logged nor stored in the browser profile.

## Start locally

Use Python 3.12+ and a supported Node.js release: `^22.22.2 || ^24.15.0 || >=26.0.0`. From the repository root, install the API and development dependencies in one terminal, then start it on `127.0.0.1:8000`:

```powershell
cd apps/api
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In a second terminal, install the locked web dependencies and start the Vite development server on `127.0.0.1:5173`:

```powershell
cd apps/web
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/v1/*` and `/health` to the API, so the browser uses same-origin requests during local development.

To check the production bundle locally, run `npm run build` followed by `npm start`; the preview server listens on `127.0.0.1:4173` and uses the same API proxy. Run `npm test -- --run` and `npm run typecheck` for the web verification gates.

## Privacy and local data

Favorites contain only hospital IDs. Browser-local profile data uses the `hospital-compass-profile` local-storage key and may be cleared with **Clear local data**. No server-side profile is created.

## Production operating requirements

Production deployment requires MFA and role-based access control (RBAC) for administrative access. Keep encrypted daily backups with an RPO of 24 hours and RTO of 4 hours. The API target is a 99.5% availability SLO. If map data is unavailable, show the hospital address and official URL as the fallback.
