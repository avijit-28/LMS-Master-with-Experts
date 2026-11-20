"""
EduPlatform LMS: Asynchronous Document Ingestion Worker.
Consumes document ingestion jobs from RabbitMQ, extracts text, chunks,
embeds via Gemini text-embedding-004, upserts into Qdrant, and updates SQL Server.
Implements:
- Asynchronous task processing for 100+ page course textbooks
- Dead-Letter Queue (DLQ) isolation for corrupted/scanned PDFs
- Zero worker death on unrecoverable extraction errors
"""
import os
import sys
import json
import logging
from pathlib import Path

# Ensure AIService root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import pika
except ImportError:
    pika = None

from config import settings
from extractors.pdf_extractor import PdfExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.pptx_extractor import PptxExtractor
from extractors.text_cleaner import clean_text
from rag.chunker import chunker
from embeddings.gemini_embedder import embedder
from vectorstore.qdrant_store import qdrant_store
from core.cache import semantic_cache
from core.logger import logger

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
worker_logger = logging.getLogger("document_worker")

QUEUE_NAME = "lms_document_ingestion_queue"
DLQ_NAME = "lms_document_ingestion_dlq"
DLX_NAME = "lms_dlx"
DLQ_ROUTING_KEY = "ingestion_failed"

def get_rabbitmq_connection():
    """Builds resilient RabbitMQ connection using environment configuration."""
    if pika is None:
        raise RuntimeError("pika library is not installed in the Python environment.")

    host = getattr(settings, "RABBITMQ_HOST", "127.0.0.1")
    port = int(getattr(settings, "RABBITMQ_PORT", 5672))
    user = getattr(settings, "RABBITMQ_USER", "lms_admin")
    password = getattr(settings, "RABBITMQ_PASSWORD", "lms_secure_queue_pass_2026")

    credentials = pika.PlainCredentials(user, password)
    parameters = pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        heartbeat=60,
        blocked_connection_timeout=300
    )
    return pika.BlockingConnection(parameters)

def process_document_job(ch, method, properties, body):
    """Processes a single document ingestion message from RabbitMQ."""
    data = {}
    try:
        data = json.loads(body.decode("utf-8"))
        doc_id = data["document_id"]
        course_id = data["course_id"]
        file_path = data["file_path"]
        title = data.get("title", "Course Document")
        visibility = data.get("visibility", "student")

        worker_logger.info(f"[*] Worker processing Document #{doc_id} ('{title}') for Course #{course_id}...")
        path = Path(file_path).resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Source file not found on disk: {file_path}")

        # Invalidate course cache
        semantic_cache.invalidate_course_cache(course_id)

        # 1. Multi-format text extraction
        ext = path.suffix.lower().replace(".", "")
        pages = []
        if ext == "pdf":
            pages = PdfExtractor.extract(str(path))
        elif ext in ["docx", "doc"]:
            pages = DocxExtractor.extract(str(path))
        elif ext in ["pptx", "ppt"]:
            pages = PptxExtractor.extract(str(path))
        elif ext in ["txt", "md", "sql", "cs", "py", "json"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = clean_text(f.read())
            pages = [{"page_number": 1, "section_title": title or path.stem, "text": content}]
        else:
            raise ValueError(f"Unsupported document format: {ext}")

        if not pages:
            raise ValueError(f"Extracted 0 readable pages from {path.name}")

        # 2. Semantic Chunking
        chunks = chunker.chunk_document_pages(
            pages=pages,
            document_id=doc_id,
            course_id=course_id,
            module_id=data.get("module_id"),
            lesson_id=data.get("lesson_id"),
            visibility=visibility
        )

        if not chunks:
            raise ValueError(f"Document #{doc_id} produced 0 meaningful chunks.")

        # 3. Dense Embeddings
        texts = [c["text"] for c in chunks]
        vectors = embedder.embed_documents(texts)

        # 4. Upsert into Qdrant & BM25
        upserted = qdrant_store.upsert_chunks(chunks, vectors)
        worker_logger.info(f"[+] Document #{doc_id} indexed successfully: {len(pages)} pages, {upserted} chunks landed in Qdrant.")

        # Acknowledge message upon success
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as ex:
        doc_id = data.get("document_id", "unknown")
        worker_logger.error(f"[!] Ingestion failed for Document #{doc_id}: {ex}. Routing to Dead-Letter Queue ({DLQ_NAME}).")
        # Reject and route to Dead-Letter Exchange (requeue=False)
        try:
            ch.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as ack_err:
            worker_logger.error(f"Failed to reject message: {ack_err}")

def start_worker():
    """Initializes RabbitMQ topology (Queues, DLX, DLQ) and enters consumer loop."""
    worker_logger.info("[*] Connecting to RabbitMQ message broker...")
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()

        # 1. Declare Dead-Letter Exchange & Queue
        channel.exchange_declare(exchange=DLX_NAME, exchange_type="direct", durable=True)
        channel.queue_declare(queue=DLQ_NAME, durable=True)
        channel.queue_bind(exchange=DLX_NAME, queue=DLQ_NAME, routing_key=DLQ_ROUTING_KEY)

        # 2. Declare Main Ingestion Queue with DLX configuration
        queue_args = {
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": DLQ_ROUTING_KEY
        }
        channel.queue_declare(queue=QUEUE_NAME, durable=True, arguments=queue_args)
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(queue=QUEUE_NAME, on_message_callback=process_document_job)

        worker_logger.info(f"[*] Document Ingestion Worker listening on queue '{QUEUE_NAME}'. Ready for jobs.")
        channel.start_consuming()

    except KeyboardInterrupt:
        worker_logger.info("[*] Worker stopped by user.")
    except Exception as ex:
        worker_logger.error(f"[!] Worker fatal error: {ex}")

if __name__ == "__main__":
    start_worker()
