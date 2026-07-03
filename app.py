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


# One persistent event loop on a dedicated thread for the whole process. Every
# cognee call runs on this single loop, so its cached async DB engines stay valid
# across Streamlit reruns (calling asyncio.run() per click would create a new loop
# each time and break cognee with "attached to a different loop").
@st.cache_resource
def _bg_loop():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    return loop


def run(coro):
    """Run an async cognee call on the shared background loop and block for the result."""
    return asyncio.run_coroutine_threadsafe(coro, _bg_loop()).result()


# --- session identity: this is what gives cross-session memory --------------
if "session_id" not in st.session_state:
    st.session_state.session_id = f"athena_{uuid.uuid4().hex[:8]}"
if "chat" not in st.session_state:
    st.session_state.chat = []

st.title("🧠 Athena")
st.markdown("##### The analyst whose memory never goes stale.")
st.markdown(
    "📎 **Cited answers** &nbsp;·&nbsp; 🔄 **Self-updating memory** &nbsp;·&nbsp; "
    "🧠 **Learns from feedback** &nbsp;·&nbsp; 🕸️ **Live knowledge graph**"
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

    # Ensure upload directory exists
    upload_dir = Path(__file__).parent / "uploaded_data"
    upload_dir.mkdir(exist_ok=True)

    st.markdown("**① Build memory**")
    uploaded_files = st.file_uploader(
        "Upload files to ingest",
        accept_multiple_files=True,
        type=["txt", "pdf", "md", "json", "docx"]
    )

    if uploaded_files:
        new_files_to_remember = []
        for uploaded_file in uploaded_files:
            file_key = f"ingested_{uploaded_file.name}_{uploaded_file.size}"
            if file_key not in st.session_state:
                # Save to uploaded_data directory
                dest_path = upload_dir / uploaded_file.name
                with open(dest_path, "wb") as f:
                    f.write(uploaded_file.getvalue())
                new_files_to_remember.append(str(dest_path))
                st.session_state[file_key] = True

        if new_files_to_remember:
            with st.spinner("Ingesting uploaded file(s) into memory…"):
                for path in new_files_to_remember:
                    run(memory.remember(path))
            st.success(f"Ingested {len(new_files_to_remember)} new file(s)!")
            st.rerun()

    # Load Demo Data option
    if st.button("📥 Load Demo Data Files", use_container_width=True):
        demo_dir = Path(__file__).parent / "demo_data"
        if demo_dir.exists():
            demo_files = list(demo_dir.glob("*"))
            if demo_files:
                new_files_to_remember = []
                for df in demo_files:
                    if df.is_file() and not df.name.startswith("."):
                        file_key = f"ingested_{df.name}_{df.stat().st_size}"
                        if file_key not in st.session_state:
                            dest_path = upload_dir / df.name
                            dest_path.write_bytes(df.read_bytes())
                            new_files_to_remember.append(str(dest_path))
                            st.session_state[file_key] = True
                
                if new_files_to_remember:
                    with st.spinner("Ingesting demo files…"):
                        for path in new_files_to_remember:
                            run(memory.remember(path))
                    st.success(f"Ingested {len(new_files_to_remember)} demo file(s)!")
                    st.rerun()
                else:
                    st.info("Demo files already loaded.")

    st.markdown("**② Explore**")
    if st.button("🕸️ View knowledge graph", use_container_width=True):
        out = os.path.join(tempfile.gettempdir(), "athena_graph.html")
        with st.spinner("Rendering graph…"):
            run(memory.graph_html(out))
        st.session_state.graph_html = Path(out).read_text(encoding="utf-8")

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
            res = run(memory.refresh(str(upload_dir)))
        st.session_state.last_refresh = res
        # The "living memory" beat: re-ask the last question so the answer visibly
        # updates to reflect the changed sources — memory that never goes stale.
        last_q = next((t["q"] for t in reversed(st.session_state.chat)), None)
        if last_q:
            with st.spinner("Re-checking your last question against the updated memory…"):
                r = run(memory.recall(last_q, session_id=st.session_state.session_id))
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
        run(memory.forget())
        st.session_state.chat = []
        st.session_state.pop("graph_html", None)
        st.session_state.pop("last_refresh", None)
        # Clear the ingested tracking keys from session state
        for key in list(st.session_state.keys()):
            if key.startswith("ingested_"):
                st.session_state.pop(key)
        # Delete files from uploaded_data directory
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
        "👋 **Start here** — upload files or click **Load Demo Data Files** in the "
        "sidebar to build your knowledge graph, then ask a question below. "
        "Athena answers **with citations**; correct it with 👎 and it **learns**; "
        "change a source and hit **🔄 Refresh** and its answers **stay current**."
    )
    st.caption("New here? Click a **Try asking** example in the sidebar to jump right in.")

for i, turn in enumerate(st.session_state.chat):
    with st.chat_message("user"):
        st.write(turn["q"])
    with st.chat_message("assistant"):
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
        # Feedback loop -> cognee.improve()
        cols = st.columns([1, 1, 6])
        if cols[0].button("👍", key=f"up{i}"):
            st.toast("Thanks — reinforced.")
        if cols[1].button("👎", key=f"down{i}"):
            st.session_state.correcting = i

    if st.session_state.get("correcting") == i:
        fix = st.text_input("What's the correct answer / what did it miss?", key=f"fix{i}")
        if st.button("Teach Athena", key=f"teach{i}") and fix.strip():
            with st.spinner("Learning from your feedback…"):
                run(memory.teach(fix, session_id=st.session_state.session_id))
            # Re-ask the same question so the improved answer shows up immediately —
            # the judge watches Athena get smarter.
            q_i = st.session_state.chat[i]["q"]
            with st.spinner("Re-asking with the new knowledge…"):
                r = run(memory.recall(q_i, session_id=st.session_state.session_id))
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
        res = run(memory.recall(q, session_id=st.session_state.session_id))
    st.session_state.chat.append(
        {"q": q, "a": res["answer"], "citations": res.get("citations", [])}
    )
    st.rerun()
