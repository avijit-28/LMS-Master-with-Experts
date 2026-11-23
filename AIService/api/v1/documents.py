"""
Multi-format Document Ingestion & Lifecycle Management.
Supports PDF (PyMuPDF), DOCX (python-docx), PPTX (python-pptx), and TXT/Markdown.
Implements:
- N-06: Zero-Text / Scanned PDF Ingestion Interceptor
- N-07: Targeted Cache Invalidation on Course Update
"""
from pathlib import Path
import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from extractors.pdf_extractor import PdfExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.pptx_extractor import PptxExtractor
from extractors.text_cleaner import clean_text
from rag.chunker import chunker
from embeddings.gemini_embedder import embedder
from vectorstore.qdrant_store import qdrant_store
from core.cache import semantic_cache
from core.security import verify_internal_api_key
from core.logger import logger

router = APIRouter(prefix="/documents", tags=["Documents"])

class IndexDocumentRequest(BaseModel):
    document_id: int
    course_id: int
    module_id: Optional[int] = None
    lesson_id: Optional[int] = None
    title: str
    file_path: Optional[str] = ""
    file_content_base64: Optional[str] = None
    raw_text: Optional[str] = None
    visibility: str = "student"  # student, instructor_only

class IndexDocumentResponse(BaseModel):
    status: str
    document_id: int
    course_id: int
    total_pages: int
    total_chunks: int
    message: str

