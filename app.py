"""Athena — the analyst whose memory never goes stale.

A Streamlit demo of cognee's full memory lifecycle:
  remember -> recall (cited) -> learn from feedback -> forget -> auto-refresh,
with a live knowledge-graph view.

Run:  streamlit run app.py
"""

import asyncio
import os
import tempfile
import threading
import uuid
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import memory

st.set_page_config(page_title="Athena — living AI memory", page_icon="🧠", layout="wide")


# --- visual polish -----------------------------------------------------------
# Defensive CSS: enhances the look but never gates behaviour. If a Streamlit
# selector changes across versions, the app still works — it just styles less.
st.markdown(
    """
    <style>
      /* sit the header a little higher */
      [data-testid="stMainBlockContainer"], .block-container { padding-top: 2.2rem; }

      h1 { font-weight: 800; letter-spacing: -0.02em; }

      /* feature chips row */
      .athena-chips { display:flex; flex-wrap:wrap; gap:8px; margin:.4rem 0 .3rem; }
      .athena-chips .chip {
        font-size:.82rem; font-weight:600; color:#cfd2e0;
        background:rgba(139,124,246,.10); border:1px solid rgba(139,124,246,.30);
        padding:5px 12px; border-radius:999px; white-space:nowrap;
      }

      /* buttons: rounded, subtle border, gentle hover lift */
      .stButton > button {
        border-radius:10px; border:1px solid rgba(255,255,255,.10); font-weight:600;
        transition:border-color .15s ease, transform .15s ease, color .15s ease;
      }
      .stButton > button:hover {
        border-color:#8b7cf6; color:#fff; transform:translateY(-1px);
      }

      /* chat turns as soft cards */
      [data-testid="stChatMessage"] {
        background:#171922; border:1px solid rgba(255,255,255,.06);
        border-radius:14px; padding:.55rem .9rem; margin-bottom:.5rem;
      }

      /* citation expander: calmer, on-brand */
      [data-testid="stExpander"] {
        border-radius:12px; border:1px solid rgba(139,124,246,.25);
      }

      /* knowledge-graph panel: framed */
      [data-testid="stElementContainer"] iframe { border-radius:10px; }

      /* recolor Streamlit's default top gradient bar to match the brand */
      [data-testid="stDecoration"] {
        background-image: linear-gradient(90deg, #8b7cf6 0%, #b3a7ff 100%);
      }
    </style>
    """,
    unsafe_allow_html=True,
)


# One persistent event loop on a dedicated thread for the whole process. Every
# cognee call runs on this single loop, so its cached async DB engines stay valid
# across Streamlit reruns (calling asyncio.run() per click would create a new loop
# each time and break cognee with "attached to a different loop").
@st.cache_resource
def _bg_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


RUN_TIMEOUT = 300  # s — safety net so a hung API call surfaces as an error, not a frozen UI


def run(coro):
    """Run an async cognee call on the shared background loop and block for the result."""
    return asyncio.run_coroutine_threadsafe(coro, _bg_loop()).result(timeout=RUN_TIMEOUT)


def try_run(coro, failure="Athena hit a snag reaching its memory."):
    """Run a cognee call but never let a failure crash the demo. On any error, show a
    calm message (the full traceback still prints to the server console for us) and
    return (False, None) so callers can skip gracefully."""
    try:
        return True, run(coro)
    except Exception:
        st.error(f"⚠️ {failure} Check the Gemini key / connection, then try again.")
        return False, None


def ingest(paths, label):
    """Ingest a batch of file paths in one cognify, guarded, and surface what OCR did.
    Returns True on success. `paths` is a list of local file paths."""
    with st.spinner(f"Ingesting {label}…"):
        ok, res = try_run(memory.remember(paths), "Couldn't ingest the file(s).")
    if ok:
        st.success(f"Ingested {len(paths)} file(s). Ask a question →")
        if isinstance(res, dict):
            if res.get("ocr"):
                st.info(
                    "🔎 Read scanned PDF(s) with OCR: **" + ", ".join(res["ocr"])
                    + "** — no text layer, so Athena recognised the pages. Now searchable."
                )
            if res.get("unreadable"):
                st.warning(
                    "⚠️ Couldn't extract text even with OCR: **" + ", ".join(res["unreadable"])
                    + "**. Try a clearer scan or a text-based PDF."
                )
    return ok


