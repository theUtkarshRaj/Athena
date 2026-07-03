# Nimbus Labs — Company Overview

Nimbus Labs builds developer tooling. The company has two flagship efforts:

- **Project Apollo** — our real-time analytics pipeline, led by **Alice Chen**.
- **Project Borealis** — the billing platform, led by **Bob Ortiz**.

Alice Chen is the VP of Engineering and owns the reliability roadmap. Bob Ortiz
reports to Alice and also contributes to Apollo's ingestion layer.

Company policy: every production incident must have a written postmortem, and any
architecture decision is recorded as an ADR (Architecture Decision Record).

The primary datastore across both projects is PostgreSQL. We migrated off SQLite
in Q1 2026 because concurrent writes were causing lock contention at scale.
