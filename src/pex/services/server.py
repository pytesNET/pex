"""Authenticated HTTP bridge for direct local or LAN printing."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import threading
import time

from flask import Flask, jsonify, request
from waitress import serve
from werkzeug.exceptions import HTTPException

from . import printer
from .. import config
from ..jobs import ConflictError, JobManager, QueueFullError
from ..locking import FileLock
from ..version import __NAME__, __VERSION__

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
_manager_lock = threading.Lock()


def response_success(data: dict, code: int = 200):
    return jsonify({"status": "success", "result": data}), code


def response_error(message: str, details: dict | None = None, code: int = 400,
                   error_code: str = "invalid_request"):
    return jsonify({"status": "error", "message": message, "code": error_code, "details": details or {}}), code


def _origin_allowed(origin: str | None) -> bool:
    if origin is None:
        return True  # Native clients must still authenticate.
    allowed = config.get_option("server.cors", False)
    if origin == "null":
        return False
    return allowed is True or origin in ([allowed] if isinstance(allowed, str) else allowed if isinstance(allowed, list) else [])


@app.before_request
def authorize():
    request.max_content_length = config.get_option("server.max_upload_mb", 10) * 1024 * 1024
    if request.content_length is not None and request.content_length > request.max_content_length:
        return response_error("The upload exceeds the configured size limit.", code=413, error_code="upload_too_large")
    if not _origin_allowed(request.headers.get("Origin")):
        return response_error("This web application is not allowed.", code=403, error_code="origin_denied")
    if request.method == "OPTIONS":
        return None
    token = os.environ.get("PEX_API_TOKEN") or config.get_option("server.token", "")
    if config.get_option("server.require_auth", True):
        if not token:
            return response_error("API authentication is not configured.", code=503, error_code="auth_not_configured")
        supplied = request.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return response_error("Authentication is required.", code=401, error_code="unauthorized")


@app.after_request
def apply_cors_headers(response):
    origin = request.headers.get("Origin")
    if origin and _origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, Idempotency-Key, Prefer"
        response.headers["Access-Control-Expose-Headers"] = "Location, Preference-Applied, Retry-After"
        if request.headers.get("Access-Control-Request-Private-Network") == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        response.vary.add("Origin")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.errorhandler(HTTPException)
def http_error(error: HTTPException):
    code = error.code or 500
    return response_error(error.description or "An HTTP error occurred.", code=code, error_code=f"http_{code}")


@app.errorhandler(Exception)
def internal_error(error: Exception):
    app.logger.error("request_failed exception=%s", type(error).__name__)
    return response_error("The printer service could not process the request.", code=500, error_code="internal_error")


def _manager() -> JobManager:
    with _manager_lock:
        if "pex_jobs" not in app.extensions:
            app.extensions["pex_jobs"] = JobManager(config.ROOT_PATH / "jobs.sqlite3",
                config.get_option("server.max_jobs", 100), config.get_option("server.job_retention_hours", 24))
        return app.extensions["pex_jobs"]


@app.get("/pex/status")
def _get_status():
    return response_success({"name": __NAME__, "version": __VERSION__,
        "config": {key: config.get_option(key) for key in ("formats", "printers", "printer_default")},
        "printers": printer.list_printers()})


@app.get("/pex/printers")
def _get_printers():
    default = config.get_option("printer_default")
    return response_success({"printers": printer.list_printers(),
                             "printer_default": printer.resolve_printer_name(default) if default else None})


@app.get("/pex/jobs/<job_id>")
def _get_job(job_id: str):
    job = _manager().get(job_id)
    if job is None:
        return response_error("The print job was not found.", code=404, error_code="job_not_found")
    return response_success({"job": job})


def _format() -> str | list[float]:
    preferred, legacy = request.form.getlist("paper_format"), request.form.getlist("format")
    def parse(values: list[str]):
        if not values:
            return "A4"
        if len(values) == 1:
            try:
                value = json.loads(values[0])
            except (ValueError, TypeError):
                return values[0]
            return value if isinstance(value, (str, list)) else values[0]
        if len(values) == 2:
            return [float(value) for value in values]
        raise ValueError("Provide a paper name or exactly two dimensions.")
    value = parse(preferred or legacy)
    if preferred and legacy and parse(preferred) != parse(legacy):
        raise ValueError("paper_format and format must not conflict.")
    if isinstance(value, list) and len(value) != 2:
        raise ValueError("Provide exactly two paper dimensions.")
    return value


def _lines() -> list[dict]:
    result = []
    for entry in request.form.getlist("lines"):
        try:
            parsed = json.loads(entry)
        except ValueError:
            parsed = entry
        entries = parsed if isinstance(parsed, list) else [parsed]
        for line in entries:
            if isinstance(line, str):
                result.append({"text": line})
            elif isinstance(line, dict):
                result.append(line)
            else:
                raise ValueError("Each label line must be text or an object.")
    return result


@app.post("/pex/print")
def _post_print():
    temporary: str | None = None
    try:
        has_file, has_lines = "file" in request.files, "lines" in request.form
        if has_file == has_lines:
            raise ValueError("Provide either one PDF file or text lines, exclusively.")
        if has_file and len(request.files.getlist("file")) != 1:
            raise ValueError("Provide exactly one PDF file.")
        orientation = request.form.get("orientation", "portrait")
        quantity = int(request.form.get("quantity", "1"))
        paper = _format()
        name, dimensions, orientation = printer.validate_options(
            request.form.get("printer") or config.get_option("printer_default"), paper, orientation, quantity)
        arguments = {"printer_name": name, "paper_format": list(dimensions), "orientation": orientation, "quantity": quantity}
        key = request.headers.get("Idempotency-Key")
        if key is not None and (not 1 <= len(key) <= 128 or not key.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            raise ValueError("Idempotency-Key must contain 1 to 128 printable ASCII characters without spaces.")
        directory = config.ROOT_PATH / "temp"
        directory.mkdir(parents=True, exist_ok=True)
        fd, filepath = tempfile.mkstemp(prefix="pex-job-", suffix=".pdf", dir=directory)
        temporary = filepath
        with os.fdopen(fd, "wb") as stream:
            if has_file:
                content = request.files["file"].read()
                if b"%PDF-" not in content[:1024]:
                    raise ValueError("Only PDF files are supported.")
                source_hash = hashlib.sha256(content).hexdigest()
            else:
                lines = _lines()
                font = request.form.get("font_name") or "helvetica"
                size = float(request.form.get("font_size", "10"))
                height = float(request.form.get("line_height", "12"))
                source_hash = hashlib.sha256(json.dumps([lines, font, size, height], sort_keys=True, allow_nan=False).encode()).hexdigest()
                content = printer.render_lines(lines, paper, orientation, font, size, height)
            stream.write(content)
        fingerprint = hashlib.sha256(json.dumps([arguments, source_hash], sort_keys=True).encode()).hexdigest()
        manager = _manager()
        job, replayed = manager.submit(filepath, arguments, fingerprint, key)
        if not replayed:
            temporary = None  # Ownership has transferred to the worker.
        asynchronous = "respond-async" in request.headers.get("Prefer", "").lower()
        if not asynchronous:
            job = manager.wait(job["id"], config.get_option("server.timeout", 30))
        if job["state"] in ("failed", "unknown"):
            return response_error("Print submission could not be confirmed. Check the printer before retrying.",
                                  {"job": job}, 502, job["error_code"] or "print_failed")
        code = 200 if job["state"] == "submitted" else 202
        response, status = response_success({"message": "Print job submitted to the spooler." if code == 200 else "Print job accepted.",
            "arguments": arguments, "job": job, "replayed": replayed}, code)
        response.headers["Location"] = f"/pex/jobs/{job['id']}"
        if asynchronous:
            response.headers["Preference-Applied"] = "respond-async"
        return response, status
    except QueueFullError as error:
        response, status = response_error(str(error), code=503, error_code="queue_full")
        response.headers["Retry-After"] = "5"
        return response, status
    except ConflictError as error:
        return response_error(str(error), code=409, error_code="idempotency_conflict")
    except (ValueError, TypeError, OverflowError) as error:
        return response_error(str(error), error_code="validation_failed")
    finally:
        if temporary:
            printer._safe_remove(temporary)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # Refuse concurrent owners of the same durable job history.
    with FileLock(config.ROOT_PATH / "server.lock", timeout=0):
        if config.get_option("server.require_auth", True) and not (os.environ.get("PEX_API_TOKEN") or config.get_option("server.token", "")):
            config.set_option("server.token", secrets.token_urlsafe(32))
            app.logger.warning("API token generated. Read it locally using: pex config server.token")
        if config.get_option("server.cors", False) is True:
            app.logger.warning("Legacy unrestricted CORS is enabled. Configure an explicit origin allowlist.")
        if not config.get_option("server.require_auth", True):
            app.logger.warning("API authentication is disabled by configuration.")
        manager = _manager()
        try:
            # Only our own stale temporary files, never user PDFs or active jobs.
            cutoff = time.time() - config.get_option("server.job_retention_hours", 24) * 3600
            for path in (config.ROOT_PATH / "temp").glob("pex-job-*.pdf"):
                try:
                    if path.is_file() and not path.is_symlink() and path.stat().st_mtime < cutoff:
                        printer._safe_remove(str(path))
                except OSError:
                    app.logger.warning("Could not inspect a stale temporary print file.")
            serve(app, host=config.get_option("server.host", "127.0.0.1"),
                  port=config.get_option("server.port", 4422), threads=config.get_option("server.threads", 4),
                  backlog=config.get_option("server.backlog", 128),
                  channel_timeout=config.get_option("server.timeout", 30),
                  max_request_body_size=config.get_option("server.max_upload_mb", 10) * 1024 * 1024,
                  ident=f"PEX/{__VERSION__}")
        finally:
            manager.close(timeout=config.get_option("server.process_timeout", 30) + 1)
            app.extensions.pop("pex_jobs", None)


if __name__ == "__main__":
    run()
