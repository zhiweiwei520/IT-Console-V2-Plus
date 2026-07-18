# IT Console V2+ Project Status

> Snapshot date: 2026-07-18  
> Status: active foundation / MVP spike  
> Primary stack: Python, Flask, SQLAlchemy, Alembic, Microsoft Graph, pytest

## Summary

IT Console V2+ is a multi-tenant Microsoft 365 / Entra / security operations console. The current work focuses on a SaaS-ready foundation: management environments, managed tenants, scoped repositories, durable background jobs, Microsoft Graph integration, audit chains, and capability modules that can be safely expanded without cross-tenant data leakage.

The codebase is intentionally separated from the older IT Console implementation. It uses its own Flask app, configuration namespace, database, migrations, and port.

## Current Progress

| Area | Status | Evidence |
|---|---:|---|
| Multi-environment / multi-tenant data model | Done | `console/app/platform/models.py`, `console/app/microsoft/models.py`, migrations `0001+` |
| Tenant-scoped repository pattern | Done | `console/app/storage/repository.py`, isolation tests |
| Local platform and environment login | Done | `console/app/web/auth/`, auth flow tests |
| Platform admin UI | Done | `/platform/` routes and service tests |
| Managed Tenant onboarding | Done | BYO app form, encrypted credential storage, connection test flow |
| Microsoft Graph client layer | Done | Token broker, endpoint allowlist, retry/error translation tests |
| Durable job queue / worker | Done | lease, retry, checkpoint, DLQ, embedded worker |
| Audit hash chain and anchor | Done | chain verification and anchor tamper tests |
| Entra SSO login flow | Implemented, real IdP evidence pending | mocked IdP tests complete |
| GitHub Actions skeleton | Done | `.github/workflows/v2plus-console-ci.yml` |
| PostgreSQL RLS real DB test | Test exists, opt-in pending | `tests/test_rls_postgres.py` |
| Real Microsoft Graph success evidence | Pending external tenant/app | failure path verified; success path needs test Entra tenant |

## Implemented Capability Modules

| Capability | Microsoft source | Sync style | Status |
|---|---|---|---|
| Accounts | `/users` | full sync | implemented and tested |
| Devices | `/deviceManagement/managedDevices` | full sync | implemented and tested |
| Sign-in logs | `/auditLogs/signIns` | watermark incremental | implemented and tested |
| Licenses / MFA | `/subscribedSkus`, `userRegistrationDetails` | staged sync | implemented and tested |
| App audit | `/applications`, `/servicePrincipals` | staged sync | implemented and tested |
| Software inventory | `/deviceManagement/detectedApps` | full sync | implemented and tested |
| Teams | groups / teams / channels / members | staged sync | implemented and tested |
| SharePoint | `/sites?search=*`, drives | staged sync | implemented and tested |
| Defender alerts | `/security/alerts_v2` | watermark incremental | implemented and tested |
| Security incidents | `/security/incidents` | watermark incremental | implemented and tested |
| Dashboard | internal aggregation | read-only | implemented and tested |

## Latest Recorded Test Evidence

The latest session log records:

- `225 passed, 3 skipped`
- Test environment: `FLASK_ENV=testing` with `sqlite:///:memory:`
- Skipped tests are expected opt-in tests for external PostgreSQL / integration resources.

See `console/docs/SESSION_LOG.md` and `console/docs/capability-manifest.md` for detailed evidence and known gaps.

## Next Milestones

1. Obtain a non-production Entra tenant and app registration.
2. Run real Microsoft Graph success-path validation for the implemented capability modules.
3. Run `tests/test_rls_postgres.py` against a disposable PostgreSQL database.
4. Move audit signing material to production-grade secret storage before any hosted deployment.
5. Decide SaaS isolation tier strategy: shared DB with RLS, dedicated DB, or dedicated stamp.
