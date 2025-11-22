import subprocess
import sys
from .services import service


def _run_command(cmd: list[str], log, timeout: int = 120, fail_message: str | None = None) -> bool:
    log(f"[INFO] Running: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        log(f"[ERROR] Command timed out: {' '.join(cmd)}")
        return False
    except Exception as e:
        log(f"[EXCEPTION] Command failed to start: {e}")
        return False

    if res.stdout:
        log(res.stdout.strip())
    if res.stderr:
        log(res.stderr.strip())

    if res.returncode != 0:
        if fail_message:
            log(f"[ERROR] {fail_message} (exit code {res.returncode})")
        else:
            log(f"[ERROR] Command failed with exit code {res.returncode}")
        return False
    return True


def perform(log) -> bool:
    success = True

    try:
        # Check Service Status
        try:
            installed = service.is_installed()
            running = service.is_running() if installed else False
        except Exception as e:
            installed, running = False, False
            log(f"[ERROR] Could not read service status: {e}")

        # Stop service
        if installed and running:
            log("[INFO] Stopping service...")
            status, msg = service.stop()
            if status:
                log("[SUCCESS] Service successfully stopped")
            else:
                log(f"[ERROR] {msg}")
                success = False

        # Pull repository
        if success:
            log("[INFO] Pulling latest changes from git...")
            ok = _run_command(
                ["git", "pull"],
                log,
                timeout=120,
                fail_message="git pull failed"
            )
            if not ok:
                success = False

        # Update requirements
        if success:
            log("[INFO] Installing/updating requirements...")
            ok = _run_command(
                [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                log,
                timeout=600,
                fail_message="pip install -r requirements.txt failed"
            )
            if not ok:
                success = False

        # Re-Install PEX package
        if success:
            log("[INFO] Installing package in editable mode...")
            ok = _run_command(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                log,
                timeout=600,
                fail_message="pip install -e . failed"
            )
            if not ok:
                success = False

        # Start service
        if installed and running and success:
            log("[INFO] Starting service...")
            status, msg = service.start()
            if status:
                log("[SUCCESS] Service successfully started")
            else:
                log(f"[ERROR] {msg}")
                success = False

    except subprocess.CalledProcessError as e:
        log(f"[EXCEPTION] {getattr(e, 'output', str(e)).strip()}")
        success = False
    except Exception as e:
        log(f"[EXCEPTION] {e}")
        success = False

    return success
