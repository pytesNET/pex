import json
import locale
import os
import subprocess
import sys
from typing import Tuple

SERVICE_NAME = "PrinterService"

LINUX = sys.platform.startswith("linux")
ROOT_PATH = os.path.dirname(os.path.abspath(__file__))
SERVER_PATH = os.path.join(ROOT_PATH, "server.py")
TEMP_PATH = os.path.join(ROOT_PATH, "temp")
TEMP_ERR_FILE = os.path.join(TEMP_PATH, "error.log")
TEMP_SCC_FILE = os.path.join(TEMP_PATH, "out.log")

VENV_PATH = os.path.join(ROOT_PATH, ".venv")
PYTHON_PATH = os.path.join(VENV_PATH, "bin", "python")
PM2_CMD = os.environ.get("PM2_PATH", "pm2")

ENCODING = locale.getpreferredencoding(False) or "utf-8"


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
        return False, f"pm2 nicht gefunden oder nicht ausführbar (PM2_PATH='{PM2_CMD}'). Details:\n{out}"
    return True, out


def _jlist() -> Tuple[bool, list]:
    ok, out = _run([PM2_CMD, "jlist"])
    if not ok:
        return False, [out]
    try:
        data = json.loads(out or "[]")
        return True, data
    except Exception as exc:
        return False, [f"Fehler beim Parsen von pm2 jlist: {exc}\nRaw: {out}"]


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
    return _run([PM2_CMD, "start", SERVICE_NAME])


def stop():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    return _run([PM2_CMD, "stop", SERVICE_NAME])


def restart():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    return _run([PM2_CMD, "restart", SERVICE_NAME])


def status():
    ok, _ = _ensure_pm2()
    if not ok:
        return _
    proc = _find_proc_by_name(SERVICE_NAME)
    if not proc:
        return False, f"Service {SERVICE_NAME} ist nicht installiert."
    status = proc.get("pm2_env", {}).get("status")
    pid = proc.get("pid")
    return True, f"{SERVICE_NAME}: {status} (pid={pid})"


def is_installed():
    ok, _ = _ensure_pm2()
    if not ok:
        return False
    return _find_proc_by_name(SERVICE_NAME) is not None


def is_running():
    ok, _ = _ensure_pm2()
    if not ok:
        return False
    proc = _find_proc_by_name(SERVICE_NAME)
    if not proc:
        return False
    status = proc.get("pm2_env", {}).get("status")
    # pm2 Statuswerte: "online", "stopped", "errored", ...
    return status == "online"


def install():
    ok, info = _ensure_pm2()
    if not ok:
        return False, info

    if not os.path.exists(PYTHON_PATH):
        return False, f"Python nicht gefunden: {PYTHON_PATH}"
    if not os.path.exists(SERVER_PATH):
        return False, f"server.py nicht gefunden: {SERVER_PATH}"

    os.makedirs(TEMP_PATH, exist_ok=True)

    cmd = [
        PM2_CMD,
        "start",
        SERVER_PATH,
        "--interpreter",
        PYTHON_PATH,
        "--name",
        SERVICE_NAME,
        "--output",
        TEMP_SCC_FILE,
        "--error",
        TEMP_ERR_FILE,
    ]

    ok, out = _run(cmd)
    if not ok:
        return False, out

    _run([PM2_CMD, "save"])
    return True, f"Service {SERVICE_NAME} installiert (pm2)."


def uninstall():
    ok, info = _ensure_pm2()
    if not ok:
        return False, info

    ok, out = _run([PM2_CMD, "delete", SERVICE_NAME])
    if not ok:
        return False, out

    _run([PM2_CMD, "save"])
    return True, f"Service {SERVICE_NAME} wurde entfernt."
