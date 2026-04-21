"""
rag.py — Retrieval-Augmented Generation pipeline.

At startup:
  1. Reads all .txt files from the knowledge/ directory
  2. Chunks them into ~400-word segments with 50-word overlap
  3. Embeds them using sentence-transformers/all-MiniLM-L6-v2
  4. Stores embeddings in a FAISS index

At query time:
  - Embeds the user query
  - Retrieves top-k most similar chunks
  - Returns them as a context string for injection into the Gemini prompt
"""

import os
import glob
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────
KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "knowledge")
CHUNK_SIZE    = 400   # words per chunk
CHUNK_OVERLAP = 50    # words of overlap between consecutive chunks
TOP_K         = 3     # chunks to retrieve per query
EMBED_MODEL   = "sentence-transformers/all-MiniLM-L6-v2"

# ── State (populated at startup) ──────────────────────────────────────────
_model:  SentenceTransformer = None
_index:  faiss.IndexFlatIP   = None   # Inner-product index (cosine after normalisation)
_chunks: list[str]           = []


# ── Chunking ──────────────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping word-windows."""
    words  = text.split()
    chunks = []
    start  = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


# ── Index build ────────────────────────────────────────────────────────────

def build_index():
    """
    Load all knowledge files, chunk them, embed, and build FAISS index.
    Called once during FastAPI startup.
    """
    global _model, _index, _chunks

    print("[RAG] Loading embedding model …")
    _model = SentenceTransformer(EMBED_MODEL)

    txt_files = glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt"))
    if not txt_files:
        print("[RAG] WARNING — no knowledge files found in", KNOWLEDGE_DIR)
        return

    all_chunks = []
    for path in txt_files:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        file_chunks = _chunk_text(text)
        all_chunks.extend(file_chunks)
        print(f"[RAG]   {os.path.basename(path)} → {len(file_chunks)} chunks")

    _chunks = all_chunks
    print(f"[RAG] Total chunks: {len(_chunks)}")

    # Embed all chunks
    embeddings = _model.encode(_chunks, convert_to_numpy=True, show_progress_bar=True)

    # L2-normalise → inner product becomes cosine similarity
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / np.maximum(norms, 1e-9)

    dim    = embeddings.shape[1]
    _index = faiss.IndexFlatIP(dim)
    _index.add(embeddings.astype("float32"))
    print(f"[RAG] FAISS index built: {_index.ntotal} vectors, dim={dim}")


# ── Retrieval ──────────────────────────────────────────────────────────────

def retrieve(query: str, top_k: int = TOP_K) -> str:
    """
    Embed query, search FAISS, return top_k chunks joined as a single string.
    Returns empty string if index is not built.
    """
    if _index is None or _model is None or not _chunks:
        return ""

    q_vec = _model.encode([query], convert_to_numpy=True).astype("float32")
    q_vec /= np.maximum(np.linalg.norm(q_vec, axis=1, keepdims=True), 1e-9)

    distances, indices = _index.search(q_vec, top_k)
    retrieved = []
    for i, idx in enumerate(indices[0]):
        if idx < len(_chunks) and distances[0][i] > 0.1:   # threshold
            retrieved.append(_chunks[idx])

    if not retrieved:
        return ""

    return "\n\n---\n\n".join(retrieved)
