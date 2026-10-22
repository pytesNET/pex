"""PDF label rendering and bounded, per-job platform print submission."""
from __future__ import annotations

import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from fpdf import FPDF
from .. import config

if sys.platform == "win32":
    import win32print

logger = logging.getLogger(__name__)
PT_TO_MM = 25.4 / 72
CORE_FONTS = {"helvetica", "times", "courier"}


def _timeout() -> int:
    return int(config.get_option("server.process_timeout", 30))


def _get_sumatra_path() -> str:
    configured = os.environ.get("PEX_SUMATRA_PATH") or config.get_option("sumatra_path", "")
    root = Path(__file__).resolve().parents[3]
    candidates = [Path(configured)] if configured else []
    candidates += [root / "tools/sumatra_pdf.exe", config.ROOT_PATH / "tools/sumatra_pdf.exe"]
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "SumatraPDF/SumatraPDF.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise FileNotFoundError("SumatraPDF not found. Configure PEX_SUMATRA_PATH or install it in tools.")


def _safe_remove(path: str, attempts: int = 5) -> bool:
    for attempt in range(attempts):
        try:
            Path(path).unlink(missing_ok=True)
            return True
        except OSError:
            time.sleep(0.1 * (attempt + 1))
    logger.warning("Temporary print file could not be removed")
    return False


def _cups_submit_job(filepath: str, printer: str, copies: int,
                     extra_args: list[str] | None = None) -> str | None:
    command = ["lp", "-d", printer, "-n", str(copies), *(extra_args or []), "--", filepath]
    result = subprocess.run(command, capture_output=True, text=True, timeout=_timeout(),
                            env={**os.environ, "LC_ALL": "C"})
    if result.returncode:
        raise RuntimeError("CUPS rejected the print job.")
    match = re.search(r"request id is (\S+-\d+)", result.stdout or "")
    return match.group(1) if match else None


def _print_on_linux(filepath: str, printer: str, fmt: tuple[float, float],
                    orientation: str, quantity: int) -> dict[str, Any]:
    mode = config.get_option("linux_command", "-n")
    options = ["-o", f"media=Custom.{fmt[0]:g}x{fmt[1]:g}mm", "-o", "print-scaling=none",
               "-o", f"orientation-requested={3 if orientation == 'portrait' else 4}"]
    job_ids = []
    # Each requested copy is submitted exactly once, including the legacy loop mode.
    for _ in range(quantity if mode == "for" else 1):
        copies = 1 if mode in ("for", "-o") else quantity
        extra = options + (["-o", f"copies={quantity}", "-o", "Collate=true"] if mode == "-o" else [])
        job_id = _cups_submit_job(filepath, printer, copies, extra)
        if job_id:
            job_ids.append(job_id)
    return {"backend": "cups", "spooler_ids": job_ids}


def _windows_paper(printer: str, fmt: tuple[float, float]) -> str:
    """Resolve an existing driver form without changing global printer defaults.

    The bundled Sumatra 3.5.2 requires a named driver form for custom labels.
    Newer-only custom-size switches must not silently fail on that version.
    """
    handle = win32print.OpenPrinter(printer)
    try:
        port = win32print.GetPrinter(handle, 2)["pPortName"]
        # DC_PAPERS / DC_PAPERSIZE query this device, not the server's global forms.
        paper_ids = win32print.DeviceCapabilities(printer, port, 2)
        sizes = win32print.DeviceCapabilities(printer, port, 3)
    finally:
        win32print.ClosePrinter(handle)
    if len(paper_ids) != len(sizes):
        raise ValueError("The printer returned inconsistent paper capabilities.")
    for paper_id, size in zip(paper_ids, sizes):
        dimensions = sorted((size["x"] / 10, size["y"] / 10))
        if all(abs(a - b) <= 0.5 for a, b in zip(dimensions, sorted(fmt))):
            return str(paper_id)
    raise ValueError(f"No driver paper form matches {fmt[0]:g} x {fmt[1]:g} mm. Configure that label size in the printer driver.")


