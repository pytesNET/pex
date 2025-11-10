import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import mm
from pathlib import Path
from typing import Union, Tuple
from .. import config

if sys.platform == "win32":
    import win32print

JOB_STATUS_SPOOLING = 0x0008


def _get_sumatra_path() -> str:
    if sys.platform != "win32":
        raise NotImplementedError("This function is not supported on not-Windows systems.")

    candidates = [
        Path(r"C:\Program Files\SumatraPDF\SumatraPDF.exe"),
        Path(r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe")
    ]

    def add_portable_candidates(start: Path):
        for parent in [start.resolve()] + list(start.resolve().parents):
            candidates.append(parent / "tools" / "sumatra_pdf.exe")

    try:
        here = Path(__file__).parent
        add_portable_candidates(here)
    except NameError:
        pass
    add_portable_candidates(Path.cwd())

    seen = set()
    unique_candidates = []
    for c in candidates:
        if c not in seen:
            unique_candidates.append(c)
            seen.add(c)
    for p in unique_candidates:
        if p.is_file():
            return str(p)
    raise FileNotFoundError("No SumatraPDF executable found, please install SumatraPDF on the host computer.")


def _printer_supports_copies(printer_name: str) -> bool:
    if sys.platform == "win32":
        raise NotImplementedError("This function is not supported on Windows systems.")
    try:
        out = subprocess.check_output(
            ["lpoptions", "-p", printer_name, "-l"],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3
        )
        return "copies" in out.lower()
    except Exception:
        return False


def _wrap_text(text: str, font_name: str, font_size: int, max_width: int) -> list[str]:
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + " " + word if current_line else word
        line_width = stringWidth(test_line, font_name, font_size)
        if line_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _safe_remove(path: str, attempts: int = 5) -> bool:
    for i in range(attempts):
        try:
            os.remove(path)
            return True
        except Exception:
            time.sleep(0.2 * (i + 1))
    return False


def _cups_submit_job(filepath: str, printer: str, copies: int, extra_args: list[str] | None = None) -> str | None:
    if sys.platform == "win32":
        raise NotImplementedError("This function is not supported on Windows systems.")

    cmd = ["lp", "-d", printer]
    if copies > 1:
        cmd += ["-n", str(copies)]
    if extra_args:
        cmd += extra_args
    cmd.append(filepath)

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or "The lp command failed.")
    m = re.search(r"request id is (\S+-\d+)", res.stdout or "")
    return m.group(1) if m else None


def _cups_wait_for_job_disappear(printer: str, job_id: str, timeout: float = 5.0, interval: float = 0.2) -> None:
    if sys.platform == "win32":
        raise NotImplementedError("This function is not supported on Windows systems.")

    if not job_id:
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = subprocess.run(["lpstat", "-W", "not-completed", "-o", printer], capture_output=True, text=True)
        out = (st.stdout or "")
        if job_id not in out:
            break
        time.sleep(interval)


def _print_on_linux(filepath: str, printer: str, fmt: Tuple[int, int], orientation: str, quantity: int):
    mode = config.get_option('linux_command', '-n')
    if quantity == 1 or mode == "-n":
        if quantity == 1:
            subprocess.run(["lp", "-d", printer, filepath], check=True)
        else:
            subprocess.run(["lp", "-d", printer, "-n", str(quantity), filepath], check=True)
    elif mode == "-o":
        subprocess.run([
            "lp",
            "-d", printer,
            "-o", f"copies={quantity}",
            "-o", "Collate=true",
            filepath
        ], check=True)
    else:
        for _ in range(quantity):
            subprocess.run(["lp", "-d", printer, filepath], check=True)

    # Wait & Delete
    job_id = _cups_submit_job(filepath, printer, quantity)
    if isinstance(job_id, str):
        _cups_wait_for_job_disappear(printer, job_id)
    else:
        time.sleep(2.0)
    _safe_remove(filepath)


