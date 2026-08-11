# ADR-002: Project Structure

## Status

Accepted

## Decision

The application uses a modular project structure with source code separated from generated data, configuration, and installer assets.

The main application entry point should remain small where practical. Feature-specific logic belongs in dedicated modules.

## Rationale

- Easier debugging and testing.
- Smaller, reviewable changes.
- Safer feature development through isolated modules.
- Clear separation between application logic and user-generated data.
