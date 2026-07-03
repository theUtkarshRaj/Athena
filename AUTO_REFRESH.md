# Auto-refreshing memory (the differentiator)

Most memory demos are write-once: ingest, then the memory slowly goes stale as the
underlying sources change. Athena stays current.

## In-app
The sidebar **🔄 Refresh** button calls `cognee.incremental_update(folder)`, which:
- re-cognifies only **changed/new** files (unchanged ones skip LLM extraction),
- **prunes** graph content for files removed from the folder — while preserving
  entities other sources still reference.

## Hands-free (git hook)
If your sources live in a git repo, install the post-commit hook so memory refreshes
on every commit:

```bash
cognee hook install --path ./demo_data --dataset-name athena
```

Now: edit a source → `git commit` → Athena's memory updates automatically, and its
answers change to match — with no manual re-ingest.

> `incremental_update` and `cognee hook install` are an upstream feature we contributed
> to cognee itself (issue #3669). Athena dogfoods our own contribution.
