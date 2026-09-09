# Hospital Compass MVP

Hospital Compass is a hospital-information navigation demonstration. It does not provide diagnosis, treatment, efficacy, or “best hospital” claims.

## Data and safety limits

The in-memory demonstration fixtures are labelled **DEMO DATA** and are not part of the public API dataset. The API's current public dataset contains one verified Beijing public record sourced from `app/data/verified_beijing_hospitals.csv`; it is labelled **已核验公开信息**, is not a comprehensive hospital directory or recommendation, and should still be checked against the linked official source before use. The matching form is not medical advice. Symptom text is processed only for the request and is neither logged nor stored in the browser profile.

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

## Qinglin media studio

Set `QINGLIN_API_KEY` in `apps/api/.env` or in the server environment. The key is read only by FastAPI and is never sent to the browser. Start both services, then open `http://127.0.0.1:5173/media` to discover available Qinglin image/video models, check balance, submit a prompt, and preview the asynchronous result.

The media routes are `/v1/media/models`, `/v1/media/models/{model_name}`, `/v1/media/balance`, `/v1/media/tasks`, and `/v1/media/tasks/{task_id}`. Generation is blocked when the Qinglin balance is empty.

To check the production bundle locally, run `npm run build` followed by `npm start`; the preview server listens on `127.0.0.1:4173` and uses the same API proxy. Run `npm test -- --run` and `npm run typecheck` for the web verification gates.

## Privacy and local data

Favorites contain only hospital IDs. Browser-local profile data uses the `hospital-compass-profile` local-storage key and may be cleared with **Clear local data**. No server-side profile is created.

## Pilot hospital data operations

Use `POST /admin/import-preview` with UTF-8 CSV text to validate, in memory only, the columns in `data/pilot-hospital-import-template.csv`: `id`, `name`, `city`, `tier`, `source_url`, `source_date`, `specialties`, `disease_tags`, `verified`, and `published`. The endpoint returns an accepted count and row-level validation errors; it neither stores nor publishes submitted records.

Operator sequence: preview → source verification → reviewer approval → publication. The current 30 pilot hospital records are unverified, unpublished drafts. They are not public and do not enter matching until they have been verified and approved for publication.

`app/data/pilot_hospitals.csv` is used only for draft import testing. `app/data/verified_beijing_hospitals.csv` is the API's only current public data source. Every record in that file must be for Beijing, set `verified=true` and `published=true`, use an HTTPS source, and have a source date within the preceding 180 days.

## Production operating requirements

Production deployment requires MFA and role-based access control (RBAC) for administrative access. Keep encrypted daily backups with an RPO of 24 hours and RTO of 4 hours. The API target is a 99.5% availability SLO. If map data is unavailable, show the hospital address and official URL as the fallback.
