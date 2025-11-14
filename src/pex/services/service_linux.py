import json
import locale
import os
import subprocess
from pathlib import Path
from typing import Tuple
from ..version import __SERVICE_NAME__

ENCODING = locale.getpreferredencoding(False) or "utf-8"
PM2_CMD = os.environ.get("PM2_PATH", "pm2")

ROOT_PATH = Path(__file__).resolve().parents[3]
VENV_PATH = ROOT_PATH / ".venv"
PYTHON_PATH = VENV_PATH / "bin" / "python"
PEX_PATH = VENV_PATH / "bin" / "pex"
TEMP_PATH = ROOT_PATH / "temp"
TEMP_ERR_FILE = TEMP_PATH / "error.log"
TEMP_OUT_FILE = TEMP_PATH / "out.log"


def _run(cmd: list[str], timeout: int = 30) -> Tuple[bool, str]:
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding=ENCODING,
        )
        out = (res.stdout or "").strip()
        err = (res.stderr or "").strip()
        if res.returncode == 0:
            return True, out
        return False, (out + ("\n" + err if err else "")).strip()
    except Exception as exc:
        return False, str(exc)


def _ensure_pm2() -> Tuple[bool, str]:
    ok, out = _run([PM2_CMD, "-v"])
    if not ok:
        return False, f"pm2 could not be found (PM2_PATH='{PM2_CMD}'). Details:\n{out}"
    return True, out


def _jlist() -> Tuple[bool, list]:
    ok, out = _run([PM2_CMD, "jlist"])
    if not ok:
        return False, [out]
    try:
        data = json.loads(out or "[]")
        return True, data
    except Exception as exc:
        return False, [f"Error during parsing of pm2 jlist : {exc}\nRaw: {out}"]


def _find_proc_by_name(name: str):
    ok, data = _jlist()
    if not ok:
        return None
    for proc in data:
        if (
            proc.get("name") == name
            or proc.get("pm2_env", {}).get("name") == name
        ):
            return proc
    return None


def start():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    return _run([PM2_CMD, "start", __SERVICE_NAME__])


def stop():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    return _run([PM2_CMD, "stop", __SERVICE_NAME__])


def restart():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    return _run([PM2_CMD, "restart", __SERVICE_NAME__])


def status():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    proc = _find_proc_by_name(__SERVICE_NAME__)
    if not proc:
        return False, f"Service {__SERVICE_NAME__} could not be installed."
    status = proc.get("pm2_env", {}).get("status")
    pid = proc.get("pid")
    return True, f"{__SERVICE_NAME__}: {status} (pid={pid})"


def is_installed():
    ok, _ = _ensure_pm2()
    if not ok:
        return False
    return _find_proc_by_name(__SERVICE_NAME__) is not None


def is_running():
    ok, _ = _ensure_pm2()
    if not ok:
        return False
    proc = _find_proc_by_name(__SERVICE_NAME__)
    if not proc:
        return False
    status = proc.get("pm2_env", {}).get("status")
    return status == "online"


def install():
    ok, info = _ensure_pm2()
    if not ok:
        return False, info

    os.makedirs(TEMP_PATH, exist_ok=True)

    cmd = [
        PM2_CMD, "start", PEX_PATH,
        "--name", __SERVICE_NAME__,
        "--interpreter", PYTHON_PATH,
        "--output", TEMP_OUT_FILE,
        "--error", TEMP_ERR_FILE,
        "--", "run"
    ]

    ok, out = _run(cmd)
    if not ok:
        return False, out

    _run([PM2_CMD, "save"])
    return True, f"Service {__SERVICE_NAME__} successfully installed (pm2)."


def uninstall():
    ok, info = _ensure_pm2()
    if not ok:
        return False, info

    ok, out = _run([PM2_CMD, "delete", __SERVICE_NAME__])
    if not ok:
        return False, out

    _run([PM2_CMD, "save"])
    return True, f"Service {__SERVICE_NAME__} successfully removed."
