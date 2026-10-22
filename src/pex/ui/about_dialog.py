"""Application identity and the bundled tools' license notices."""
import tkinter as tk
from tkinter import ttk
import webbrowser

from ..version import __VERSION__
from .utils import place_window_near


class AboutDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self._closed = False
        self._position_id = None
        self._status = tk.StringVar(value="")
        self.title("About PEX")
        self.transient(parent)
        self.resizable(False, False)

        body = ttk.Frame(self, padding=14)
        body.grid(sticky="nsew")
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text="PEX", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(body, text="Printer Execution Service", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Label(body, text=f"Version {__VERSION__}", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Separator(body).grid(row=3, column=0, sticky="ew", pady=10)
        ttk.Label(body, text="Copyright © 2024 - 2026 pytesNET <sam@pytes.net>").grid(row=4, column=0, sticky="w")
        ttk.Label(body, text="Published under the MIT License.", style="Muted.TLabel").grid(row=5, column=0, sticky="w", pady=(3, 10))
        ttk.Label(body, text="Bundled tools", style="Section.TLabel").grid(row=6, column=0, sticky="w", pady=(0, 6))

        self._tool_card(body, 7, "NSSM", "Windows service management · Public Domain",
                        "https://nssm.cc/", "https://git.nssm.cc/nssm/nssm/src/master/README.txt")
        self._tool_card(body, 8, "SumatraPDF", "PDF printing · GNU GPLv3\nIncluded components retain their respective licenses.",
                        "https://sumatrapdfreader.org/", "https://github.com/sumatrapdfreader/sumatrapdf/blob/master/COPYING")
        ttk.Label(body, textvariable=self._status, style="Muted.TLabel", wraplength=500).grid(row=9, column=0, sticky="w", pady=(2, 0))
        footer = ttk.Frame(body)
        footer.grid(row=10, column=0, sticky="ew", pady=(6, 0))
        self.github_button = ttk.Button(footer, text="View on GitHub", command=lambda: self.open_link("https://github.com/pytesNET/pex"))
        self.github_button.pack(side="left")
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self._position_id = self.after_idle(self._position)

    def _tool_card(self, parent: ttk.Frame, row: int, name: str, description: str,
                   website: str, license_url: str) -> None:
        card = ttk.Frame(parent, padding=8, style="Card.TFrame")
        card.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=name, style="CardSection.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, text=description, style="CardMuted.TLabel", wraplength=350).grid(row=1, column=0, sticky="w", pady=(4, 0))
        links = ttk.Frame(card, style="Card.TFrame")
        links.grid(row=0, column=1, rowspan=2, padx=(10, 0))
        ttk.Button(links, text="Website", command=lambda: self.open_link(website)).pack(fill="x", pady=(0, 4))
        ttk.Button(links, text="License", command=lambda: self.open_link(license_url)).pack(fill="x")

    def _position(self) -> None:
        self._position_id = None
        if not self._closed:
            place_window_near(self.master, self, dx=0, dy=0)

    def open_link(self, url: str) -> None:
        try:
            opened = webbrowser.open_new_tab(url)
        except webbrowser.Error:
            opened = False
        self._status.set("" if opened else f"Open this address in your browser: {url}")

    def destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._position_id is not None:
            self.after_cancel(self._position_id)
        if getattr(self.master, "_about_dialog", None) is self:
            self.master._about_dialog = None
        super().destroy()