def _print_on_windows(filepath: str, printer: str, fmt: tuple[float, float],
                      orientation: str, quantity: int) -> dict[str, Any]:
    if quantity > 999:
        raise ValueError("The bundled SumatraPDF supports at most 999 copies per job.")
    paper = _windows_paper(printer, fmt)
    settings = f"noscale,{orientation},{quantity}x,paper={paper}"
    result = subprocess.run([_get_sumatra_path(), "-silent", "-print-to", printer,
                             "-print-settings", settings, filepath],
                            capture_output=True, timeout=_timeout())
    if result.returncode:
        raise RuntimeError(f"SumatraPDF rejected the print job (exit {result.returncode}).")
    return {"backend": "sumatra", "spooler_ids": []}


def list_printers() -> list[str]:
    if sys.platform == "win32":
        return sorted({entry[2] for entry in win32print.EnumPrinters(2 | 4)}, key=str.casefold)
    result = subprocess.run(["lpstat", "-e"], capture_output=True, text=True, timeout=3)
    if result.returncode:
        raise RuntimeError("Could not list CUPS printers. Check that CUPS is running.")
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()}, key=str.casefold)


def resolve_printer_name(printer_name: str) -> str:
    if not isinstance(printer_name, str) or not printer_name.strip():
        raise ValueError("A printer or default printer is required.")
    return (config.get_option("printers", {}) or {}).get(printer_name, printer_name)


def printer_exists(printer_name: str) -> bool:
    return resolve_printer_name(printer_name) in list_printers()


def resolve_paper_format(paper_format: str | tuple | list) -> tuple[float, float]:
    dimensions = (config.get_option("formats", {}) or {}).get(paper_format) if isinstance(paper_format, str) else paper_format
    if not isinstance(dimensions, (list, tuple)) or len(dimensions) < 2:
        raise ValueError("Unknown or invalid paper format.")
    width, height = dimensions[:2]
    if any(type(value) not in (float, int) or not math.isfinite(value) or not 5 <= value <= 2000 for value in (width, height)):
        raise ValueError("Paper dimensions must be between 5 and 2000 mm.")
    return float(width), float(height)


def validate_options(printer_name: str, paper_format: str | tuple | list,
                     orientation: str, quantity: int) -> tuple[str, tuple[float, float], str]:
    printer = resolve_printer_name(printer_name)
    if printer not in list_printers():
        raise ValueError("The selected printer is not available.")
    if not isinstance(orientation, str) or orientation.lower() not in ("p", "portrait", "l", "landscape"):
        raise ValueError("Orientation must be portrait or landscape.")
    if type(quantity) is not int or not 1 <= quantity <= config.get_option("server.max_copies", 100):
        raise ValueError("Quantity is outside the configured limit.")
    return printer, resolve_paper_format(paper_format), "portrait" if orientation.lower() in ("p", "portrait") else "landscape"


def print_file(filepath: str, printer_name: str, paper_format: str | tuple | list,
               orientation: str = "portrait", quantity: int = 1) -> dict[str, Any]:
    """Submit a caller-owned PDF; callers retain responsibility for its lifetime."""
    with Path(filepath).open("rb") as stream:
        if b"%PDF-" not in stream.read(1024):
            raise ValueError("Only PDF files are supported.")
    printer, fmt, orientation = validate_options(printer_name, paper_format, orientation, quantity)
    return (_print_on_windows if sys.platform == "win32" else _print_on_linux)(str(Path(filepath).resolve()), printer, fmt, orientation, quantity)


def _font(pdf: FPDF, line: dict, font_name: str, font_size: float) -> None:
    family = line.get("font") or font_name
    if not isinstance(family, str) or family.lower() not in CORE_FONTS:
        raise ValueError("Supported fonts are helvetica, times, and courier.")
    size = line.get("size", font_size)
    if type(size) not in (int, float) or not math.isfinite(size) or not 1 <= size <= 144:
        raise ValueError("Font size must be between 1 and 144 points.")
    for option in ("bold", "italic", "underline", "strikethrough"):
        if type(line.get(option, False)) is not bool:
            raise ValueError(f"{option} must be a boolean.")
    style = "".join(letter for key, letter in (("bold", "B"), ("italic", "I"), ("underline", "U"), ("strikethrough", "S")) if line.get(key, False))
    pdf.set_font(family.lower(), style=style, size=size)


