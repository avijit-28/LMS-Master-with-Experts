"""
Pillar 2: Reciprocal Rank Fusion (RRF) & Re-Ranking with Dual-Score Gating.
Fuses dense semantic vector rankings with sparse BM25 lexical rankings:
RRF(d) = sum( 1 / (k + rank_m(d)) )
Applies Dual-Score Gating to filter out low-confidence/hallucinatory chunks.
"""
from typing import List, Dict, Any
from config import settings
from core.logger import logger

def reciprocal_rank_fusion(
    dense_results: List[Dict[str, Any]],
    sparse_results: List[Dict[str, Any]],
    top_k: int = 5,
    rrf_k: int = 60,
    min_dense_threshold: float = 0.35,
    min_bm25_threshold: float = 0.50
) -> List[Dict[str, Any]]:
    """
    Combines dense semantic hits and sparse keyword hits using RRF with Dual-Score Gating.
    Prevents low-similarity hallucinations by discarding chunks that fail both semantic and keyword thresholds.
    """
    fused_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict[str, Any]] = {}
    passed_gate_chunks = set()

    # 1. Process Dense Rankings with similarity gating
    for rank, hit in enumerate(dense_results, 1):
        chunk_id = str(hit.get("chunk_id"))
        sim = float(hit.get("similarity", 0.0))

        # Gate check: only contribute score if meets minimum semantic relevance
        if sim >= min_dense_threshold:
            passed_gate_chunks.add(chunk_id)
            doc_map[chunk_id] = hit
            score = 1.0 / (rrf_k + rank)
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (score * settings.DENSE_WEIGHT)
        else:
            logger.debug(f"Dense chunk {chunk_id} below threshold ({sim} < {min_dense_threshold})")

    # 2. Process Sparse BM25 Rankings with lexical gating
    for rank, hit in enumerate(sparse_results, 1):
        chunk_id = str(hit.get("chunk_id"))
        bm25_score = float(hit.get("bm25_score", 0.0))

        # Gate check: only contribute score if meets minimum keyword relevance
        if bm25_score >= min_bm25_threshold:
            passed_gate_chunks.add(chunk_id)
            if chunk_id not in doc_map:
                doc_map[chunk_id] = hit
            score = 1.0 / (rrf_k + rank)
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + (score * settings.SPARSE_WEIGHT)
        else:
            logger.debug(f"Sparse chunk {chunk_id} below threshold ({bm25_score} < {min_bm25_threshold})")

    # 3. Only keep chunks that passed at least one of the quality gates
    valid_fused = {k: v for k, v in fused_scores.items() if k in passed_gate_chunks}

    # 4. Sort by fused RRF score
    sorted_chunks = sorted(valid_fused.items(), key=lambda x: x[1], reverse=True)

    final_results: List[Dict[str, Any]] = []
    for rank, (chunk_id, score) in enumerate(sorted_chunks[:top_k], 1):
        doc = dict(doc_map[chunk_id])
        doc["rrf_rank"] = rank
        doc["fused_score"] = round(score, 5)
        final_results.append(doc)

    logger.info(f"RRF Dual-Score Fusion completed: {len(dense_results)} dense + {len(sparse_results)} sparse -> {len(final_results)} qualified chunks.")
    return final_results
