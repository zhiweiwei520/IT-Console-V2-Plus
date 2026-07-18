# Claude for OSS Application Notes — IT Console V2+

This document is intended as supporting material for a Claude for OSS application.

## Project Name

IT Console V2+

## Project Type

Open-source Microsoft 365 / Entra / security operations console.

## Short Description

IT Console V2+ is a Python / Flask based operations console for managing and auditing multiple Microsoft Entra tenants from a safer, tenant-scoped control plane. It focuses on Microsoft Graph data collection, delegated tenant administration, auditability, background sync reliability, and strict data isolation.

## Why This Project Matters

Many small IT teams, MSPs, and internal security teams need visibility across Entra ID, Microsoft 365, Intune, Teams, SharePoint, Defender, and security incidents. Existing approaches often become one-off scripts, spreadsheets, or single-tenant tools with weak audit trails.

This project aims to provide an inspectable open-source foundation for:

- Multi-tenant Microsoft 365 operational visibility.
- Safer tenant isolation through scoped repositories and PostgreSQL RLS design.
- Durable background synchronization with retry, checkpoint, and dead-letter handling.
- Auditable operations using per-environment hash chains and anchors.
- Practical self-host deployment before any SaaS deployment.

## Current Development Stage

The project is in an active MVP / foundation phase. The multi-tenant kernel, Microsoft Graph client layer, durable job queue, platform administration UI, managed tenant onboarding, audit chain, and multiple read-only capability modules are already implemented with tests.

Current known gaps are explicit and tracked:

- Real Microsoft Graph success-path evidence requires a non-production Entra tenant and app registration.
- PostgreSQL RLS tests are written but need an opt-in disposable PostgreSQL database.
- Production secret handling still needs Key Vault or equivalent external secret storage.
- SaaS deployment automation and hosted control plane are not yet complete.

## How Claude Helps

Claude is useful in this project because the codebase requires consistent changes across architecture documents, migrations, SQLAlchemy models, scoped repositories, service layers, Flask routes, templates, workers, and tests.

Claude-assisted workflows are especially valuable for:

- Adding new Microsoft Graph capability modules while preserving tenant isolation rules.
- Reviewing code for cross-tenant access risks and permission gating mistakes.
- Keeping architecture documents, roadmaps, changelogs, and session logs synchronized with implementation.
- Writing focused tests for worker retry behavior, checkpoint behavior, Graph error translation, and route-level authorization.
- Refactoring repeated capability patterns only after enough module shapes are proven.

## Repository Evidence

Recommended files for reviewers:

- `README.md` — architecture and documentation index.
- `console/README.md` — local run instructions and feature overview.
- `PROJECT_STATUS.md` — current implementation status.
- `console/docs/capability-manifest.md` — authoritative done / not-done list.
- `console/docs/SESSION_LOG.md` — append-only development history.
- `console/docs/roadmap.md` — planned phases and remaining gates.
- `.github/workflows/v2plus-console-ci.yml` — CI skeleton.

## Open Source Readiness Notes

Before publishing publicly:

- Do not upload `.env`, `console/.env`, `console/instance/secret.key`, local SQLite databases, release zips, or generated caches.
- Rotate any key that was ever committed, shared, zipped, or uploaded.
- Add an explicit OSS license if public reuse is intended.
- Keep `.env.example` as the only environment file in the repository.