# --- session identity: this is what gives cross-session memory --------------
if "session_id" not in st.session_state:
    st.session_state.session_id = f"athena_{uuid.uuid4().hex[:8]}"
if "chat" not in st.session_state:
    st.session_state.chat = []

st.title("🧠 Athena")
st.markdown("##### The analyst whose memory never goes stale.")
st.markdown(
    '<div class="athena-chips">'
    '<span class="chip">📎 Cited answers</span>'
    '<span class="chip">🔄 Self-updating memory</span>'
    '<span class="chip">🧠 Learns from feedback</span>'
    '<span class="chip">🕸️ Live knowledge graph</span>'
    "</div>",
    unsafe_allow_html=True,
)
st.caption("Built on the open-source cognee memory layer.")

if st.session_state.get("last_refresh"):
    _r = st.session_state.last_refresh
    st.info(
        f"🧠 **Memory refreshed** — {_r.get('processed', '?')} source(s) processed, "
        f"{_r.get('removed', '?')} removed. Athena's memory stays live as your sources change."
    )

# --------------------------------------------------------------------------- #
# Sidebar — the memory lifecycle controls
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("🧠 Memory")
    st.caption(f"Session `{st.session_state.session_id}` · cross-session memory on")

    # Uploaded files land here; Refresh watches this folder. Runtime-only (gitignored).
    upload_dir = Path(__file__).parent / "uploaded_data"
    upload_dir.mkdir(exist_ok=True)

    st.markdown("**① Build memory**")
    uploaded_files = st.file_uploader(
        "Upload documents to remember",
        accept_multiple_files=True,
        type=["txt", "md", "pdf", "docx", "csv", "json"],
    )
    if uploaded_files:
        new_paths = []
        for uf in uploaded_files:
            file_key = f"ingested_{uf.name}_{uf.size}"
            if file_key not in st.session_state:
                dest = upload_dir / uf.name
                dest.write_bytes(uf.getvalue())
                new_paths.append(str(dest))
                st.session_state[file_key] = True
        if new_paths and ingest(new_paths, "uploaded file(s)"):
            st.rerun()

    if st.button("📥 Load demo data", use_container_width=True):
        demo_dir = Path(__file__).parent / "demo_data"
        new_paths = []
        for df in sorted(demo_dir.glob("*")):
            if df.is_file() and not df.name.startswith("."):
                file_key = f"ingested_{df.name}_{df.stat().st_size}"
                if file_key not in st.session_state:
                    dest = upload_dir / df.name
                    dest.write_bytes(df.read_bytes())
                    new_paths.append(str(dest))
                    st.session_state[file_key] = True
        if new_paths:
            if ingest(new_paths, "demo file(s)"):
                st.rerun()
        else:
            st.info("Demo files already loaded.")

    st.markdown("**② Explore**")
    if st.button("🕸️ View knowledge graph", use_container_width=True):
        out = os.path.join(tempfile.gettempdir(), "athena_graph.html")
        with st.spinner("Rendering graph…"):
            ok, _ = try_run(memory.graph_html(out), "Couldn't render the graph — build memory first.")
        if ok:
            try:
                st.session_state.graph_html = Path(out).read_text(encoding="utf-8")
            except Exception:
                st.error("⚠️ The graph wasn't produced yet — build memory first.")

    st.caption("Try asking 👇")
    for j, ex in enumerate(
        [
            "How is Alice connected to the Apollo export timeout?",
            "Why did Nimbus move to PostgreSQL, and who decided it?",
            "What fixed the Apollo export timeout?",
        ]
    ):
        if st.button(ex, key=f"ex{j}", use_container_width=True):
            st.session_state.pending_q = ex

    st.markdown("**③ Keep it current**")
    if st.button("🔄 Refresh (only changed files)", use_container_width=True):
        with st.spinner("Syncing changed/removed sources…"):
            ok, res = try_run(memory.refresh(str(upload_dir)), "Refresh couldn't reach the sources.")
        if ok:
            st.session_state.last_refresh = res
            # The "living memory" beat: re-ask the last question so the answer visibly
            # updates to reflect the changed sources — memory that never goes stale.
            last_q = next((t["q"] for t in reversed(st.session_state.chat)), None)
            if last_q:
                with st.spinner("Re-checking your last question against the updated memory…"):
                    ok2, r = try_run(memory.recall(last_q, session_id=st.session_state.session_id))
                if ok2 and r:
                    st.session_state.chat.append(
                        {
                            "q": last_q,
                            "a": r["answer"],
                            "citations": r.get("citations", []),
                            "note": "🔄 re-answered after refresh — sources changed, so the answer did too",
                        }
                    )
            st.rerun()
    st.caption("Powered by `incremental_update` — a feature we contributed to cognee.")

    st.divider()
    if st.button("🗑️ Forget everything", use_container_width=True):
        try_run(memory.forget())
        st.session_state.chat = []
        st.session_state.pop("graph_html", None)
        st.session_state.pop("last_refresh", None)
        st.session_state.pop("correcting", None)
        # Reset upload tracking and clear the uploaded files from disk.
        for key in [k for k in st.session_state.keys() if k.startswith("ingested_")]:
            st.session_state.pop(key, None)
        if upload_dir.exists():
            for f in upload_dir.glob("*"):
                if f.is_file():
                    f.unlink()
        st.warning("Memory cleared for this dataset.")

