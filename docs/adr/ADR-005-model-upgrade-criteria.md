# ADR-005: Model Upgrade Criteria

## Status

Accepted

## Decision

An LLM/model upgrade should be adopted only when it provides a measurable benefit for the application's research workflow without unacceptable cost, latency, or reliability regressions.

Evaluation should consider:

- factual reliability
- instruction following
- structured-output consistency
- multilingual performance
- latency
- API cost
- regression risk

A model upgrade should be isolated in its own change so it can be reverted independently.