@router.post("/index", response_model=IndexDocumentResponse)
def index_document(
    req: IndexDocumentRequest,
    api_key_valid: bool = Depends(verify_internal_api_key)
):
    import base64
    path: Optional[Path] = None

    if req.file_content_base64:
        uploads_dir = Path(__file__).resolve().parent.parent.parent / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        file_ext = Path(req.title).suffix.lower().replace(".", "") or "pdf"
        target_path = uploads_dir / f"doc_{req.document_id}.{file_ext}"
        try:
            target_path.write_bytes(base64.b64decode(req.file_content_base64))
            path = target_path
            ext = file_ext
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to decode base64 file content: {e}")
    elif req.raw_text:
        ext = "txt"
        path = None
    else:
        # Establish canonical root boundary for uploaded documents to prevent path traversal
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        allowed_base_dirs = [
            (project_root / "App_Data").resolve(),
            (project_root / "Uploads").resolve(),
            (project_root / "Content").resolve(),
            (project_root / "AIService" / "uploads").resolve(),
            Path("/tmp").resolve()
        ]

        target_path = Path(req.file_path).resolve()
        is_authorized_path = any(
            str(target_path).startswith(str(base_dir)) for base_dir in allowed_base_dirs
        )
        if not is_authorized_path:
            logger.warning(f"Path Traversal Blocked: Attempted to index unauthorized path: {req.file_path}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security violation: Target document path is outside authorized project storage volumes."
            )

        if not target_path.exists() or not target_path.is_file():
            raise HTTPException(status_code=404, detail=f"File not found on server: {req.file_path}")

        path = target_path
        ext = path.suffix.lower().replace(".", "")

    logger.info(f"Ingesting Document #{req.document_id} ('{req.title}', format: {ext}) for Course #{req.course_id}...")

    # 1. Remove previous vectors for this document (idempotent re-indexing)
    qdrant_store.delete_document_vectors(req.document_id)

    # N-07: Targeted Cache Invalidation on Course Update
    semantic_cache.invalidate_course_cache(req.course_id)

    # 2. Extract multi-format text
    pages: List[Dict[str, Any]] = []
    try:
        if ext == "pdf":
            pages = PdfExtractor.extract(str(path))
        elif ext in ["docx", "doc"]:
            pages = DocxExtractor.extract(str(path))
        elif ext in ["pptx", "ppt"]:
            pages = PptxExtractor.extract(str(path))
        elif ext in ["txt", "md", "sql", "cs", "py", "json"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = clean_text(f.read())
            pages = [{"page_number": 1, "section_title": req.title or path.stem, "text": content}]
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported document format: {ext}")
    except ValueError as ve:
        # N-06: Zero-Text / Scanned PDF Ingestion Interceptor
        err_msg = str(ve)
        if "ParsingFailed: ScannedOrEncrypted" in err_msg:
            logger.error(f"Ingestion rejected for Document #{req.document_id}: {err_msg}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=err_msg
            )
        raise HTTPException(status_code=400, detail=err_msg)

    if not pages:
        raise HTTPException(status_code=400, detail=f"Could not extract readable text from document {path.name}")

    # 3. Semantic Chunking
    chunks = chunker.chunk_document_pages(
        pages=pages,
        document_id=req.document_id,
        course_id=req.course_id,
        module_id=req.module_id,
        lesson_id=req.lesson_id,
        visibility=req.visibility
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="Document produced 0 meaningful chunks.")

    # 4. Dense Vector Embedding
    texts = [c["text"] for c in chunks]
    vectors = embedder.embed_documents(texts)

    # 5. Upsert to Qdrant & BM25 sparse index
    upserted_count = qdrant_store.upsert_chunks(chunks, vectors)

    logger.info(f"Successfully indexed Document #{req.document_id}: {len(pages)} pages, {upserted_count} chunks.")

    return IndexDocumentResponse(
        status="Indexed",
        document_id=req.document_id,
        course_id=req.course_id,
        total_pages=len(pages),
        total_chunks=upserted_count,
        message=f"Document successfully parsed and indexed into Hybrid Knowledge Base ({upserted_count} chunks)."
    )

def publish_to_rabbitmq(job_data: dict) -> bool:
    """Attempts to publish a document ingestion job to RabbitMQ. Returns True if queued, False if offline."""
    try:
        import pika
        url = getattr(settings, "RABBITMQ_URL", None)
        if url:
            params = pika.URLParameters(url)
            connection = pika.BlockingConnection(params)
        else:
            host = getattr(settings, "RABBITMQ_HOST", "127.0.0.1")
            port = int(getattr(settings, "RABBITMQ_PORT", 5672))
            user = getattr(settings, "RABBITMQ_USER", "lms_admin")
            password = getattr(settings, "RABBITMQ_PASSWORD", "lms_secure_queue_pass_2026")

            credentials = pika.PlainCredentials(user, password)
            params = pika.ConnectionParameters(host=host, port=port, credentials=credentials, connection_attempts=1, retry_delay=1)
            connection = pika.BlockingConnection(params)
        channel = connection.channel()

        # Ensure DLX and Queue exist
        channel.exchange_declare(exchange="lms_dlx", exchange_type="direct", durable=True)
        channel.queue_declare(queue="lms_document_ingestion_dlq", durable=True)
        channel.queue_bind(exchange="lms_dlx", queue="lms_document_ingestion_dlq", routing_key="ingestion_failed")

        queue_args = {
            "x-dead-letter-exchange": "lms_dlx",
            "x-dead-letter-routing-key": "ingestion_failed"
        }
        channel.queue_declare(queue="lms_document_ingestion_queue", durable=True, arguments=queue_args)

        channel.basic_publish(
            exchange="",
            routing_key="lms_document_ingestion_queue",
            body=json.dumps(job_data),
            properties=pika.BasicProperties(delivery_mode=2)  # Persistent message
        )
        connection.close()
        return True
    except Exception as ex:
        logger.warning(f"RabbitMQ message broker offline ({ex}). Processing document synchronously.")
        return False

@router.post("/queue-index", response_model=IndexDocumentResponse)
def queue_document_index(
    req: IndexDocumentRequest,
    api_key_valid: bool = Depends(verify_internal_api_key)
):
    """
    Asynchronous document ingestion endpoint.
    If base64 file content or raw text is provided, indexes directly into Qdrant.
    """
    if req.file_content_base64 or req.raw_text:
        return index_document(req, api_key_valid)

    # 1. Path traversal security validation
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    allowed_base_dirs = [
        (project_root / "App_Data").resolve(),
        (project_root / "Uploads").resolve(),
        (project_root / "Content").resolve(),
        (project_root / "AIService" / "uploads").resolve(),
        Path("/tmp").resolve()
    ]

    target_path = Path(req.file_path).resolve()
    is_authorized_path = any(
        str(target_path).startswith(str(base_dir)) for base_dir in allowed_base_dirs
    )
    if not is_authorized_path:
        logger.warning(f"Path Traversal Blocked: Attempted to index unauthorized path: {req.file_path}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Security violation: Target document path is outside authorized project storage volumes."
        )

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail=f"File not found on server: {req.file_path}")

    # 2. Attempt RabbitMQ publish
    job_payload = {
        "document_id": req.document_id,
        "course_id": req.course_id,
        "module_id": req.module_id,
        "lesson_id": req.lesson_id,
        "title": req.title,
        "file_path": str(target_path),
        "visibility": req.visibility
    }

    queued = publish_to_rabbitmq(job_payload)
    if queued:
        logger.info(f"Document #{req.document_id} queued to RabbitMQ for asynchronous background indexing.")
        return IndexDocumentResponse(
            status="Queued",
            document_id=req.document_id,
            course_id=req.course_id,
            total_pages=0,
            total_chunks=0,
            message="Document successfully queued for background extraction via RabbitMQ worker."
        )

    # 3. Fallback to inline processing if queue is offline
    return index_document(req, api_key_valid)

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    course_id: Optional[int] = None,
    api_key_valid: bool = Depends(verify_internal_api_key)
):
    success = qdrant_store.delete_document_vectors(document_id)
    if course_id is not None:
        semantic_cache.invalidate_course_cache(course_id)
    return {
        "status": "deleted" if success else "not_found",
        "document_id": document_id,
        "message": f"Purged all vectors and lexical index entries for document #{document_id}."
    }