# --------------------------------------------------------------------------- #
# Main — chat with cited answers + feedback loop
# --------------------------------------------------------------------------- #
if st.session_state.get("graph_html"):
    with st.expander("🕸️ Knowledge graph", expanded=True):
        components.html(st.session_state.graph_html, height=500, scrolling=True)

if not st.session_state.chat and not st.session_state.get("graph_html"):
    st.info(
        "👋 **Start here** — upload your documents or click **📥 Load demo data** in the "
        "sidebar to build a knowledge graph, then ask a question below. "
        "Athena answers **with citations**; correct it with 👎 and it **learns**; "
        "change a source and hit **🔄 Refresh** and its answers **stay current**."
    )
    st.caption("New here? Load the demo data, then click a **Try asking** example.")

for i, turn in enumerate(st.session_state.chat):
    with st.chat_message("user", avatar="🧑"):
        st.write(turn["q"])
    with st.chat_message("assistant", avatar="🧠"):
        if turn.get("note"):
            st.caption(turn["note"])
        st.write(turn["a"])
        if turn.get("citations"):
            with st.expander(f"📎 {len(turn['citations'])} source(s)"):
                for c in turn["citations"]:
                    if isinstance(c, dict):
                        st.markdown(f"📄 **{c.get('doc', 'source')}** — {c.get('snippet', '')}")
                    else:
                        st.markdown(f"- {c}")
        # Feedback loop -> cognee.improve()  (narrow cols keep 👍/👎 close together)
        cols = st.columns([1, 1, 16])
        if cols[0].button("👍", key=f"up{i}"):
            st.toast("Thanks — reinforced.")
        if cols[1].button("👎", key=f"down{i}"):
            st.session_state.correcting = i

    if st.session_state.get("correcting") == i:
        fix = st.text_input("What's the correct answer / what did it miss?", key=f"fix{i}")
        if st.button("Teach Athena", key=f"teach{i}") and fix.strip():
            with st.spinner("Learning from your feedback…"):
                ok, _ = try_run(memory.teach(fix, session_id=st.session_state.session_id),
                                "Couldn't record that correction.")
            if ok:
                # Re-ask the same question so the improved answer shows up immediately —
                # the judge watches Athena get smarter.
                q_i = st.session_state.chat[i]["q"]
                with st.spinner("Re-asking with the new knowledge…"):
                    ok2, r = try_run(memory.recall(q_i, session_id=st.session_state.session_id))
                if ok2 and r:
                    st.session_state.chat.append(
                        {
                            "q": q_i,
                            "a": r["answer"],
                            "citations": r.get("citations", []),
                            "note": "✅ improved after your feedback",
                        }
                    )
                st.session_state.correcting = None
                st.rerun()

q = st.chat_input("Ask Athena about your sources…") or st.session_state.pop("pending_q", None)
if q:
    with st.spinner("Recalling with sources…"):
        ok, res = try_run(memory.recall(q, session_id=st.session_state.session_id),
                          "Athena couldn't answer that just now.")
    if ok and res:
        st.session_state.chat.append(
            {"q": q, "a": res["answer"], "citations": res.get("citations", [])}
        )
        st.rerun()
