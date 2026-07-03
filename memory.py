"""Athena's memory layer — a thin, honest wrapper over cognee's lifecycle.

Every function here maps 1:1 to a cognee memory verb, so the agent's behaviour
*is* the cognee lifecycle:

    remember()  -> cognee.add + cognee.cognify        (ingest -> knowledge graph)
    recall()    -> cognee.recall(include_references=True)  (cited answer)
    teach()     -> add a correction + cognee.improve  (learn from feedback)
    forget()    -> cognee.forget                       (drop stale sources)
    refresh()   -> cognee.incremental_update           (auto-refresh changed sources)
    graph_html()-> cognee.visualize_graph              (see the memory)

Kept deliberately small; the Streamlit app calls these.
"""

import glob
import os
import re
from typing import Any, Optional
from urllib.parse import unquote, urlparse

import cognee
from cognee.api.v1.search import SearchType

DATASET = os.getenv("ATHENA_DATASET", "athena")


# --------------------------------------------------------------------------- #
# pre-flight: catch scanned / image-only PDFs (no text layer) before ingest so
# we can tell the user, instead of silently refusing every question later.
# --------------------------------------------------------------------------- #
def _local_path(paths) -> Optional[str]:
    """Turn a folder path or a file:// URL into a local filesystem path (best effort)."""
    if not isinstance(paths, str):
        return None
    p = paths.strip()
    if p.startswith("file://"):
        p = unquote(urlparse(p).path)
        # 'file:///C:/x' -> urlparse gives '/C:/x'; drop the leading slash on Windows
        if os.name == "nt" and len(p) > 2 and p[0] == "/" and p[2] == ":":
            p = p[1:]
    return p