def _win32_list_job_ids(printer: str) -> set[int]:
    if sys.platform != "win32":
        raise NotImplementedError("This function is not supported on not-Windows systems.")

    inst = win32print.OpenPrinter(printer)
    try:
        jobs = win32print.EnumJobs(inst, 0, -1, 1)  # Level 1
        return {j["JobId"] for j in jobs}
    finally:
        win32print.ClosePrinter(inst)


def _win32_wait_for_spool(
    printer: str,
    known_ids: set[int],
    basename: str | None,
    timeout: float = 5.0,
    interval: float = 0.2
) -> None:
    if sys.platform != "win32":
        raise NotImplementedError("This function is not supported on not-Windows systems.")

    deadline = time.time() + timeout
    target_id = None

    # Discover job
    while time.time() < deadline and target_id is None:
        inst = win32print.OpenPrinter(printer)
        try:
            jobs = win32print.EnumJobs(inst, 0, -1, 1)
        finally:
            win32print.ClosePrinter(inst)

        for job in jobs:
            jid = job["JobId"]
            if jid in known_ids:
                continue
            if basename:
                doc = (job.get("pDocument") or "")
                if basename.lower() not in doc.lower():
                    continue
            target_id = jid
            break

        if target_id is None:
            time.sleep(interval)

    # Found nothing
    if target_id is None:
        return

    # Wait until job is done
    while time.time() < deadline:
        inst = win32print.OpenPrinter(printer)
        try:
            jobs = win32print.EnumJobs(inst, 0, -1, 1)
        finally:
            win32print.ClosePrinter(inst)

        jmap = {j["JobId"]: j for j in jobs}
        j = jmap.get(target_id)
        if j is None:
            break
        status = j.get("Status", 0)
        if not (status & JOB_STATUS_SPOOLING):
            break
        time.sleep(interval)


def _print_on_windows(filepath: str, printer: str, fmt: Tuple[int, int], orientation: str, quantity: int):
    print_defaults = {"DesiredAccess": win32print.PRINTER_ALL_ACCESS}
    handle = win32print.OpenPrinter(printer, print_defaults)
    try:
        level = 2
        attributes = win32print.GetPrinter(handle, level)
        attributes['pDevMode'].PaperWidth = fmt[0] * 10
        attributes['pDevMode'].PaperLength = fmt[1] * 10
        attributes['pDevMode'].Orientation = 1 if orientation == 'portrait' else 2
        attributes['pDevMode'].Copies = quantity
        win32print.SetPrinter(handle, level, attributes, 0)
    finally:
        win32print.ClosePrinter(handle)
    known_ids = _win32_list_job_ids(printer)

    # Submit Sumatra Print job
    sumatra_path = _get_sumatra_path()
    settings = f"noscale,{orientation}"
    if quantity > 1:
        settings += f",copies={quantity}"

    subprocess.run([
        sumatra_path,
        "-silent",
        "-exit-on-print",
        "-print-to", printer,
        "-print-settings", settings,
        filepath
    ], check=True)

    # Wait & Delete
    _win32_wait_for_spool(printer, known_ids, Path(filepath).name, timeout=5.0, interval=0.2)
    _safe_remove(filepath)


def list_printers():
    if sys.platform == "win32":
        return sorted([pr[2] for pr in win32print.EnumPrinters(2)], key=lambda s: s.lower())
    try:
        res = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=3)
        if res.returncode != 0:
            return []
        printers = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        return sorted(printers, key=lambda s: s.lower())
    except Exception:
        return []


def resolve_printer_name(printer_name: str) -> str:
    printers = config.get_option("printers", {}) or {}
    if printer_name in printers:
        return printers[printer_name]
    return printer_name


def printer_exists(printer_name: str) -> bool:
    printer = resolve_printer_name(printer_name)
    return True if printer in list_printers() else False


