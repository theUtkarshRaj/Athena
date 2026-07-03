# Project Apollo — Real-time Analytics Pipeline

**Lead:** Alice Chen. **Contributors:** Bob Ortiz (ingestion), Priya Nair (query engine).

Apollo ingests event streams and serves sub-second analytics queries. The ingestion
layer batches writes into PostgreSQL; the query engine caches hot aggregates.

## Known risks
- Ingestion throughput drops when a single batch exceeds 50k rows — see the
  "Apollo export timeout" incident.
- The query cache can go stale after a large backfill.

## The Apollo export timeout incident (2026-06)
During a nightly export, a 120k-row batch exceeded the ingestion limit and the export
job timed out, blocking downstream dashboards for 40 minutes. Alice Chen led the
response; the fix was to stream rows in bounded chunks instead of materializing the
whole batch. This is now the standard pattern for large exports.
