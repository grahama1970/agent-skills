from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import faiss
import numpy as np

app = FastAPI(title="Vector Store Service")

# Global Index State
index: Optional[faiss.IndexFlatIP] = None
dimension: int = 0
stored_ids: List[str] = []

class IndexRequest(BaseModel):
    ids: List[str]
    vectors: List[List[float]]
    reset: bool = False

class SearchRequest(BaseModel):
    query: Optional[List[float]] = None
    queries: Optional[List[List[float]]] = None
    k: int = 10

class SearchResponse(BaseModel):
    ids: List[str]
    scores: List[float]

class BatchSearchResponse(BaseModel):
    ids: List[List[str]]
    scores: List[List[float]]

@app.post("/index")
async def add_vectors(req: IndexRequest):
    global index, dimension, stored_ids
    
    if req.reset:
        index = None
        stored_ids = []
        dimension = 0

    if not req.ids or not req.vectors:
        return {"count": len(stored_ids)}

    if len(req.ids) != len(req.vectors):
        raise HTTPException(status_code=400, detail="Mismatched ids and vectors length")

    vecs = np.array(req.vectors, dtype='float32')
    
    # Normalize for Inner Product (Cosine Similarity)
    faiss.normalize_L2(vecs)

    new_dim = vecs.shape[1]
    
    if index is None:
        dimension = new_dim
        index = faiss.IndexFlatIP(dimension)
    elif dimension != new_dim:
        raise HTTPException(status_code=400, detail=f"Dimension mismatch. Expected {dimension}, got {new_dim}")

    index.add(vecs)
    stored_ids.extend(req.ids)
    
    return {"count": len(stored_ids)}

@app.post("/search")
async def search(req: SearchRequest):
    global index
    
    if index is None or index.ntotal == 0:
        if req.queries:
            return {"ids": [], "scores": []}
        return {"ids": [], "scores": []}

    is_batch = req.queries is not None
    
    if is_batch:
        q_raw = req.queries
    elif req.query:
        q_raw = [req.query]
    else:
        raise HTTPException(status_code=400, detail="Either 'query' or 'queries' is required")

    qvec = np.array(q_raw, dtype='float32')
    faiss.normalize_L2(qvec)
    
    if qvec.shape[1] != dimension:
        raise HTTPException(status_code=400, detail=f"Dimension mismatch. Expected {dimension}, got {qvec.shape[1]}")

    k = min(req.k, index.ntotal)
    D, I = index.search(qvec, k)
    
    res_ids_batch = []
    res_scores_batch = []
    
    for i in range(len(q_raw)):
        row_ids = []
        row_scores = []
        for score, idx in zip(D[i], I[i]):
            if idx != -1 and idx < len(stored_ids):
                row_ids.append(stored_ids[idx])
                row_scores.append(float(score))
        res_ids_batch.append(row_ids)
        res_scores_batch.append(row_scores)
            
    if is_batch:
        return {"ids": res_ids_batch, "scores": res_scores_batch}
    else:
        return {"ids": res_ids_batch[0], "scores": res_scores_batch[0]}

@app.delete("/reset")
async def reset():
    global index, stored_ids, dimension
    index = None
    stored_ids = []
    dimension = 0
    return {"status": "reset"}

@app.get("/info")
async def info():
    return {
        "count": len(stored_ids) if stored_ids else 0,
        "dimension": dimension,
        "backend": "faiss-cpu",
        "service": "vector-store",
        "status": "ready"
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.post("/shutdown")
async def shutdown():
    """Gracefully shutdown the service."""
    import os, asyncio, sys
    print("Shutdown requested via API", file=sys.stderr)
    asyncio.get_event_loop().call_later(0.5, lambda: os._exit(0))
    return {"status": "shutting_down"}

@app.post("/reload")
async def reload():
    """Reload the service (resets index for transient logic)."""
    global index, stored_ids, dimension
    print("Reload requested via API (Resetting Index)", file=sys.stderr)
    index = None
    stored_ids = []
    dimension = 0
    return {"status": "reloaded", "count": 0}
