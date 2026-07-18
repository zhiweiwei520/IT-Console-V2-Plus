# Contributing

## Development Rules

- Read `console/docs/roadmap.md`, `console/docs/capability-manifest.md`, and the latest entries in `console/docs/SESSION_LOG.md` before making changes.
- Keep changes scoped to the current capability or architecture area.
- Do not bypass `TenantContext` or scoped repositories for tenant data.
- Do not use production data or production Microsoft tenants for tests.
- Do not commit secrets, local databases, release archives, cache folders, or generated runtime state.

## Local Setup

```powershell
cd console
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py init-db
python manage.py seed-demo
python wsgi.py
```

## Tests

```powershell
cd console
python -m pytest tests -q
```

`tests/test_rls_postgres.py` is opt-in. Set `V2PLUS_TEST_DATABASE_URL` only to a disposable PostgreSQL database.

## Documentation

When a meaningful change is made, update the relevant files:

- `console/docs/capability-manifest.md`
- `console/docs/SESSION_LOG.md`
- `console/docs/roadmap.md`
- `CHANGELOG.md`
