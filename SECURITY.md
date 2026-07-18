# Security Policy

## Supported Status

IT Console V2+ is currently in active foundation / MVP development. It is suitable for review, local testing, and non-production validation. Production deployment requires additional work around secret storage, infrastructure hardening, PostgreSQL role separation, and real tenant evidence.

## Secret Handling

Never commit:

- `.env` files containing real values.
- `console/instance/secret.key`.
- SQLite databases.
- Microsoft client secrets.
- Fernet keys.
- Audit master keys.
- Access tokens, refresh tokens, or exported browser/session cookies.
- Generated release archives that include local runtime files.

Use `console/.env.example` as the only committed environment template.

## Reporting Vulnerabilities

Until a public maintainer contact is added, please open a private security advisory on GitHub if available. If private advisories are not available, open a minimal issue without sensitive proof-of-concept details and ask for a secure contact path.

## Known Security Boundaries

- Capability data access must go through `TenantContext` and scoped repositories.
- Feature routes must use permission checks and tenant context guards.
- Microsoft Graph endpoint usage is constrained through the Graph client layer.
- Audit logs are append-only by design and linked with a hash chain.
- PostgreSQL RLS policy exists in migrations, but real RLS verification is opt-in and must be run against a disposable PostgreSQL database before production use.

## Production Requirements

Before any hosted or customer-facing deployment:

- Move secrets to Key Vault or equivalent managed secret storage.
- Use a non-owner app database role without `BYPASSRLS`.
- Run PostgreSQL RLS tests.
- Rotate any secret that appeared in local archives or repository history.
- Disable Flask debug mode.
- Serve only over HTTPS.
- Review Microsoft Graph permissions and keep them least-privilege.