def _wrap_text(line: dict, pdf: FPDF, max_width: float) -> list[dict]:
    """Preserve explicit blank lines and split words wider than the label."""
    text = line.get("text", "")
    if not isinstance(text, str):
        raise ValueError("Each line's text must be a string.")
    # Core PDF fonts use Windows-1252; reject unsupported characters explicitly.
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        raise ValueError("Label text contains unsupported characters; upload a PDF with embedded fonts for Unicode text.") from None
    result = []
    for paragraph in text.split("\n"):
        current = ""
        for character in paragraph:
            candidate = current + character
            if pdf.get_string_width(candidate) > max_width:
                if not current:
                    raise ValueError("A character is wider than the label's printable area.")
                # Prefer breaking at a word boundary while retaining all characters.
                split = current.rfind(" ")
                if split > 0:
                    result.append({**line, "text": current[:split]})
                    current = current[split + 1:] + character
                else:
                    result.append({**line, "text": current})
                    current = character
                if pdf.get_string_width(current) > max_width:
                    raise ValueError("A character is wider than the label's printable area.")
            else:
                current = candidate
        result.append({**line, "text": current})
    return result


def render_lines(lines: list[dict], paper_format: str | tuple | list,
                 orientation: str = "portrait", font_name: str | None = None,
                 font_size: float = 10, line_height: float = 12) -> bytes:
    """Render in memory so invalid label content never enters the print queue."""
    if not isinstance(lines, list) or not 1 <= len(lines) <= 200 or any(not isinstance(line, dict) for line in lines):
        raise ValueError("Provide between 1 and 200 text lines.")
    if sum(len(str(line.get("text", ""))) for line in lines) > 20000:
        raise ValueError("Label text is too long.")
    fmt = resolve_paper_format(paper_format)
    if orientation.lower() not in ("p", "portrait", "l", "landscape"):
        raise ValueError("Orientation must be portrait or landscape.")
    pdf = FPDF(orientation="P" if orientation.lower() in ("p", "portrait") else "L", unit="mm", format=tuple(sorted(fmt)))
    pdf.core_fonts_encoding = "cp1252"
    pdf.set_auto_page_break(False)
    pdf.add_page()
    wrapped = []
    for line in lines:
        _font(pdf, line, font_name or "helvetica", font_size)
        height = line.get("height", line_height)
        if type(height) not in (int, float) or not math.isfinite(height) or not 1 <= height <= 300 or height < pdf.font_size_pt:
            raise ValueError("Line height must fit the font and be between 1 and 300 points.")
        wrapped.extend({**part, "height": height} for part in _wrap_text(line, pdf, pdf.w - 4))
    total = sum(line["height"] * PT_TO_MM for line in wrapped)
    if total > pdf.h - 4:
        raise ValueError("The text does not fit on one label. Reduce text or font size.")
    y = (pdf.h - total) / 2
    for line in wrapped:
        _font(pdf, line, font_name or "helvetica", font_size)
        y += line["height"] * PT_TO_MM
        pdf.text(x=(pdf.w - pdf.get_string_width(line["text"])) / 2,
                 y=y - (line["height"] - pdf.font_size_pt) * PT_TO_MM / 2 - pdf.font_size * 0.2,
                 text=line["text"])
    return bytes(pdf.output())


def print_lines(lines: list[dict], printer_name: str, paper_format: str | tuple | list,
                orientation: str = "portrait", quantity: int = 1, font_name: str | None = None,
                font_size: float = 10, line_height: float = 12) -> dict[str, Any]:
    content = render_lines(lines, paper_format, orientation, font_name, font_size, line_height)
    fd, name = tempfile.mkstemp(prefix="pex-label-", suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        return print_file(name, printer_name, paper_format, orientation, quantity)
    finally:
        _safe_remove(name)