def _pdf_text_len(path: str) -> int:
    """Chars pypdf (cognee's extractor) can pull from a PDF. -1 if it can't be read."""
    try:
        from pypdf import PdfReader
    except Exception:
        return -1
    try:
        reader = PdfReader(path)
        return sum(len(pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        return -1


def _scanned_pdf_paths(paths) -> list:
    """Full paths of PDFs in `paths` whose text layer is ~empty — i.e. scanned/image
    PDFs that need OCR. `paths` may be a folder, a single file:// URL or path, or a
    list of any of those."""
    items = paths if isinstance(paths, (list, tuple)) else [paths]
    pdfs = []
    for item in items:
        local = _local_path(item)
        if not local:
            continue
        if os.path.isdir(local):
            pdfs += glob.glob(os.path.join(local, "**", "*.pdf"), recursive=True)
        elif local.lower().endswith(".pdf") and os.path.isfile(local):
            pdfs.append(local)
    return [f for f in pdfs if 0 <= _pdf_text_len(f) < 20]


def unreadable_pdfs(paths) -> list:
    """Basenames of scanned/image PDFs found under `paths` (for UI messages)."""
    return [os.path.basename(f) for f in _scanned_pdf_paths(paths)]


# --------------------------------------------------------------------------- #
# OCR — read scanned/image PDFs that have no text layer. Pip-only stack
# (PyMuPDF renders pages, rapidocr-onnxruntime does OCR) so it deploys anywhere
# with no system binaries. Lazily initialised so startup stays instant.
# --------------------------------------------------------------------------- #
_OCR_DPI = 300
_OCR_THRESHOLD = 165  # grayscale cutoff: lighter pixels (watermarks/background) -> white
_ocr_engine = None


def _get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        from rapidocr_onnxruntime import RapidOCR  # bundles its own models; no downloads

        _ocr_engine = RapidOCR()
    return _ocr_engine


def ocr_pdf_text(path: str) -> str:
    """OCR a scanned PDF into plain text. Renders each page, drops the light background
    so faint watermarks don't swamp the real text, then recognises it. Returns "" if OCR
    isn't installed or fails — callers treat that as 'still unreadable'."""
    try:
        import io

        import fitz  # PyMuPDF
        from PIL import Image

        engine = _get_ocr()
    except Exception:
        return ""
    try:
        pages_text = []
        doc = fitz.open(path)
        for page in doc:
            pix = page.get_pixmap(dpi=_OCR_DPI)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
            img = img.point(lambda x: 255 if x > _OCR_THRESHOLD else 0)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            result, _ = engine(buf.getvalue())
            pages_text.append("\n".join(line[1] for line in (result or [])))
        doc.close()
        return "\n".join(pages_text).strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# helpers — normalise cognee's `search_result: Any` into display-ready text
# --------------------------------------------------------------------------- #
def _as_text(value: Any) -> str:
    """Flatten whatever a retriever returned into a readable string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("answer", "text", "content", "completion"):
            if value.get(key):
                return str(value[key])
        return str(value)
    if isinstance(value, (list, tuple)):
        return "\n\n".join(_as_text(v) for v in value if v)
    # cognee returns typed result objects (e.g. GraphCompletion) — the answer is on
    # a `.text`/`.answer` attribute; fall back to str() only if none is present.
    for attr in ("text", "answer", "completion", "content"):
        inner = getattr(value, attr, None)
        if inner:
            return _as_text(inner)
    return str(value)


# Cognee's graph-completion answer often appends an "Evidence:" block listing the
# source chunks, e.g.  - chunk 1 of document project_apollo (data_id: ...): "text"
_EVIDENCE_LINE = re.compile(
    r"-\s*chunk\s+\d+\s+of\s+document\s+(?P<doc>[^\(]+?)\s*\(data_id[^)]*\)\s*:\s*"
    r"[\"']?(?P<snippet>.+?)[\"']?\s*(?=(?:-\s*chunk)|\Z)",
    re.DOTALL | re.IGNORECASE,
)


def _split_answer_and_evidence(text: str) -> tuple[str, list[dict]]:
    """Separate the clean answer from cognee's appended 'Evidence:' block and
    parse each source into {'doc', 'snippet'} for tidy citation display."""
    if not text:
        return "", []
    parts = re.split(r"\n\s*Evidence\s*:\s*\n?", text, maxsplit=1, flags=re.IGNORECASE)
    answer = parts[0].strip()
    citations: list[dict] = []
    if len(parts) > 1:
        for m in _EVIDENCE_LINE.finditer(parts[1]):
            snippet = " ".join(m.group("snippet").split())
            citations.append({"doc": m.group("doc").strip(), "snippet": snippet[:220]})
    return answer, citations


def _pick_current_answer(results):
    """recall() with a session_id returns [session history…, fresh graph answer…].
    results[0] is therefore the OLDEST session entry — returning it shows a previous
    turn's answer. The answer to the CURRENT query is the graph-tagged result
    (cognee tags each entry source="graph"/"session" and appends graph last), so
    prefer that; fall back to the last entry, then the first."""
    if not results:
        return None
    graph_entries = [r for r in results if getattr(r, "source", None) == "graph"]
    if graph_entries:
        return graph_entries[0]
    return results[-1]


# When the answer isn't in memory, cognee returns an honest refusal like
# "The provided context does not contain information about …". We detect that so
# we don't decorate a non-answer with unrelated fallback sources.
_REFUSAL = re.compile(
    r"(does not (?:contain|include|provide|mention)|provided context does not|"
    r"no (?:information|relevant|data|mention)|could ?n'?t find|cannot answer)",
    re.IGNORECASE,
)


def _looks_like_refusal(answer: str) -> bool:
    return bool(answer) and bool(_REFUSAL.search(answer))


# --------------------------------------------------------------------------- #
# the cognee lifecycle
# --------------------------------------------------------------------------- #
async def remember(paths) -> dict:
    """Ingest files/folders/text and build the knowledge graph. Scanned/image PDFs
    (no text layer) are OCR'd first so they become searchable memory too; anything OCR
    still can't read is reported back so the UI can say so instead of failing quietly."""
    ocr_ok, ocr_fail = [], []
    for fp in _scanned_pdf_paths(paths):
        name = os.path.basename(fp)
        text = ocr_pdf_text(fp)
        if text:
            await cognee.add(f"[Document: {name}]\n\n{text}", dataset_name=DATASET)
            ocr_ok.append(name)
        else:
            ocr_fail.append(name)
    # Add each source (folder, file, or list of files), then cognify once for the batch.
    for item in (paths if isinstance(paths, (list, tuple)) else [paths]):
        await cognee.add(item, dataset_name=DATASET)
    await cognee.cognify(datasets=[DATASET])
    return {"ok": True, "dataset": DATASET, "ocr": ocr_ok, "unreadable": ocr_fail}


async def refresh(folder: str, prune: bool = True) -> dict:
    """Auto-refresh memory from a source folder (upstream feature #3669):
    re-cognify only changed files, prune sources removed from disk."""
    return await cognee.incremental_update(folder, dataset_name=DATASET, prune_removed=prune)


async def recall(query: str, session_id: Optional[str] = None) -> dict:
    """Answer a question with citations, scoped to this session's memory."""
    results = await cognee.recall(
        query,
        datasets=[DATASET],
        session_id=session_id,
        include_references=True,
    )
    # recall() merges [session history…, fresh graph answer]. results[0] is the
    # OLDEST session entry — using it returns a previous turn's answer. The answer
    # to the CURRENT question is the graph-tagged result (appended last), so pick
    # that; fall back to the last entry, then the first.
    answer_entry = _pick_current_answer(results)
    text = _as_text(getattr(answer_entry, "search_result", answer_entry)) if answer_entry else ""
    answer, citations = _split_answer_and_evidence(text)

    # If Athena is honestly saying "that's not in my memory", don't attach fallback
    # source chunks — a non-answer shouldn't look like it has evidence.
    if _looks_like_refusal(answer):
        return {"answer": answer, "citations": []}

    # Fallback provenance if the answer carried no evidence block: pull source chunks.
    if not citations:
        try:
            chunks = await cognee.search(
                query_text=query,
                query_type=SearchType.CHUNKS,
                datasets=[DATASET],
                top_k=3,
            )
            for c in chunks or []:
                snippet = " ".join(_as_text(getattr(c, "search_result", c)).split())
                if snippet:
                    citations.append({"doc": "source", "snippet": snippet[:220]})
        except Exception:
            pass

    return {"answer": answer or "(no answer found in memory yet)", "citations": citations}


async def teach(correction: str, session_id: Optional[str] = None) -> dict:
    """Learn from feedback: remember the correction, then enrich the graph so
    future recalls reflect it."""
    await cognee.add(correction, dataset_name=DATASET)
    await cognee.cognify(datasets=[DATASET])
    try:
        # Improve THIS dataset (default is 'main_dataset'), not the wrong one.
        await cognee.improve(DATASET)
    except Exception:
        pass
    return {"ok": True}


async def forget() -> dict:
    """Surgically drop this dataset's memory. Never raises (nothing to forget on a
    fresh/empty dataset would otherwise throw)."""
    try:
        await cognee.forget(dataset=DATASET)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


async def graph_html(destination_file_path: str) -> str:
    """Render THIS dataset's knowledge graph to a standalone HTML file."""
    await cognee.visualize_graph(destination_file_path=destination_file_path, dataset=DATASET)
    return destination_file_path
