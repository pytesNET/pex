import tkinter as tk
from tkinter import ttk, messagebox
from .utils import place_window_near
from ..services import printer
from .. import config


class PrintersEditor(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self._printers = printer.list_printers() or []
        self._default = tk.StringVar(value=config.get_option("printer_default", "") or "")
        self._rows = []

        self.canvas = None
        self.scrollbar = None
        self.rows_frame = None
        self.inner = None

        # Configure TK window
        self.title("Configure Printers")
        self.resizable(True, True)
        self.transient(parent)
        self.after_idle(lambda: place_window_near(parent, self, mode="master", dx=0, dy=0))

        # Setup UI
        self.setup_ui()
        self.build_rows()

    def setup_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Frame
        frame = ttk.Frame(self, padding=12)
        frame.grid(sticky="nsew")
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Toolbar
        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="ew", pady=(0,8))
        bar.grid_columnconfigure(0, weight=1)
        btn_add = ttk.Button(bar, text="Add alias", width=20, command=lambda: self.add_row("", ""))
        btn_refresh = ttk.Button(bar, text="Refresh printers", width=20, command=self.refresh_printers)
        btn_add.pack(side="left", padx=(0, 8))
        btn_refresh.pack(side="left")
        bar.update_idletasks()

        # Header
        header = ttk.Frame(frame)
        header.grid(row=1, column=0, sticky="ew")
        for i, txt, w in [(0,"Alias", 24), (1,"System printer", 36), (2,"Default", 8), (3,"", 6)]:
            label = ttk.Label(header, text=txt)
            label.grid(row=0, column=i, sticky="w", padx=(0,8))
            header.grid_columnconfigure(i, weight=(1 if i in (0,1) else 0), minsize=w*6)

        # Scrollable area
        self.canvas = tk.Canvas(frame, highlightthickness=0, height=280)
        self.scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.rows_frame = ttk.Frame(self.canvas)
        self.inner = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=2, column=0, sticky="nsew", pady=(6,6))
        self.scrollbar.grid(row=2, column=1, sticky="ns")
        self.rows_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda ev: self.canvas.itemconfigure(self.inner, width=ev.width))

        # Footer
        footer = ttk.Frame(frame)
        footer.grid(row=3, column=0, sticky="e")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save", command=self.save).pack(side="right", padx=(0,8))

    def build_rows(self):
        self._default = tk.StringVar(value=config.get_option("printer_default", "") or "")
        aliases = config.get_option("printers", {}) or {}
        if aliases:
            for alias, sysname in aliases.items():
                self.add_row(alias, sysname)
        else:
            self.add_row("", "")

    def refresh_printers(self):
        self._printers = printer.list_printers() or []
        for row in self._rows:
            combo: ttk.Combobox = row["combo"]
            combo["values"] = self._printers

    def add_row(self, alias: str, sysname: str):
        row_frame = ttk.Frame(self.rows_frame)
        row_frame.grid(sticky="ew", padx=(0,0), pady=2)

        alias_var = tk.StringVar(value=alias)
        entry = ttk.Entry(row_frame, textvariable=alias_var)
        entry.grid(row=0, column=0, sticky="we", padx=(0,8))
        row_frame.grid_columnconfigure(0, weight=1, minsize=24*6)

        # Combobox
        combo = ttk.Combobox(row_frame, values=self._printers, state="readonly")
        combo.set(sysname or ("(choose)" if not self._printers else (sysname or "")))
        combo.grid(row=0, column=1, sticky="we", padx=(0,8))
        row_frame.grid_columnconfigure(1, weight=1, minsize=36*6)

        # Radiobutton
        radio = ttk.Radiobutton(row_frame, variable=self._default, value=alias or sysname)
        radio.grid(row=0, column=2, sticky="we", padx=(0,8))
        row_frame.grid_columnconfigure(2, weight=1, minsize=8*6)

        # Delete Button
        delete = ttk.Button(row_frame, text="✕", width=3, command=lambda: self.remove_row(row_frame))
        delete.grid(row=0, column=3, sticky="e")
        row_frame.grid_columnconfigure(3, weight=1, minsize=6*6)

        row = {"frame": row_frame, "alias_var": alias_var, "combo": combo, "radio": radio}
        self._rows.append(row)

        if alias and self._default.get() == alias:
            pass
        elif not self._default.get() and (alias or sysname):
            self._default.set(alias or sysname)

    def remove_row(self, frame):
        for i, R in enumerate(self._rows):
            if R["frame"] is frame:
                val = R["alias_var"].get() or R["combo"].get()
                if self._default.get() == val:
                    self._default.set("")
                R["frame"].destroy()
                del self._rows[i]
                break

    def save(self):
        aliases = {}
        seen_alias = set()

        for R in self._rows:
            alias = R["alias_var"].get().strip()
            sysname = R["combo"].get().strip()

            if not alias and not sysname:
                continue

            if not alias:
                messagebox.showerror("Validation error", "Alias must not be empty.")
                return
            if not sysname:
                messagebox.showerror("Validation error", f"System printer for alias '{alias}' is required.")
                return
            if self._printers and sysname not in self._printers:
                messagebox.showerror("Validation error", f"Unknown system printer: '{sysname}'.")
                return
            if alias in seen_alias:
                messagebox.showerror("Validation error", f"Duplicate alias: '{alias}'.")
                return

            aliases[alias] = sysname
            seen_alias.add(alias)

        chosen = self._default.get().strip()
        default_value = ""
        if chosen:
            default_value = chosen if chosen in aliases else chosen

        if not default_value and aliases:
            default_value = next(iter(aliases.keys()))

        config.set_option("printers", aliases)
        config.set_option("printer_default", default_value)

        self.destroy()
