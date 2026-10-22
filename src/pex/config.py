"""Validated configuration with atomic, process-safe updates."""
from __future__ import annotations

import json
import math
import os
import tempfile
import threading
from copy import deepcopy
from importlib.resources import files
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .locking import FileLock
from .utils import deep_get, deep_set, deep_delete

PROJECT_PATH = Path(__file__).resolve().parents[2]
_editable = (PROJECT_PATH / "pyproject.toml").is_file()
_user_data = (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "PEX"
              if os.name == "nt" else Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "pex")
ROOT_PATH = Path(os.environ.get("PEX_DATA_DIR", PROJECT_PATH if _editable else _user_data)).resolve()
CONFIG_FILE = ROOT_PATH / "config.json"
LEGACY_CONFIG_FILE = ROOT_PATH / "pexconfig.json"
_lock = threading.RLock()


def _default_config() -> dict[str, Any]:
    source = files("pex").joinpath("defaults.json")
    return json.loads(source.read_text(encoding="utf-8"))


def _merge(defaults: dict, overrides: dict) -> dict:
    result = deepcopy(defaults)
    for key, value in overrides.items():
        result[key] = _merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else value
    return result


def validate(data: dict[str, Any]) -> None:
    """Reject invalid configuration before replacing the previous file."""
    if not isinstance(data, dict):
        raise ValueError("Configuration must be an object.")
    server = data.get("server", {})
    if not isinstance(server, dict):
        raise ValueError("server must be an object.")
    for key, minimum, maximum in (("port", 1, 65535), ("threads", 1, 64), ("backlog", 1, 4096),
                                  ("timeout", 1, 3600), ("max_upload_mb", 1, 100),
                                  ("max_copies", 1, 10000), ("max_jobs", 1, 10000),
                                  ("process_timeout", 1, 600), ("job_retention_hours", 1, 720)):
        value = server.get(key)
        if value is not None and (type(value) is not int or not minimum <= value <= maximum):
            raise ValueError(f"server.{key} must be an integer between {minimum} and {maximum}.")
    if "host" in server and (not isinstance(server["host"], str) or not server["host"].strip()):
        raise ValueError("server.host must be a non-empty string.")
    if not isinstance(server.get("token", ""), str):
        raise ValueError("server.token must be a string.")
    if type(server.get("require_auth", True)) is not bool:
        raise ValueError("server.require_auth must be a boolean.")
    cors = server.get("cors", False)
    if not isinstance(cors, (bool, str, list)):
        raise ValueError("server.cors must be false, true, an origin, or a list of origins.")
    origins = [cors] if isinstance(cors, str) else cors if isinstance(cors, list) else []
    for origin in origins:
        if not isinstance(origin, str):
            raise ValueError("CORS origins must be strings.")
        parsed = urlsplit(origin)
        if parsed.scheme not in ("https", "http") or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("CORS origins must contain only http(s)://host[:port].")
    if data.get("linux_command", "-n") not in ("-n", "-o", "for"):
        raise ValueError("linux_command must be -n, -o, or for.")
    printers = data.get("printers", {})
    if not isinstance(printers, dict) or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip() for k, v in printers.items()):
        raise ValueError("printers must map non-empty aliases to printer names.")
    default = data.get("printer_default")
    if default is not None and not isinstance(default, str):
        raise ValueError("printer_default must be a string or null.")
    formats = data.get("formats", {})
    if not isinstance(formats, dict):
        raise ValueError("formats must be an object.")
    for name, dimensions in formats.items():
        if not isinstance(dimensions, (list, tuple)) or len(dimensions) < 2:
            raise ValueError(f"Invalid paper format: {name}")
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 5 <= v <= 2000 for v in dimensions[:2]):
            raise ValueError(f"Invalid dimensions for paper format: {name}")


def _write(data: dict) -> None:
    validate(data)
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".pex-config-", suffix=".json", dir=CONFIG_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, CONFIG_FILE)
    finally:
        Path(name).unlink(missing_ok=True)


def _load() -> dict:
    defaults = _default_config()
    if CONFIG_FILE.exists():
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    elif LEGACY_CONFIG_FILE.exists():
        legacy = json.loads(LEGACY_CONFIG_FILE.read_text(encoding="utf-8"))
        data = deepcopy(defaults)
        for old, alias in (("file_printer", "file"), ("label_printer", "label")):
            name = legacy.get(old)
            if isinstance(name, str) and name and name != "null":
                data["printers"][alias] = name
        data["printer_default"] = next(iter(data["printers"]), None)
        _write(data)  # Preserve the legacy source as a recovery copy.
    else:
        data = defaults
    validate(data)
    return _merge(defaults, data)


def load_config() -> dict[str, Any]:
    with _lock, FileLock(CONFIG_FILE.with_suffix(".lock")):
        return _load()


def save_config(data: dict[str, Any]) -> None:
    with _lock, FileLock(CONFIG_FILE.with_suffix(".lock")):
        _write(data)


def get_option(name: str, default: Any = "") -> Any:
    return deep_get(load_config(), name, default)


def set_options(options: dict[str, Any]) -> None:
    """Commit related options together under the same cross-process lock."""
    with _lock, FileLock(CONFIG_FILE.with_suffix(".lock")):
        data = _load()
        for key, value in options.items():
            deep_set(data, key, value)
        _write(data)


def set_option(name: str, value: Any) -> None:
    set_options({name: value})


def delete_option(name: str) -> None:
    with _lock, FileLock(CONFIG_FILE.with_suffix(".lock")):
        data = _load()
        deep_delete(data, name)
        _write(data)
