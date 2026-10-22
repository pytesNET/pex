"""Preflighted updates to an explicit upstream commit, with recovery snapshots."""
from __future__ import annotations

import json
import base64
import configparser
import csv
import hashlib
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable

from .config import PROJECT_PATH, ROOT_PATH
from .locking import FileLock
from .services import service


def _environment() -> dict[str, str]:
    # An inherited GIT_DIR/GIT_WORK_TREE must never redirect an update elsewhere.
    return {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}


def _run(cmd: list[str], cwd: Path = PROJECT_PATH, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=_environment(), capture_output=True, text=True, timeout=timeout, check=True)


def _run_command(cmd: list[str], log: Callable[[str], None], timeout: int = 120,
                 fail_message: str | None = None) -> bool:
    try:
        _run(cmd, timeout=timeout)
        return True
    except (OSError, subprocess.SubprocessError) as error:
        log(f"[ERROR] {fail_message or 'Command failed'} ({type(error).__name__}).")
        return False


def _install_editable(recovery: Path) -> None:
    """Refresh editable metadata without replacing the running console launcher.

    Windows keeps pex.exe locked while the desktop updater is running. Install
    into a temporary target, validate the unchanged entry point, then copy only
    editable import files and metadata. Retain previous registration in recovery.
    """
    purelib = Path(sysconfig.get_path("purelib")).resolve()
    scripts = Path(sysconfig.get_path("scripts")).resolve()
    launcher = scripts / ("pex.exe" if os.name == "nt" else "pex")
    if not launcher.is_file():
        raise RuntimeError("The existing PEX console launcher is missing. Reinstall PEX manually.")
    with tempfile.TemporaryDirectory(prefix="pex-registration-") as temporary:
        target = Path(temporary)
        _run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation",
              "--target", str(target), "-e", "."], timeout=120)
        metadata = list(target.glob("*.dist-info"))
        if len(metadata) != 1:
            raise RuntimeError("Expected exactly one PEX editable distribution.")
        parser = configparser.ConfigParser()
        parser.read(metadata[0] / "entry_points.txt", encoding="utf-8")
        if dict(parser["console_scripts"]) != {"pex": "pex.cli:main"}:
            raise RuntimeError("Console entry points changed; reinstall PEX with all PEX windows closed.")
        previous = [path for path in purelib.iterdir() if (path.name.lower().startswith("pex-") and path.name[4:5].isdigit()
                    or path.name.lower().startswith(("__editable__.pex-", "__editable___pex_")))
                    and (path.name.endswith((".dist-info", ".pth", "_finder.py")))]
        backup = recovery / "registration"
        backup.mkdir(parents=True, exist_ok=True)
        for path in previous:
            if path.is_dir():
                shutil.copytree(path, backup / path.name)
            else:
                shutil.copy2(path, backup / path.name)
        # RECORD must reference the preserved real launcher, not target/bin/pex.
        record = metadata[0] / "RECORD"
        with record.open(newline="", encoding="utf-8") as stream:
            rows = [row for row in csv.reader(stream) if not row[0].startswith("bin/")]
        content = launcher.read_bytes()
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
        rows.append([os.path.relpath(launcher, purelib).replace(os.sep, "/"), f"sha256={digest}", str(len(content))])
        with record.open("w", newline="", encoding="utf-8") as stream:
            csv.writer(stream).writerows(rows)
        installed = set()
        for path in target.iterdir():
            if path.name in ("bin", "Scripts", "__pycache__"):
                continue
            installed.add(path.name)
            if path.is_dir():
                shutil.copytree(path, purelib / path.name, dirs_exist_ok=True)
            else:
                shutil.copy2(path, purelib / path.name)
        for path in previous:
            if path.name not in installed:
                # Move superseded registration out of site-packages, preserving it.
                destination = backup / f"superseded-{path.name}"
                if path.resolve().parent != purelib or not destination.resolve().is_relative_to(backup.resolve()):
                    raise RuntimeError("Unsafe registration recovery path.")
                shutil.move(str(path), str(destination))


