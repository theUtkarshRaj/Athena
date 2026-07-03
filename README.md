# 🧠 Athena — the analyst whose memory never goes stale

An AI analyst agent with **persistent, cited, self-improving memory** built on the
open-source [cognee](https://github.com/topoteretes/cognee) memory layer. Point it at a
folder of *your* sources; it builds a **knowledge graph**, answers questions **with
citations**, **learns from your feedback**, and **auto-refreshes** when the sources
change — so it never goes stale and never asks you the same thing twice.

> **Not a general chatbot.** Athena reasons only over the documents *you* give it, and
> every answer traces back to them. If it's not in your sources, Athena says so — it
> won't guess. This is memory *over your knowledge*, not a model reciting the internet.

> Hackathon: *The Hangover Part AI — Where's My Context?* · Track: **Best Use of Open Source Cognee**

## The problem
AI agents are stateless and their knowledge bases rot. You get confident answers you
can't trust (no sources), the memory drifts out of date as documents change, and nothing
gets smarter when you correct it.

## Screenshots
<!-- Drop real captures into docs/ and uncomment. Order tells the story: graph → cited
     answer → learns from 👎 → refresh changes the answer. -->
<!--
| Knowledge graph | Cited answer |
|---|---|
| ![graph](docs/01-graph.png) | ![cited answer](docs/02-cited-answer.png) |
| Learns from feedback | Refresh — the answer changes |
| ![teach](docs/03-teach.png) | ![refresh](docs/04-refresh.png) |
-->
_See the [3-minute demo](#3-minute-demo-script) for the full lifecycle in motion._

## What Athena does — the full cognee lifecycle, on screen
| Cognee verb | In Athena | Why it matters |
|---|---|---|
| **remember** (`add` + `cognify`) | Ingest a folder → build a knowledge graph | Turns files into connected, queryable memory |
| **recall** (`recall`, `include_references=True`) | Cited answers scoped to your session | Trust: every claim traces to a source |
| **improve** (`improve` + feedback) | 👎 + a correction makes the next answer better | The agent learns |
| **forget** (`forget`) | Drop stale/irrelevant sources | Memory you can prune |
| **incremental_update** (our upstream feature) | Auto-refresh only changed files; prune removed ones | Memory stays current, hands-free |
| **visualize_graph** | Live knowledge-graph view | See what it actually knows |

It also uses cognee **sessions** for cross-session memory (close it, reopen it — it
remembers the whole conversation) and cognee's **hybrid graph + vector** retrieval.

## Why it's different
- **Cited by default** — answers show their sources (cognee's `include_references`), and
  out-of-scope questions get an honest "that's not in my memory" instead of a hallucination.
- **Self-improving** — a 👎 plus a correction flows into `cognee.improve()`; re-ask and the
  answer is better. Most memory demos are read-only; Athena closes the loop.
- **Never stale** — memory auto-refreshes via `cognee.incremental_update` /
  `cognee hook install`. Edit a source, and the answer changes to match — no re-ingest.

## Built by cognee contributors
Athena's auto-refresh isn't a wrapper around someone else's API — it's **our own feature,
shipped upstream and dogfooded here**:
- **[cognee#3797](https://github.com/topoteretes/cognee/pull/3797)** — `incremental_update`
  + `cognee hook install` (issue **#3669**).
- **cognee-integrations #200** — post-commit hook timing.

That's the difference between *using* open-source cognee and *building* it.

## Quickstart
```bash
pip install -r requirements.txt          # cognee[gemini] + streamlit
cp .env.example .env                      # then paste your Gemini API key into .env
streamlit run app.py
```
All databases are file-based (SQLite / Kuzu / LanceDB) — no infra to run.

## 3-minute demo script
1. **Remember** — click *Remember* on `demo_data/` → watch the graph build (*View knowledge graph*).
2. **Recall (cited)** — ask *"How is Alice connected to the Apollo export timeout?"* → cited answer spanning multiple files.
3. **Improve** — 👎 + a correction → *Teach Athena* → ask again → better answer.
4. **Auto-refresh** — edit a file in `demo_data/` (or `git commit`) → *Refresh* → answer now reflects the change.
5. **Forget** — *Forget everything* → the graph and answers clear.
6. **Cross-session** — reopen the app → it still remembers the conversation.

## Architecture
- `memory.py` — thin cognee-lifecycle wrapper (remember / recall / teach / forget / refresh / graph).
- `app.py` — Streamlit UI (chat with cited answers, feedback loop, live graph).
- `demo_data/` — a sample "company brain" corpus with connected entities.
- Model: **Gemini** (`gemini-2.5-flash` + `gemini-embedding-001`) via cognee.

See [AUTO_REFRESH.md](AUTO_REFRESH.md) for how the never-stale memory works.

## Notes
- `.env` (your API key) is gitignored — never commit it.
