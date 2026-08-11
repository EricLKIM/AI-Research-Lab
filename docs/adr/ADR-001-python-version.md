# ADR-001: Python Version Policy

## Status

Accepted

## Decision

The project standardizes on **Python 3.10+** for the supported development/runtime environment.

The exact interpreter version should be pinned or constrained in project configuration when a dependency requires it.

## Rationale

- Maintain compatibility with the project's dependency set.
- Avoid unexpected breakage from untested interpreter releases.
- Keep local development and packaged environments reproducible.

## Upgrade Policy

A Python version upgrade is treated as a controlled project change rather than an automatic update.
