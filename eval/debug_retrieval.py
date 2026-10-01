"""Show dense and BM25 rankings separately for a query: python eval/debug_retrieval.py "query" [venue]"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "api"))

from app.rag.retrieval import HybridRetriever  # noqa: E402

q = sys.argv[1]
venue = sys.argv[2] if len(sys.argv) > 2 else "riverside_hall"
r = HybridRetriever()
r._refresh()
label = lambda cid: f"{r._rows[cid]['doc_id']}#{r._rows[cid]['meta'].get('heading', '')}"  # noqa: E731
print("index:", r.index_info.get("embedder_label"), r.dense_error or "")
print("-- dense")
for cid, s in r._dense(venue, q, 8):
    print(f"  {s:.3f} {label(cid)}")
print("-- bm25")
for cid, s in (r._bm25.search(q, venue, 8) if r._bm25 else []):
    print(f"  {s:.3f} {label(cid)}")
