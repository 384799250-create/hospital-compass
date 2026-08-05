# Hospital Compass MVP

Hospital Compass is a hospital-information navigation demonstration. It does not provide diagnosis, treatment, efficacy, or “best hospital” claims.

## Demo-data limits

Every displayed hospital record is labelled **DEMO DATA**. The records are in-memory examples, are not a directory of real hospitals, and must be verified with official sources before use. The matching form is not medical advice. Symptom text is processed only for the request and is neither logged nor stored in the browser profile.

## Start locally

From `apps/api`, install the project dependencies and start the API:

```powershell
python -m pip install -e .
python -m uvicorn app.main:app --reload
```

From `apps/web`, install dependencies and run the web unit suite:

```powershell
npm install
npm test
```

The web component is designed to call `/v1/matches` and can be served by the application host used for the deployment.

## Privacy and local data

Favorites contain only hospital IDs. Browser-local profile data uses the `hospital-compass-profile` local-storage key and may be cleared with **Clear local data**. No server-side profile is created.

## Production operating requirements

Production deployment requires MFA and role-based access control (RBAC) for administrative access. Keep encrypted daily backups with an RPO of 24 hours and RTO of 4 hours. The API target is a 99.5% availability SLO. If map data is unavailable, show the hospital address and official URL as the fallback.