def perform(log: Callable[[str], None]) -> bool:
    """Prepare and smoke-test a candidate before stopping the installed service.

    Recovery archives are retained; no reset, forced checkout, or automatic
    deletion of repository files is performed. Failed deployment always attempts
    to restart a previously running service and reports the recovery location.
    """
    stopped = False
    success = False
    recovery: Path | None = None
    try:
        with FileLock(ROOT_PATH / "update.lock", timeout=0):
            if not (PROJECT_PATH / ".git").exists():
                log("[ERROR] Automatic updates require an editable Git checkout.")
                return False
            if _run(["git", "status", "--porcelain"]).stdout.strip():
                log("[ERROR] Commit or preserve local changes before updating.")
                return False
            previous = _run(["git", "rev-parse", "HEAD"]).stdout.strip()
            log("[INFO] Fetching upstream and resolving an exact candidate commit...")
            _run(["git", "fetch", "--tags"], timeout=120)
            target = _run(["git", "rev-parse", "@{upstream}^{commit}"]).stdout.strip()
            if target == previous:
                log("[SUCCESS] PEX is already up to date.")
                return True
            _run(["git", "merge-base", "--is-ancestor", previous, target])
            recovery = ROOT_PATH / "recovery" / f"{time.time_ns()}-{previous[:12]}"
            recovery.mkdir(parents=True)
            _run(["git", "archive", "--format=zip", f"--output={recovery / 'previous.zip'}", previous])
            (recovery / "versions.json").write_text(json.dumps({"previous": previous, "target": target}), encoding="utf-8")
            config_path = ROOT_PATH / "config.json"
            if config_path.exists():
                shutil.copy2(config_path, recovery / "config.json")
            # Capture installed versions without exposing private index URLs.
            (recovery / "packages.txt").write_text(_run([sys.executable, "-m", "pip", "list", "--format=freeze"]).stdout, encoding="utf-8")
            with tempfile.TemporaryDirectory(prefix="pex-update-") as staging:
                stage = Path(staging)
                archive = stage / "candidate.zip"
                _run(["git", "archive", "--format=zip", f"--output={archive}", target])
                source = stage / "source"
                source.mkdir()
                with zipfile.ZipFile(archive) as bundle:
                    for member in bundle.infolist():
                        if not (source / member.filename).resolve().is_relative_to(source.resolve()):
                            raise ValueError("Unsafe path in update archive.")
                    bundle.extractall(source)
                environment = stage / "venv"
                _run([sys.executable, "-m", "venv", str(environment)], timeout=120)
                python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                log("[INFO] Validating the candidate in an isolated environment...")
                _run([str(python), "-m", "pip", "install", "-r", "requirements.lock"], cwd=source, timeout=600)
                _run([str(python), "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", "."], cwd=source, timeout=120)
                _run([str(python), "-m", "pex", "--version"], cwd=source)
                _run([str(python), "-m", "unittest", "discover", "-s", "tests"], cwd=source, timeout=120)
            # Recheck after network/installation work, before touching the service.
            if _run(["git", "rev-parse", "HEAD"]).stdout.strip() != previous or _run(["git", "status", "--porcelain"]).stdout.strip():
                raise RuntimeError("The checkout changed during preflight.")
            running = service.is_installed() and service.is_running()
            if running:
                ok, message = service.stop()
                if not ok:
                    raise RuntimeError(message)
                stopped = True
            log(f"[INFO] Installing validated commit {target[:12]}...")
            _run(["git", "merge", "--ff-only", target])
            _run([sys.executable, "-m", "pip", "install", "-r", "requirements.lock"], timeout=600)
            _install_editable(recovery)
            _run([sys.executable, "-m", "pip", "check"])
            success = True
    except Exception as error:
        log(f"[ERROR] Update failed ({type(error).__name__}).")
        if recovery:
            log(f"[INFO] Recovery snapshot: {recovery}")
    finally:
        if stopped:
            try:
                ok, message = service.start()
                if not ok:
                    success = False
                    log(f"[ERROR] Service restart failed: {message}")
                else:
                    log("[INFO] Previously running service restarted.")
            except Exception as error:
                success = False
                log(f"[ERROR] Service restart failed ({type(error).__name__}).")
    if success:
        log("[SUCCESS] Update completed.")
    return success
