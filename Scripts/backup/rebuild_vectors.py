#!/usr/bin/env python3
"""
Deterministic Vector Reconstruction Script for EduPlatform LMS.
Rebuilds Qdrant dense vector index directly from dbo.AI_DocumentChunks in SQL Server.
Ensures zero data loss even if vector storage is completely unrecoverable.
"""
import os
import sys
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent / "AIService"
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(level=logging.INFO, format="[%(asctime)s UTC] %(levelname)s: %(message)s")
logger = logging.getLogger("rebuild_vectors")

try:
    import pyodbc
except ImportError:
    pyodbc = None

def rebuild():
    if pyodbc is None:
        logger.error("pyodbc is required for SQL Server connection. Install with: pip install pyodbc")
        sys.exit(1)

    from config import settings
    from embeddings.gemini_embedder import embedder
    from vectorstore.qdrant_store import qdrant_store

    conn_str = os.getenv(
        "DATABASE_CONNECTION_STRING",
        "Driver={ODBC Driver 17 for SQL Server};Server=localhost;Database=LMS;Trusted_Connection=yes;"
    )

    logger.info("Connecting to SQL Server database...")
    try:
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
    except Exception as ex:
        logger.error(f"Failed to connect to database: {ex}")
        sys.exit(1)

    logger.info("Querying dbo.AI_DocumentChunks...")
    cursor.execute("""
        SELECT ChunkId, DocumentId, CourseId, ModuleId, LessonId, 
               ChunkText, PageNumber, SectionTitle, Visibility
        FROM dbo.AI_DocumentChunks
        ORDER BY CourseId, DocumentId, ChunkId
    """)

    rows = cursor.fetchall()
    logger.info(f"Retrieved {len(rows)} chunks from database. Beginning vector reconstruction...")

    batch_size = 50
    total_processed = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i + batch_size]
        chunks = []
        texts = []

        for r in batch:
            chunk = {
                "chunk_id": str(r[0]),
                "document_id": r[1],
                "course_id": r[2],
                "module_id": r[3],
                "lesson_id": r[4],
                "text": r[5] or "",
                "page_number": r[6] or 1,
                "section_title": r[7] or "Document Chunk",
                "visibility": r[8] or "student"
            }
            chunks.append(chunk)
            texts.append(chunk["text"])

        # Embed batch
        vectors = embedder.embed_documents(texts)
        # Upsert batch
        qdrant_store.upsert_chunks(chunks, vectors)
        total_processed += len(chunks)
        logger.info(f"Indexed {total_processed}/{len(rows)} chunks into Qdrant...")

    conn.close()
    logger.info(f"[SUCCESS] Vector rebuild complete! Successfully restored {total_processed} chunks into Qdrant.")

if __name__ == "__main__":
    rebuild()
