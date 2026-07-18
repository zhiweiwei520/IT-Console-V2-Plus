# GitHub Upload Checklist

Use this checklist before uploading IT Console V2+ to GitHub.

## Must Do Before Public Upload

- [ ] Remove `console/.env`.
- [ ] Remove `console/instance/secret.key`.
- [ ] Remove local SQLite databases under `console/instance/`.
- [ ] Remove `Release/` build folders unless the release content is intentionally published and has been sanitized.
- [ ] Remove `IT-Console-V2+.zip` or any generated release zip from the repository.
- [ ] Keep `console/.env.example`.
- [ ] Confirm `.gitignore` is committed before adding files.
- [ ] Run a secret scan before push.
- [ ] Add a `LICENSE` file if the repository will be open source.

## Recommended Git Commands

```powershell
cd C:\Temp\IT-Console-V2+
git status --short
git add .gitignore README.md PROJECT_STATUS.md CLAUDE_FOR_OSS_APPLICATION.md GITHUB_UPLOAD_CHECKLIST.md SECURITY.md CONTRIBUTING.md console .github
git status --short
```

Review `git status --short` carefully. If you see any of these, do not commit them:

- `.env`
- `secret.key`
- `*.db`
- `*.sqlite`
- `Release/`
- `*.zip`
- `__pycache__/`
- `.pytest_cache/`

## Suggested Repository Description

Multi-tenant Microsoft 365 / Entra / security operations console with tenant-scoped data access, Microsoft Graph sync workers, audit chains, and Flask-based self-hosting.

## Suggested Topics

```text
microsoft-graph
entra-id
microsoft365
intune
defender
flask
sqlalchemy
alembic
multi-tenant
security-operations
it-operations
open-source
```
