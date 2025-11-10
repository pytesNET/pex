import os
import subprocess
from pathlib import Path

SERVICE_NAME = "PrinterService"

ROOT_PATH = Path(__file__).resolve().parents[3]
VENV_PATH = ROOT_PATH / ".venv"
PYTHON_PATH = VENV_PATH / "bin" / "python"
SERVER_PATH = Path(__file__).resolve() / "server.py"
TEMP_PATH = ROOT_PATH / "temp"
TEMP_ERR_FILE = TEMP_PATH / "error.log"
TEMP_OUT_FILE = TEMP_PATH / "out.log"
TOOLS_PATH = ROOT_PATH / "tools"
NSSM_PATH = TOOLS_PATH / "nssm.exe"


def run_nssm_command(command):
    if not os.path.exists(NSSM_PATH):
        return False, f"nssm.exe not found: {NSSM_PATH}"

    try:
        result = subprocess.run(
            [NSSM_PATH, command, SERVICE_NAME],
            capture_output=True, text=True, shell=True, encoding=os.device_encoding(1)
        )
        if result.returncode == 0:
            return True, result.stdout.replace('\x00', '').strip()
        else:
            return False, result.stderr.replace('\x00', '').strip()
    except Exception as e:
        return False, str(e)


def start():
    return run_nssm_command("start")


def stop():
    return run_nssm_command("stop")


def restart():
    return run_nssm_command("restart")


def status():
    return run_nssm_command("status")


def is_installed():
    result = run_nssm_command("status")
    return result[0]


def is_running():
    result = run_nssm_command("status")
    if result[0]:
        return 'SERVICE_RUNNING' in result[1]
    else:
        return False


def install():
    if not os.path.exists(PYTHON_PATH):
        return False, f"Python nicht gefunden: {PYTHON_PATH}"
    if not os.path.exists(SERVER_PATH):
        return False, f"server.py nicht gefunden: {SERVER_PATH}"
    if not os.path.exists(NSSM_PATH):
        return False, f"nssm.exe nicht gefunden: {NSSM_PATH}"

    cmd = [NSSM_PATH, "install", SERVICE_NAME, PYTHON_PATH, SERVER_PATH]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            subprocess.run([NSSM_PATH, "set", SERVICE_NAME, "Description", "Printer Service"], timeout=10)
            subprocess.run([NSSM_PATH, "set", SERVICE_NAME, "AppStderr", TEMP_ERR_FILE], timeout=10)
            subprocess.run([NSSM_PATH, "set", SERVICE_NAME, "AppStdout", TEMP_SCC_FILE], timeout=10)
            return True, f"Service {SERVICE_NAME} installiert!"
        else:
            return False, result.stdout + "\n" + result.stderr
    except Exception as exc:
        return False, str(exc)


def uninstall():
    if not os.path.exists(NSSM_PATH):
        return False, f"nssm.exe nicht gefunden: {NSSM_PATH}"

    cmd = [NSSM_PATH, "remove", SERVICE_NAME, "confirm"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return True, f"Service {SERVICE_NAME} wurde entfernt!"
        else:
            return False, result.stdout + "\n" + result.stderr
    except Exception as exc:
        return False, str(exc)
