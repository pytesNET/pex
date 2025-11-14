import os
import subprocess
from pathlib import Path
from ..version import __SERVICE_NAME__

ROOT_PATH = Path(__file__).resolve().parents[3]
VENV_PATH = ROOT_PATH / ".venv"
PEX_PATH = VENV_PATH / "Scripts" / "pex.exe"
TEMP_PATH = ROOT_PATH / "temp"
TEMP_ERR_FILE = TEMP_PATH / "error.log"
TEMP_OUT_FILE = TEMP_PATH / "out.log"
TOOLS_PATH = ROOT_PATH / "tools"
NSSM_PATH = TOOLS_PATH / "nssm.exe"


def _run_nssm_command(command):
    if not os.path.exists(NSSM_PATH):
        return False, f"nssm.exe not found: {NSSM_PATH}"

    try:
        result = subprocess.run(
            [NSSM_PATH, command, __SERVICE_NAME__],
            capture_output=True, text=True, shell=True, encoding=os.device_encoding(1)
        )
        if result.returncode == 0:
            return True, result.stdout.replace('\x00', '').strip()
        else:
            return False, result.stderr.replace('\x00', '').strip()
    except Exception as e:
        return False, str(e)


def start():
    return _run_nssm_command("start")


def stop():
    return _run_nssm_command("stop")


def restart():
    return _run_nssm_command("restart")


def status():
    return _run_nssm_command("status")


def is_installed():
    result = _run_nssm_command("status")
    return result[0]


def is_running():
    result = _run_nssm_command("status")
    if result[0]:
        return 'SERVICE_RUNNING' in result[1]
    else:
        return False


def install():
    if not NSSM_PATH.exists():
        return False, f"nssm.exe not found: {NSSM_PATH}"

    os.makedirs(TEMP_PATH, exist_ok=True)
    try:
        result = subprocess.run(
            [str(NSSM_PATH), "install", __SERVICE_NAME__, str(PEX_PATH), "run",],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            return False, (result.stdout + "\n" + result.stderr).strip()

        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "AppDirectory", str(ROOT_PATH)], timeout=10)
        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "AppStdout", str(TEMP_OUT_FILE)], timeout=10)
        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "AppStderr", str(TEMP_ERR_FILE)], timeout=10)
        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "AppStopMethodConsole", "1500"], timeout=10)
        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "AppKillProcessTree", "1"], timeout=10)
        subprocess.run([str(NSSM_PATH), "set", __SERVICE_NAME__, "Start", "SERVICE_AUTO_START"], timeout=10)

        return True, f"Service {__SERVICE_NAME__} successfully installed: {str(PEX_PATH)} run"
    except Exception as exc:
        return False, str(exc)


def uninstall():
    if not os.path.exists(NSSM_PATH):
        return False, f"nssm.exe not found: {NSSM_PATH}"

    try:
        subprocess.run([str(NSSM_PATH), "stop", __SERVICE_NAME__], timeout=15)

        result = subprocess.run(
            [str(NSSM_PATH), "remove", __SERVICE_NAME__, "confirm"],
            capture_output=True, text=True, timeout=30
        )
        out = (result.stdout + result.stderr).strip()

        if result.returncode == 0:
            return True, f"Service {__SERVICE_NAME__} successfully removed"
        elif "The service is not installed" in out:
            return True, f"Service {__SERVICE_NAME__} was not installed"
        else:
            return False, f"Service {__SERVICE_NAME__} could not be removed"
    except subprocess.TimeoutExpired:
        return False, f"Uninstall timed out while removing {__SERVICE_NAME__}"
    except Exception as exc:
        return False, f"{exc}"