def resolve_paper_format(paper_format: Union[str, Tuple[int, int]]) -> Tuple[int, int]:
    if isinstance(paper_format, str):
        formats = config.get_option("formats", {}) or {}
        fmt = formats.get(paper_format)
        if not fmt:
            raise ValueError(f"Unknown paper format '{paper_format}'.")
        if not isinstance(fmt, (list, tuple)) or len(fmt) < 2:
            raise ValueError(f"Invalid format entry for '{paper_format}' in config.")
        width, height = fmt[0], fmt[1]
        if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
            raise ValueError(f"Invalid numeric values in format '{paper_format}'.")
        return width, height
    elif isinstance(paper_format, (tuple, list)) and len(paper_format) == 2:
        width, height = paper_format
        if not (isinstance(width, (int, float)) and isinstance(height, (int, float))):
            raise ValueError("paper_format tuple must contain two numeric values.")
        return width, height
    else:
        raise TypeError("paper_format must be a string or a tuple of two numbers.")


def print_file(
    filepath: str,
    printer_name: str,
    paper_format: Union[str, Tuple[int, int]],
    orientation: str = 'portrait',
    quantity: int = 1
):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"The filepath: '{filepath}' does not exist.")
    if orientation.lower() not in ('portrait', 'p', 'landscape', 'l',):
        raise ValueError(f"Unknown orientation '{orientation}' (use 'portrait', 'P' or 'landscape', 'L').")

    printer = resolve_printer_name(printer_name)
    if not printer_exists(printer):
        raise ValueError(f"The printer '{printer_name}' does not exist no this system.")

    fmt = resolve_paper_format(paper_format)
    orientation = 'portrait' if orientation.lower() in ('portrait','p',) else 'landscape'
    quantity = 1 if quantity <= 1 else quantity

    if sys.platform == "win32":
        _print_on_windows(filepath, printer, fmt, orientation, quantity)
    else:
        _print_on_linux(filepath, printer, fmt, orientation, quantity)


def print_lines(
    lines: Tuple[str],
    printer_name: str,
    paper_format: Union[str, Tuple[int, int]],
    orientation: str = 'portrait',
    quantity: int = 1,
    font_name: str = None,
    font_size: int = 10,
    line_height: int = 12,
):
    if orientation.lower() not in ('portrait', 'p', 'landscape', 'l',):
        raise ValueError(f"Unknown orientation '{orientation}' (use 'portrait', 'P' or 'landscape', 'L').")

    printer = resolve_printer_name(printer_name)
    if not printer_exists(printer):
        raise ValueError(f"The printer '{printer_name}' does not exist no this system.")

    fmt = resolve_paper_format(paper_format)
    orientation = 'portrait' if orientation.lower() in ('portrait','p',) else 'landscape'
    quantity = 1 if quantity <= 1 else quantity

    # Temporary File
    tmpdir = tempfile.gettempdir()
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
    filepath = os.path.join(tmpdir, f"custom_label-{timestamp}.pdf")

    # Create Canvas
    width = fmt[0] * mm
    height = fmt[1] * mm
    font_name = font_name if type(font_name) is str else 'Helvetica'

    c = canvas.Canvas(filepath, pagesize=(width, height))
    c.setFillColorRGB(0, 0, 0)

    # Wrap / Handle lines
    max_text_width = width - 2 * mm
    wrapped_lines = []
    for line in lines:
        wrapped_lines.extend(_wrap_text(line, font_name, font_size, max_text_width))

    total_text_height = line_height * len(wrapped_lines)
    start_y = (height + total_text_height) / 2 - font_size

    # Draw lines
    for i, line in enumerate(wrapped_lines):
        text_width = stringWidth(line, font_name, font_size)
        x = (width - text_width) / 2
        y = start_y - i * line_height
        c.setFont(font_name, font_size)
        c.drawString(x, y, line)
    c.save()

    # Print
    if sys.platform == "win32":
        _print_on_windows(filepath, printer, fmt, orientation, quantity)
    else:
        _print_on_linux(filepath, printer, fmt, orientation, quantity)
