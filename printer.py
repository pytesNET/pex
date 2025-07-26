from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.units import mm
import tempfile
import os
import pexconfig
import subprocess
import sys

if sys.platform == "win32":
    import win32print


def get_printers():
    if sys.platform == "win32":
        printers = [pr[2] for pr in win32print.EnumPrinters(2)]
    else:
        try:
            out = os.popen("lpstat -e").read()
            printers = [line.strip() for line in out.splitlines() if line.strip()]
        except Exception:
            printers = []
    return sorted(printers, key=lambda s: s.lower())


def wrap_text(text, font_name, font_size, max_width):
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


def convert_format(paper: str):
    paper = paper.lower().replace('×', 'x').replace(' ', '')
    standards = {
        'a4': (210, 297),
        'a5': (148, 210),
        'a6': (105, 148),
    }
    if paper in standards:
        return standards[paper]

    try:
        width_str, height_str = paper.lower().split('x')
        width = float(width_str)
        height = float(height_str)
        return width, height
    except Exception as e:
        raise ValueError(f"Invalid Paper Format: '{paper}'.") from e


def file(filepath: str, paper: str = 'A6', orientation: str = 'portrait', quantity: int = 1):
    printer_name = pexconfig.get_file_printer()
    if len(printer_name) == 0 or printer_name == "null":
        return False

    paper = convert_format(paper)
    if sys.platform == "win32":
        print_defaults = {"DesiredAccess": win32print.PRINTER_ALL_ACCESS}
        handle = win32print.OpenPrinter(printer_name, print_defaults)
        level = 2
        attributes = win32print.GetPrinter(handle, level)
        attributes['pDevMode'].PaperWidth = paper[0] * 10
        attributes['pDevMode'].PaperLength = paper[1] * 10
        attributes['pDevMode'].Orientation = 1 if orientation == 'portrait' else 2
        attributes['pDevMode'].Copies = quantity
        win32print.SetPrinter(handle, level, attributes, 0)
        sumatra_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
        subprocess.run([
            sumatra_path,
            "-print-to", printer_name,
            "-print-settings", "noscale,portrait,paper=A6",
            filepath
        ], check=True)
    else:
        subprocess.run(["lp", "-d", printer_name, "-n", str(quantity), filepath], check=True)


def label(model: str, hashtag: str, quantity: int = 1):
    printer_name = pexconfig.get_label_printer()
    if len(printer_name) == 0 or printer_name == "null":
        return False

    tmpdir = tempfile.gettempdir()
    file = os.path.join(tmpdir, 'label.pdf')

    wmm = 51
    hmm = 25
    w = wmm * mm
    h = hmm * mm

    c = canvas.Canvas(file, pagesize=(w, h))
    c.setFillColorRGB(0, 0, 0)

    font_name = "Helvetica-Bold"
    font_size = 10
    line_height = 12

    max_text_width = w - 2 * mm
    wrapped_lines = []
    for line in [model, hashtag]:
        wrapped_lines.extend(wrap_text(line, font_name, font_size, max_text_width))

    total_text_height = line_height * len(wrapped_lines)
    start_y = (h + total_text_height) / 2 - font_size

    for i, line in enumerate(wrapped_lines):
        text_width = stringWidth(line, font_name, font_size)
        x = (w - text_width) / 2
        y = start_y - i * line_height
        c.setFont(font_name, font_size)
        c.drawString(x, y, line)
    c.save()

    if sys.platform == "win32":
        print_defaults = {"DesiredAccess": win32print.PRINTER_ALL_ACCESS}
        handle = win32print.OpenPrinter(printer_name, print_defaults)
        level = 2
        attributes = win32print.GetPrinter(handle, level)
        attributes['pDevMode'].PaperWidth = 510
        attributes['pDevMode'].PaperLength = 250
        attributes['pDevMode'].Orientation = 1
        attributes['pDevMode'].Copies = quantity
        win32print.SetPrinter(handle, level, attributes, 0)
        sumatra_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
        subprocess.run([
            sumatra_path,
            "-print-to", printer_name,
            "-print-settings", "noscale,landscape",
            file
        ], check=True)
    else:
        subprocess.run(["lp", "-d", printer_name, "-n", str(quantity), "-o", "landscape", file], check=True)
