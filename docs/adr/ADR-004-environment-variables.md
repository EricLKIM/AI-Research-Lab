# ADR-004: Environment Variables

## Status

Accepted

## Decision

Secrets such as API keys are stored outside source code, normally through `.env` or environment variables.

The repository must provide `.env.example` rather than a real secret-bearing `.env`.

## Security Rules

- Never commit real API keys.
- Keep `.env` in `.gitignore`.
- Do not expose secrets in logs, screenshots, issue reports, or release assets.
