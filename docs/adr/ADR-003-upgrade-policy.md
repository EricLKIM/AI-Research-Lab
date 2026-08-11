# ADR-003: Upgrade Policy

## Status

Accepted

## Decision

Dependency and model upgrades should be deliberate, tested changes.

Before upgrading a critical dependency or model:

1. Record the current version.
2. Test the application.
3. Review compatibility notes.
4. Run the relevant smoke tests.
5. Commit the upgrade separately from unrelated feature work.

## Rationale

This makes regressions easier to identify and revert.
