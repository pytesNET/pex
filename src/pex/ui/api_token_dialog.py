"""Read and edit the saved API token without blocking the Tk event loop."""
import os
import queue
import secrets
import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable

from .. import config
from .utils import place_window_near


class ApiTokenDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self._closed = False
        self._busy = False
        self._loaded = False
        self._environment_token = os.environ.get("PEX_API_TOKEN", "")
        self._results = queue.Queue()
        self._poll_id = None
        self._position_id = None
        self._token = tk.StringVar(value="")
        self._show = tk.BooleanVar(value=False)
        self._status = tk.StringVar(value="Loading API token...")

        self.title("Manage API Token")
        self.transient(parent)
        self.resizable(False, False)
        frame = ttk.Frame(self, padding=10)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Use this value in the Authorization: Bearer <token> header.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        self.entry = ttk.Entry(frame, textvariable=self._token, show="*", width=64)
        self.entry.grid(row=1, column=0, sticky="ew")
        self.show_button = ttk.Checkbutton(frame, text="Show", variable=self._show,
            command=lambda: self.entry.configure(show="" if self._show.get() else "*"))
        self.show_button.grid(row=1, column=1, padx=(8, 0))

        actions = ttk.Frame(frame)
        actions.grid(row=2, column=0, columnspan=2, sticky="w", pady=6)
        self.copy_button = ttk.Button(actions, text="Copy", command=self.copy_token)
        self.copy_button.pack(side="left")
        self.generate_button = ttk.Button(actions, text="Generate", command=self.generate_token)
        self.generate_button.pack(side="left", padx=8)
        self.reload_button = ttk.Button(actions, text="Reload", command=self.reload_token)
        self.reload_button.pack(side="left")
        ttk.Label(frame, textvariable=self._status, wraplength=540).grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Saved changes apply to servers using this configuration. A server's PEX_API_TOKEN environment variable takes precedence.",
            wraplength=540).grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 8))
        footer = ttk.Frame(frame)
        footer.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(footer, text="Close", command=self.destroy).pack(side="right")
        self.save_button = ttk.Button(footer, text="Save", command=self.save_token)
        self.save_button.pack(side="right", padx=(0, 8))
        self._token.trace_add("write", lambda *_: self._update_controls())
        self._position_id = self.after_idle(self._position)
        self.reload_token()

    def _position(self) -> None:
        self._position_id = None
        if not self._closed:
            place_window_near(self.master, self, dx=0, dy=0)

    def _update_controls(self) -> None:
        if self._closed:
            return
        ready = self._loaded and not self._busy
        editable = ready and not self._environment_token
        self.entry.configure(state="normal" if editable else "readonly" if ready else "disabled")
        self.show_button.configure(state="normal" if ready else "disabled")
        self.copy_button.configure(state="normal" if ready and self._token.get() else "disabled")
        self.generate_button.configure(state="normal" if editable else "disabled")
        self.save_button.configure(state="normal" if editable else "disabled")
        self.reload_button.configure(state="disabled" if self._busy else "normal")

    def _start(self, action: Callable, success: Callable, message: str) -> None:
        if self._closed or self._busy:
            return
        self._busy = True
        self._status.set(message)
        self.configure(cursor="watch")
        self._update_controls()

        def worker():
            try:
                result = action(), None
            except Exception as error:
                # Do not echo the token through exception text or logs.
                result = None, type(error).__name__
            self._results.put((result, success))
        threading.Thread(target=worker, daemon=True).start()
        self._poll_id = self.after(50, self._poll_result)

    def _poll_result(self) -> None:
        self._poll_id = None
        if self._closed:
            return
        try:
            (value, error), success = self._results.get_nowait()
        except queue.Empty:
            self._poll_id = self.after(50, self._poll_result)
            return
        self._busy = False
        self.configure(cursor="")
        if error:
            self._status.set(f"Could not read or save the token ({error}). Use Reload to retry.")
        else:
            success(value)
        self._update_controls()

    def reload_token(self) -> None:
        if self._closed or self._busy:
            return
        if self._environment_token:
            self._loaded = True
            self._token.set(self._environment_token)
            self._status.set("This UI process uses PEX_API_TOKEN. Change the environment variable to replace this read-only value.")
            self._update_controls()
        else:
            self._start(lambda: config.get_option("server.token", ""), self._apply_token, "Loading API token...")

    def _apply_token(self, value: str) -> None:
        self._loaded = True
        self._token.set(value or "")
        self._status.set("Saved API token loaded." if value else "No saved token. Generate one and save it, or start the HTTP server to create one automatically.")

    def generate_token(self) -> None:
        if self._closed or self._busy or not self._loaded or self._environment_token:
            return
        self._token.set(secrets.token_urlsafe(32))
        self._status.set("New token generated. Save to apply it, then update your web application.")

    def copy_token(self) -> None:
        if self._closed or self._busy or not self._loaded or not self._token.get():
            return
        self.clipboard_clear()
        self.clipboard_append(self._token.get())
        self._status.set("Token copied to the clipboard.")

    def save_token(self) -> None:
        if self._closed or self._busy or not self._loaded or self._environment_token:
            return
        value = self._token.get().strip()
        if not value or any(ord(character) < 33 or ord(character) > 126 for character in value):
            self._status.set("Enter a non-empty token using printable ASCII characters without spaces.")
            return
        self._token.set(value)
        self._start(lambda: config.set_option("server.token", value), self._saved_token, "Saving API token...")

    def _saved_token(self, _: object) -> None:
        self._status.set("Token saved. Requests using the saved token must now send this value.")

    def destroy(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._position_id is not None:
            self.after_cancel(self._position_id)
        if self._poll_id is not None:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if getattr(self.master, "_api_token_dialog", None) is self:
            self.master._api_token_dialog = None
        super().destroy()
