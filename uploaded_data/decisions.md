# Architecture Decision Records (ADRs)

## ADR-014: Move from SQLite to PostgreSQL (Q1 2026)
Decided by Alice Chen. SQLite's single-writer model caused lock contention under
concurrent ingestion in Project Apollo. PostgreSQL is now the standard datastore for
all production services. Status: ACCEPTED.

## ADR-021: Stream large exports in bounded chunks (2026-06)
Decided by Alice Chen after the Apollo export timeout incident. Exports must iterate
rows in fixed-size chunks rather than loading a full batch into memory. This caps peak
memory and prevents the ingestion-limit timeout. Applies to Apollo and Borealis.
Status: ACCEPTED.

## ADR-009: Every service owns its data (2025)
Decided by Bob Ortiz for Project Borealis. Each service has its own schema; no shared
tables across service boundaries. Status: ACCEPTED.
