"""Shared ttk styles for the desktop application and its dialogs."""
import sys
import tkinter as tk
from tkinter import font as tkfont, ttk

BACKGROUND = "#f4f6f8"
SURFACE = "#ffffff"
TEXT = "#000000"
MUTED = TEXT
BORDER = "#cbd5e1"
ACCENT = "#2563eb"


def configure_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    # Native readonly combobox rendering differs from editable entries on Windows.
    # Clam lets both controls share the same field, border and state styling.
    if "clam" in style.theme_names():
        style.theme_use("clam")
    font = tkfont.nametofont("TkDefaultFont", root=root)
    font.configure(size=9)
    if sys.platform == "win32":
        font.configure(family="Segoe UI")
    family = font.actual("family")
    root.configure(background=BACKGROUND)
    style.configure(".", font=font, background=BACKGROUND, foreground=TEXT)
    style.configure("TFrame", background=BACKGROUND)
    style.configure("TLabel", background=BACKGROUND, foreground=TEXT)
    style.configure("TButton", padding=(5, 3))
    for widget in ("TButton", "TLabel", "TRadiobutton", "TCheckbutton"):
        style.map(widget, foreground=[("disabled", TEXT), ("!disabled", TEXT)])
    for field in ("TEntry", "TCombobox"):
        style.configure(field, padding=(4, 2), fieldbackground=SURFACE,
                        foreground=TEXT, bordercolor=BORDER, lightcolor=BORDER,
                        darkcolor=BORDER, borderwidth=1, relief="solid")
        style.map(field,
                  fieldbackground=[("disabled", "#eef1f5"), ("readonly", SURFACE), ("!disabled", SURFACE)],
                  foreground=[("disabled", MUTED), ("!disabled", TEXT)],
                  bordercolor=[("focus", ACCENT), ("!focus", BORDER)],
                  lightcolor=[("focus", ACCENT), ("!focus", BORDER)],
                  darkcolor=[("focus", ACCENT), ("!focus", BORDER)])
    style.configure("TCombobox", arrowsize=14, arrowcolor=MUTED)
    style.configure("Default.TRadiobutton", indicatorsize=14, indicatormargin=0, padding=2)
    style.map("Default.TRadiobutton",
              indicatorbackground=[("!disabled", SURFACE)],
              indicatorforeground=[("!disabled", TEXT)])
    style.configure("Card.TFrame", background=SURFACE)
    style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
    style.configure("Muted.TLabel", foreground=MUTED)
    style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
    style.configure("Title.TLabel", font=(family, 20, "bold"), foreground=TEXT)
    style.configure("Section.TLabel", font=(family, 10, "bold"), foreground=TEXT)
    style.configure("CardSection.TLabel", font=(family, 10, "bold"), background=SURFACE, foreground=TEXT)
    root.option_add("*TCombobox*Listbox.font", font)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*Text.foreground", TEXT)
