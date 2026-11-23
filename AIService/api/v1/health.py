"""
Telemetry and Health Diagnostics Endpoint.
"""
from fastapi import APIRouter
from vectorstore.qdrant_store import qdrant_store
from embeddings.gemini_embedder import embedder
from core.cache import semantic_cache
from config import settings

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def get_health():
    redis_status = "disabled"
    if settings.REDIS_URL or settings.UPSTASH_REDIS_REST_URL:
        redis_status = "connected" if semantic_cache.has_redis else "fallback_memory"

    rabbitmq_status = "disabled"
    if settings.RABBITMQ_URL or settings.RABBITMQ_HOST:
        rabbitmq_status = "configured"

    return {
        "status": "healthy",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "vector_store": {
            "mode": "embedded_disk",
            "collection": settings.QDRANT_COLLECTION,
            "total_vectors": qdrant_store.count(),
            "dimension": embedder.dimension
        },
        "semantic_cache": {
            "enabled": settings.ENABLE_SEMANTIC_CACHE,
            "cached_entries": len(semantic_cache.entries),
            "threshold": settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
            "distributed_backend": redis_status,
            "redis_active": semantic_cache.has_redis
        },
        "message_broker": {
            "rabbitmq_status": rabbitmq_status,
            "provider": "CloudAMQP" if "cloudamqp" in (settings.RABBITMQ_URL or "") else "Standard"
        },
        "llm_cascading": {
            "primary": settings.DEFAULT_LLM_PROVIDER,
            "primary_model": settings.GEMINI_MODEL,
            "failover": settings.FAILOVER_LLM_PROVIDER,
            "failover_model": settings.GROQ_MODEL
        },
        "pillars_active": [
            "Pillar 1: Agentic RAG & Self-Correction (Self-RAG / CRAG)",
            "Pillar 2: Hybrid Search (Dense + Sparse BM25) + RRF Re-Ranking",
            "Pillar 3: Production LLMOps & Evaluation Benchmark Tracer",
            "Pillar 4: Model Cascading & Semantic Caching Layer",
            "Pillar 5: Multi-Modal Document Extraction & Code Sandbox Tutor",
            "Pillar 6: Adversarial Jailbreak & Hard RBAC Boundary Defense"
        ]
    }
