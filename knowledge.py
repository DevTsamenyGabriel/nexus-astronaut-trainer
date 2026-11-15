"""NEXUS knowledge layer (Sage): RAG answers from NASA documents, with citations.

ask(question) -> {"answer": str, "sources": [str]}. Never raises.
Explains only. It never generates events, numbers, or outcomes.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- Copied from backend.py (do not change) ---------------------------------
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
# api key:  os.environ.get("GROQ_API_KEY", "").strip()
# model:    os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip() or "openai/gpt-oss-120b"
# client:   OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
# -----------------------------------------------------------------------------

DB_PATH = str(Path(__file__).resolve().parent / "chroma_db")
COLLECTION = "nasa_docs"
TOP_K = 3
MAX_DISTANCE = 1.2            # same as test_rag.py
CITE_MAX = 3                  # chunks sent to Groq AND cited (same set)
REFUSAL = "I don't have that in my NASA sources."
SAFETY = ("Note: radiation numbers are mission-planning references, not medical "
          "clearance. Shelter and EVA abort are simulated mission protocols, not "
          "real emergency advice.")

SYSTEM_PROMPT = (
    "You are the knowledge assistant of a mission-training simulator. Answer the "
    "question using ONLY the numbered NASA excerpts provided. Do not use outside "
    "knowledge. Do not invent numbers, events, or outcomes. Do not state calendar "
    "years from the Artemis Plan or Mars DRA as current facts. Treat radiation "
    "values as mission-planning references, not medical clearance. Answer in 2-4 "
    "plain sentences with no markdown. If the excerpts do not contain the answer, "
    f'reply with exactly: {REFUSAL}'
)

_collection = None


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        client = chromadb.PersistentClient(path=DB_PATH)
        _collection = client.get_collection(COLLECTION)   # read-only use
    return _collection


def _citation(meta: dict) -> str:
    label = meta.get("source_label") or meta.get("doc_title") or "NASA document"
    section = meta.get("section_path") or "n/a"
    p0, p1 = meta.get("page_start"), meta.get("page_end")
    if p0 is None:
        page = "n/a"
    elif p1 is None or p1 == p0:
        page = str(p0)
    else:
        page = f"{p0}-{p1}"
    return f"Source: [{label}], Sec. {section}, p. {page}"


def _unique(items):
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _retrieve(question: str):
    """Return passing chunks as (text, meta, distance), nearest first."""
    res = _get_collection().query(query_texts=[question], n_results=TOP_K)
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    return [(d, m or {}, x) for d, m, x in zip(docs, metas, dists) if x <= MAX_DISTANCE]


def _groq_answer(question: str, chunks) -> str:
    from openai import OpenAI
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("no GROQ_API_KEY")
    model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b").strip() \
        or "openai/gpt-oss-120b"
    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL,
                    timeout=20, max_retries=1)
    excerpts = "\n\n".join(f"[{i + 1}] {text}" for i, (text, _, _) in enumerate(chunks))
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Excerpts:\n{excerpts}\n\nQuestion: {question}"},
        ],
        temperature=0,
        max_tokens=800,   # reasoning models spend tokens thinking before answering
    )
    out = (resp.choices[0].message.content or "").strip()
    if not out:
        raise RuntimeError("empty answer")
    return out


def _is_refusal(text: str) -> bool:
    return REFUSAL.rstrip(".").lower() in text.lower()


def _clean_excerpt(text: str, limit: int = 320) -> str:
    """Display only: drop the 'Document > Section (PDF p. N)' breadcrumb, HTML, markdown,
    table/figure captions and leading fragments; start at a real sentence and trim to a
    sentence boundary. Never changes sources or answers."""
    import re as _re
    t = str(text or "")
    sup = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    t = _re.sub(r"<sup>(\d)</sup>", lambda m: sup[int(m.group(1))], t)
    t = _re.sub(r"<[^>]+>", "", t)
    marker = _re.search(r"\(PDF p\.\s*\d+\)\s*", t[:700])
    if marker:
        t = t[marker.end():]
    t = _re.sub(r"[*#_`]+", "", t)
    t = " ".join(t.split())
    # drop a leading table/figure caption sentence
    t = _re.sub(r"^(?:Table|Figure|Fig\.)\s+\d+[^.]*\.\s*", "", t)
    # if it starts mid-sentence (formula, citation fragment), jump to the next real sentence
    if t and not _re.match(r"[A-Z][a-z]{2,}", t):
        m = _re.search(r"[.;)]\s+([A-Z][a-z]{2,}[^.]{25,})", t)
        if m:
            t = t[m.start(1):]
    if len(t) > limit:
        cut = t[:limit]
        end = max(cut.rfind(". "), cut.rfind("; "))
        t = cut[:end + 1] if end > 120 else cut.rstrip() + "..."
    return t


_STOP = {"why", "should", "during", "what", "does", "are", "the", "how", "much",
         "with", "from", "that", "this", "have", "your", "about", "which", "and",
         "compared", "performing"}


_BAD_SENT = re.compile(r"(table|figure|fig\.|appendix|note:|gm/cm|et al\.)", re.I)


def _score_sentence(sentence: str, words) -> float:
    """Prefer a plain, readable sentence that matches the question. Display choice only:
    the sentence itself is never edited."""
    low = sentence.lower()
    score = sum(2.0 for w in words if w[:5] in low)
    if _BAD_SENT.search(sentence):
        score -= 6.0
    score -= sum(char.isdigit() for char in sentence) * 0.4
    if not sentence[:1].isupper():
        score -= 3.0
    length = len(sentence)
    if 70 <= length <= 230:
        score += 2.0
    elif length < 55:
        score -= 2.0
    return score


def evidence(question: str, prefer=None, limit: int = 240) -> dict:
    """Retrieval only: the clearest sentence from the retrieved NASA passages, verbatim,
    plus its citation. No AI call, so it is instant and works offline. Never raises."""
    empty = {"text": "", "source": "", "ok": False}
    try:
        q = (question or "").strip()
        chunks = _retrieve(q)
        if not chunks:
            return empty
        words = [w for w in re.findall(r"[a-z]+", q.lower())
                 if len(w) >= 4 and w not in _STOP]
        best, best_score, best_meta = "", -999.0, {}
        for text, meta, _distance in chunks:
            full = _clean_excerpt(text, 4000)
            if not full:
                continue
            for part in re.split(r"(?<=[.!?])\s+", full):
                sentence = part.strip()
                if len(sentence) < 45:
                    continue
                score = _score_sentence(sentence, words)
                if prefer:
                    low = sentence.lower()
                    score += sum(10.0 for p in prefer if str(p).lower() in low)
                if score > best_score:
                    best, best_score, best_meta = sentence, score, meta
        if not best:
            text, best_meta, _distance = chunks[0]
            best = _clean_excerpt(text, 240)
        if not best:
            return empty
        if len(best) > limit:
            cut = best[:limit]
            space = cut.rfind(" ")
            best = (cut[:space] if space > 0 else cut).rstrip(" ,;:") + "..."
        return {"text": best, "source": _citation(best_meta), "ok": True}
    except Exception:
        return empty


def ask(question: str) -> dict:
    """Answer from NASA chunks. Citations are returned separately for display."""
    try:
        question = (question or "").strip()
        if not question:
            return {"answer": REFUSAL, "sources": []}

        try:
            chunks = _retrieve(question)
        except Exception:
            return {"answer": "AI: OFFLINE. The NASA index is unavailable.",
                    "sources": []}

        if not chunks:
            return {"answer": REFUSAL, "sources": []}

        used = chunks[:CITE_MAX]
        sources = _unique(_citation(meta) for _, meta, _ in used)

        try:
            out = _groq_answer(question, used)
        except Exception:
            excerpts = "\n\n".join(
                f"- {_clean_excerpt(text)}" for text, _, _ in used[:2])
            return {
                "answer": f"AI: OFFLINE\n\nRetrieved NASA text:\n{excerpts}\n\n{SAFETY}",
                "sources": sources,
            }

        if _is_refusal(out):
            return {"answer": REFUSAL, "sources": []}

        return {"answer": f"{out}\n\n{SAFETY}", "sources": sources}
    except Exception:
        return {"answer": "AI: OFFLINE", "sources": []}
