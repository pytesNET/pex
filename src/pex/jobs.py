"""Bounded FIFO queues per printer, with durable metadata and deduplication.

Payloads stay in private temporary files. A process restart never reprints a job:
unfinished records become unknown and require an operator's decision.
"""
from __future__ import annotations

import hashlib
import json
import logging
import queue
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .services import printer

logger = logging.getLogger(__name__)
TERMINAL = {"submitted", "failed", "unknown"}


class QueueFullError(Exception):
    pass


class ConflictError(Exception):
    pass


class JobManager:
    def __init__(self, database: Path, limit: int = 100, retention_hours: int = 24) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(database, check_same_thread=False, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.limit = limit
        self.retention = retention_hours * 3600
        self.pending = 0
        self.accepting = True
        self.queues: dict[str, queue.Queue] = {}
        self.threads: list[threading.Thread] = []
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, request_key TEXT UNIQUE, fingerprint TEXT NOT NULL,
            printer TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL,
            updated REAL NOT NULL, result TEXT, error_code TEXT)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS jobs_updated ON jobs(updated)")
        self.db.execute("UPDATE jobs SET state='unknown', error_code='service_restarted', updated=? WHERE state IN ('queued','processing')", (time.time(),))
        self.db.commit()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return None
            return {"id": row["id"], "printer": row["printer"], "state": row["state"],
                    "created_at": row["created"], "updated_at": row["updated"],
                    "result": json.loads(row["result"]) if row["result"] else None,
                    "error_code": row["error_code"]}

    def submit(self, filepath: str, arguments: dict[str, Any], fingerprint: str,
               request_key: str | None = None) -> tuple[dict, bool]:
        """Take ownership of filepath on acceptance only; replays own no new file."""
        with self.lock:
            now = time.time()
            self.db.execute("DELETE FROM jobs WHERE updated < ? AND state IN ('submitted','failed','unknown')", (now - self.retention,))
            self.db.commit()
            key = hashlib.sha256(request_key.encode()).hexdigest() if request_key else None
            if key:
                previous = self.db.execute("SELECT id, fingerprint FROM jobs WHERE request_key=?", (key,)).fetchone()
                if previous:
                    if previous["fingerprint"] != fingerprint:
                        raise ConflictError("The idempotency key was already used for a different print job.")
                    return self.get(previous["id"]), True
            if not self.accepting or self.pending >= self.limit:
                raise QueueFullError("The print queue is full or shutting down.")
            # Bound disk usage as well as active work; never silently evict deduplication records.
            count = self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            if count >= 100000:
                raise QueueFullError("The retained job history is full.")
            job_id = uuid.uuid4().hex
            name = arguments["printer_name"]
            self.db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?)",
                            (job_id, key, fingerprint, name, "queued", now, now, None, None))
            self.db.commit()
            self.pending += 1
            if name not in self.queues:
                work = self.queues[name] = queue.Queue()
                thread = threading.Thread(target=self._worker, args=(work,), name=f"pex-printer-{len(self.threads)}", daemon=True)
                self.threads.append(thread)
                thread.start()
            self.queues[name].put((job_id, filepath, dict(arguments)))
            logger.info("job=%s state=queued", job_id)
            return self.get(job_id), False

    def _update(self, job_id: str, state: str, result: dict | None = None,
                error_code: str | None = None) -> None:
        with self.condition:
            self.db.execute("UPDATE jobs SET state=?, updated=?, result=?, error_code=? WHERE id=?",
                            (state, time.time(), json.dumps(result) if result else None, error_code, job_id))
            self.db.commit()
            self.condition.notify_all()
        logger.info("job=%s state=%s error_code=%s", job_id, state, error_code)

    def _worker(self, work: queue.Queue) -> None:
        while True:
            item = work.get()
            if item is None:
                work.task_done()
                return
            job_id, filepath, arguments = item
            try:
                self._update(job_id, "processing")
                result = printer.print_file(filepath=filepath, **arguments)
                self._update(job_id, "submitted", result)
            except (ValueError, FileNotFoundError) as error:
                logger.error("job=%s setup_exception=%s", job_id, type(error).__name__)
                self._update(job_id, "failed", {"message": "Check the printer, PDF, and installed paper forms."}, "print_setup_invalid")
            except Exception as error:
                # Partial submission and timeouts must never invite automatic retry.
                logger.error("job=%s backend_exception=%s", job_id, type(error).__name__)
                self._update(job_id, "unknown", error_code="submission_uncertain")
            finally:
                printer._safe_remove(filepath)
                with self.condition:
                    self.pending -= 1
                    self.condition.notify_all()
                work.task_done()

    def wait(self, job_id: str, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                job = self.get(job_id)
                if job is None:
                    raise KeyError(job_id)
                if job["state"] in TERMINAL or time.monotonic() >= deadline:
                    return job
                self.condition.wait(max(0, deadline - time.monotonic()))

    def close(self, timeout: float = 5.0) -> None:
        with self.lock:
            if not self.accepting:
                return
            self.accepting = False
            for work in self.queues.values():
                work.put(None)
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
        # Active daemon workers may still need the connection during shutdown.
        if not any(thread.is_alive() for thread in self.threads):
            self.db.close()
