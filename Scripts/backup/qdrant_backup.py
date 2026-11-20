#!/usr/bin/env python3
"""
Production Hardened Qdrant Vector Database Snapshot & Restoration Utility.
Features atomic temporary downloads, tarball integrity validation,
and graceful HTTP exception handling.
"""
import os
import sys
import tarfile
import logging
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.error
import json

logging.basicConfig(level=logging.INFO, format="[%(asctime)s UTC] %(levelname)s: %(message)s")
logger = logging.getLogger("qdrant_backup")

QDRANT_HOST = os.getenv("QDRANT_HOST", "http://127.0.0.1:6333").rstrip("/")
COLLECTION = os.getenv("QDRANT_COLLECTION", "lms_course_knowledge")
BACKUP_DIR = Path(os.getenv("QDRANT_BACKUP_DIR", "C:/LMS_Backups/Qdrant"))
RETENTION_DAYS = 7

BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def create_snapshot():
    logger.info(f"Triggering snapshot creation for collection '{COLLECTION}' at {QDRANT_HOST}...")
    snap_url = f"{QDRANT_HOST}/collections/{COLLECTION}/snapshots"

    try:
        req = urllib.request.Request(snap_url, data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        if ex.code == 404:
            logger.error(f"Collection '{COLLECTION}' does not exist in Qdrant cluster. Backup aborted.")
            sys.exit(1)
        logger.error(f"HTTP error creating snapshot: {ex}")
        sys.exit(1)
    except Exception as ex:
        logger.error(f"Failed to communicate with Qdrant service: {ex}")
        sys.exit(1)

    snap_data = data.get("result", {})
    snap_name = snap_data.get("name")
    if not snap_name:
        logger.error(f"Snapshot API returned invalid response: {data}")
        sys.exit(1)

    logger.info(f"Snapshot '{snap_name}' generated on cluster. Initiating streaming download...")
    download_url = f"{snap_url}/{snap_name}"
    final_file = BACKUP_DIR / snap_name
    temp_file = BACKUP_DIR / f"{snap_name}.tmp"

    try:
        with urllib.request.urlopen(download_url, timeout=300) as response, open(temp_file, "wb") as out_file:
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                out_file.write(chunk)

        # Validate tarball integrity before promoting from .tmp
        if not tarfile.is_tarfile(temp_file) or temp_file.stat().st_size == 0:
            raise ValueError("Downloaded snapshot file is not a valid tar archive or is empty.")

        # Atomic promotion to final target path
        if final_file.exists():
            final_file.unlink()
        temp_file.replace(final_file)
        size_mb = round(final_file.stat().st_size / (1024 * 1024), 2)
        logger.info(f"Snapshot successfully verified and archived: {final_file} ({size_mb} MB)")

    except Exception as ex:
        logger.error(f"Failed to download or verify snapshot archive: {ex}")
        if temp_file.exists():
            temp_file.unlink(missing_ok=True)
        sys.exit(1)

    # Prune expired snapshots
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    for p in BACKUP_DIR.glob(f"{COLLECTION}-*.snapshot"):
        if datetime.utcfromtimestamp(p.stat().st_mtime) < cutoff:
            logger.info(f"Pruning expired vector snapshot: {p.name}")
            p.unlink(missing_ok=True)

def restore_snapshot(snapshot_path: str):
    snap_path = Path(snapshot_path)
    if not snap_path.is_file() or not tarfile.is_tarfile(snap_path):
        logger.error(f"Specified restore path '{snapshot_path}' is not a valid tar snapshot archive.")
        sys.exit(1)

    logger.info(f"Restoring collection '{COLLECTION}' from {snap_path}...")
    restore_url = f"{QDRANT_HOST}/collections/{COLLECTION}/snapshots/upload"

    try:
        # Upload snapshot binary to restore endpoint
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        with open(snap_path, "rb") as f:
            file_data = f.read()

        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="snapshot"; filename="{snap_path.name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")

        req = urllib.request.Request(
            restore_url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        logger.info(f"Qdrant collection restored successfully: {result}")
    except Exception as ex:
        logger.error(f"Failed to restore Qdrant snapshot: {ex}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--restore":
        if len(sys.argv) < 3:
            logger.error("Usage: python qdrant_backup.py --restore <path_to_snapshot>")
            sys.exit(1)
        restore_snapshot(sys.argv[2])
    else:
        create_snapshot()
