import tkinter as tk
import queue
import threading
import uuid
from tkinter import ttk, messagebox
from .utils import place_window_near
from .. import config


class PrintersEditor(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)

        self._printers: list[str] = []
        self._default = tk.StringVar(value="")
        self._rows = []
        self._loading = False
        self._loaded = False
        self._load_error = False
        self._closed = False
        self._load_results = queue.Queue()
        self._poll_id = None
        self._position_id = None
        self._startup_id = None
        self._scroll_id = None
        self._status = tk.StringVar(value="Loading printers...")

        self.canvas = None
        self.scrollbar = None
        self.rows_frame = None
        self.inner = None

        # Configure TK window
        self.title("Configure Printers")
        self.resizable(True, True)
        self.transient(parent)

        # Setup UI
        self.setup_ui()
        self._update_controls()
        self._position_id = self.after_idle(self._position)
        self._startup_id = self.after_idle(self._start_discovery)

    def setup_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Frame
        frame = ttk.Frame(self, padding=8)
        frame.grid(sticky="nsew")
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Toolbar
        bar = ttk.Frame(frame)
        bar.grid(row=0, column=0, sticky="ew", pady=(0,8))
        bar.grid_columnconfigure(0, weight=1)
        self.btn_add = ttk.Button(bar, text="Add alias", width=20, command=lambda: self.add_row("", ""))
        self.btn_refresh = ttk.Button(bar, text="Refresh printers", width=20, command=self.refresh_printers)
        self.btn_add.pack(side="left", padx=(0, 8))
        self.btn_refresh.pack(side="left")

        # Header
        header = ttk.Frame(frame)
        header.grid(row=1, column=0, sticky="ew")
        self._configure_columns(header)
        for i, text in enumerate(("Alias", "System printer", "Default", "")):
            ttk.Label(header, text=text).grid(row=0, column=i, sticky="" if i == 2 else "w", padx=(0, 8))

        # Scrollable area
        self.canvas = tk.Canvas(frame, highlightthickness=0, borderwidth=0, height=280, background=ttk.Style(self).lookup("TFrame", "background"))
        self.scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.rows_frame = ttk.Frame(self.canvas)
        self.rows_frame.columnconfigure(0, weight=1)
        self.inner = self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=2, column=0, sticky="nsew", pady=(6,6))
        self.rows_frame.bind("<Configure>", self._schedule_scroll_region)
        self.canvas.bind("<Configure>", self._resize_canvas)

        # Loading/error feedback remains visible while discovery runs off-thread.
        status = ttk.Frame(frame)
        status.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(2, 8))
        status.columnconfigure(0, weight=1)
        ttk.Label(status, textvariable=self._status, wraplength=480).grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=100)
        self.progress.grid(row=0, column=1, padx=(12, 0))

        # Cancel remains available during discovery; Save requires a successful load.
        footer = ttk.Frame(frame)
        footer.grid(row=4, column=0, sticky="e")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        self.btn_save = ttk.Button(footer, text="Save", command=self.save)
        self.btn_save.pack(side="right", padx=(0,8))

    def _resize_canvas(self, event):
        self.canvas.itemconfigure(self.inner, width=event.width)
        self._schedule_scroll_region()

    def _schedule_scroll_region(self, event=None):
        if self._scroll_id is not None:
            self.after_cancel(self._scroll_id)
        self._scroll_id = self.after_idle(self._update_scroll_region)

    def _update_scroll_region(self):
        self._scroll_id = None
        # A region smaller than the viewport lets Tk shift short lists away
        # from the top. Keep it at least as tall as the visible canvas.
        viewport = self.canvas.winfo_height()
        content = self.rows_frame.winfo_reqheight() if self._rows else 0
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), max(viewport, content)))
        if content > viewport:
            self.scrollbar.grid(row=2, column=1, sticky="ns", pady=(6, 6))
        else:
            self.canvas.yview_moveto(0)
            self.scrollbar.grid_remove()

    @staticmethod
    def _configure_columns(container):
        for column, width, weight in ((0, 200, 1), (1, 300, 2), (2, 72, 0), (3, 48, 0)):
            container.columnconfigure(column, minsize=width, weight=weight)

    def _position(self):
        self._position_id = None
        if not self._closed:
            place_window_near(self.master, self, mode="master", dx=0, dy=0)

    def _start_discovery(self):
        self._startup_id = None
        self.refresh_printers()

    def build_rows(self, settings: dict):
        self._default.set(settings.get("printer_default") or "")
        aliases = settings.get("printers") or {}
        if aliases:
            for alias, sysname in aliases.items():
                self.add_row(alias, sysname)
        else:
            self.add_row("", "")

    def _update_controls(self):
        ready = self._loaded and not self._loading
        self.btn_add.config(state="normal" if ready else "disabled")
        self.btn_refresh.config(state="disabled" if self._loading else "normal")
        self.btn_save.config(state="normal" if ready and not self._load_error else "disabled")
        for row in self._rows:
            row["combo"].config(state="readonly" if ready else "disabled")

    def refresh_printers(self):
        if self._closed or self._loading:
            return
        self._loading = True
        initial = not self._loaded
        self._status.set("Loading printers..." if initial else "Refreshing printers...")
        self.configure(cursor="watch")
        self.progress.grid()
        self.progress.start(10)
        self._update_controls()

        def worker():
            # No Tk calls from this thread, including after() or winfo_exists().
            try:
                if initial:
                    self._load_results.put(("settings", config.load_config()))
                # Importing the backend loads PDF/font libraries. Keep that work,
                # as well as native discovery, off Tk's thread on the first open.
                from ..services import printer
                self._load_results.put(("printers", printer.list_printers() or []))
            except Exception as error:
                self._load_results.put(("error", str(error)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_id = self.after(50, self._poll_printers)

    def _poll_printers(self):
        self._poll_id = None
        if self._closed:
            return
        while True:
            try:
                kind, value = self._load_results.get_nowait()
            except queue.Empty:
                self._poll_id = self.after(50, self._poll_printers)
                return
            if kind == "settings":
                if not self._loaded:
                    self.build_rows(value)
                    self._loaded = True
                    self._update_controls()
                continue
            break

        self._loading = False
        self._load_error = kind == "error"
        self.progress.stop()
        self.progress.grid_remove()
        self.configure(cursor="")
        if self._load_error:
            self._status.set(f"Could not load printers: {value}. Use Refresh printers to retry.")
        else:
            self._printers = value
            for row in self._rows:
                row["combo"]["values"] = self._printers
            self._status.set(f"Available printers: {len(value)}" if value else "No printers found. Check the printer setup and refresh.")
        self._update_controls()

    def destroy(self):
        if self._closed:
            return
        self._closed = True
        for callback in (self._position_id, self._startup_id, self._scroll_id):
            if callback is not None:
                self.after_cancel(callback)
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        self.progress.stop()
        if getattr(self.master, "_printers_editor", None) is self:
            self.master._printers_editor = None
        super().destroy()

    def add_row(self, alias: str, sysname: str):
        row_frame = ttk.Frame(self.rows_frame)
        row_frame.grid(sticky="ew", padx=0, pady=2)
        self._configure_columns(row_frame)

        alias_var = tk.StringVar(value=alias)
        entry = ttk.Entry(row_frame, textvariable=alias_var, width=1)
        entry.grid(row=0, column=0, sticky="we", padx=(0,8))

        # Combobox
        combo = ttk.Combobox(row_frame, values=self._printers, state="readonly", width=1)
        combo.set(sysname or "")
        combo.grid(row=0, column=1, sticky="we", padx=(0,8))

        # Radiobutton
        row_id = uuid.uuid4().hex
        radio = ttk.Radiobutton(row_frame, variable=self._default, value=row_id, style="Default.TRadiobutton")
        radio.grid(row=0, column=2, padx=(0,8))

        # Delete Button
        delete = ttk.Button(row_frame, text="✕", width=3, command=lambda: self.remove_row(row_frame))
        delete.grid(row=0, column=3, sticky="e")

        row = {"frame": row_frame, "alias_var": alias_var, "combo": combo, "radio": radio, "id": row_id}
        self._rows.append(row)
        self._schedule_scroll_region()

        if self._default.get() in (alias, sysname) and (alias or sysname):
            self._default.set(row_id)
        elif not self._default.get() and (alias or sysname):
            self._default.set(row_id)

    def remove_row(self, frame):
        for i, R in enumerate(self._rows):
            if R["frame"] is frame:
                val = R["id"]
                if self._default.get() == val:
                    self._default.set("")
                R["frame"].destroy()
                del self._rows[i]
                self._schedule_scroll_region()
                break

    def save(self):
        if self._closed or self._loading or not self._loaded or self._load_error:
            return
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
            default_value = next((row["alias_var"].get().strip() for row in self._rows if row["id"] == chosen), "")
        if default_value not in aliases:
            default_value = ""

        if not default_value and aliases:
            default_value = next(iter(aliases.keys()))

        try:
            config.set_options({"printers": aliases, "printer_default": default_value})
        except (OSError, ValueError, TimeoutError) as error:
            messagebox.showerror("Save failed", str(error), parent=self)
            return

        self.destroy()
