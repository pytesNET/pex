import ctypes
import os
import subprocess
import sys
import threading
import queue
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk, messagebox
from typing import Callable
from pex import config
from pex.updater import perform as perform_update
from pex.services import service
from pex.version import __NAME__, __VERSION__
from .theme import configure_theme


ROOT_PATH = Path(__file__).resolve().parents[3]


class PexApp(tk.Tk):
    def __init__(self):
        super().__init__()
        configure_theme(self)
        self._last_installed = False
        self._last_running = False
        self._exec_inflight = False
        self._poll_inflight = False
        self._stopped = False
        self._ui_events = queue.Queue()
        self._printers_editor: tk.Toplevel | None = None
        self._opening_printers_editor = False
        self._api_token_dialog: tk.Toplevel | None = None
        self._opening_api_token_dialog = False
        self._about_dialog: tk.Toplevel | None = None
        self._opening_about_dialog = False

        self.btn_install = None
        self.btn_uninstall = None
        self.btn_spooler = None
        self.btn_update = None
        self.btn_start = None
        self.btn_stop = None
        self.btn_restart = None
        self.btn_status = None
        self.btn_exit = None
        self.output_text = None

        self.loading = True
        self.menubar = None
        self.settings_menu = None
        self.linux_menu = None
        self.linux_cmd = tk.StringVar(value=config.get_option('linux_command'))

        self.title(f"{__NAME__} ({__VERSION__})")
        self._set_icon()
        self.setup_ui()
        self.create_menu()
        self.after(50, self._drain_ui_events)
        self.auto_refresh()

    def destroy(self):
        self._stopped = True
        super().destroy()

    def _set_icon(self):
        if sys.platform == 'win32':
            icon = str(ROOT_PATH / 'icon-color.ico')
            if os.path.exists(icon):
                try:
                    self.iconbitmap(default=icon)
                    self.iconbitmap(icon)
                except tk.TclError:
                    pass
        else:
            icon = str(ROOT_PATH / 'icon-color.png')
            if os.path.exists(icon):
                try:
                    self.iconphoto(True, tk.PhotoImage(file=icon))
                except tk.TclError:
                    pass

    def setup_ui(self):
        frame = ttk.Frame(self)
        frame.pack(padx=12, pady=6)

        shared = {"width": 14, "state": "disabled"}
        self.btn_install = ttk.Button(frame, text="Install", command=lambda: self.exec(service.install), **shared)
        self.btn_uninstall = ttk.Button(frame, text="Uninstall", command=lambda: self.exec(service.uninstall), **shared)
        self.btn_spooler = ttk.Button(frame, text="Restart Spooler", command=lambda: self.exec(self._cmd_restart_spooler), width=32, state="disabled")
        self.btn_update = ttk.Button(frame, text="Update PEX", command=lambda: self.exec(self._cmd_update), **shared)
        self.btn_start = ttk.Button(frame, text="Start", command=lambda: self.exec(service.start), **shared)
        self.btn_stop = ttk.Button(frame, text="Stop", command=lambda: self.exec(service.stop), **shared)
        self.btn_restart = ttk.Button(frame, text="Restart", command=lambda: self.exec(service.restart), **shared)
        self.btn_status = ttk.Button(frame, text="Status", command=lambda: self.exec(service.status), **shared)
        self.btn_exit = ttk.Button(frame, text="Exit PEX", command=self.destroy, **shared)

        self.btn_install.grid(row=0, column=0, padx=3, pady=3)
        self.btn_uninstall.grid(row=0, column=1, padx=3, pady=3)
        self.btn_spooler.grid(row=0, column=2, columnspan=2, padx=3, pady=3)
        self.btn_update.grid(row=0, column=4, padx=3, pady=3)
        self.btn_start.grid(row=1, column=0, padx=3, pady=3)
        self.btn_stop.grid(row=1, column=1, padx=3, pady=3)
        self.btn_restart.grid(row=1, column=2, padx=3, pady=3)
        self.btn_status.grid(row=1, column=3, padx=3, pady=3)
        self.btn_exit.grid(row=1, column=4, padx=3, pady=3)

        self.output_text = scrolledtext.ScrolledText(self, height=10, width=60, padx=8, pady=6)
        self.output_text.pack(fill="x", padx=8, pady=6)
        self.output_text.insert(tk.END, "[LOADING] Loading application, please wait...")
        self.output_text.config(state='disabled')

    def create_menu(self):
        self.menubar = tk.Menu(self, tearoff=0)
        self.config(menu=self.menubar)

        self.settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.linux_menu = tk.Menu(self.settings_menu, tearoff=0)

        self.menubar.add_command(label="Printers", command=self.open_printers_editor)
        self.menubar.add_cascade(label="Settings", menu=self.settings_menu)
        self.settings_menu.add_command(label="Manage API Token", command=self.open_api_token_dialog)
        self.menubar.add_command(label="About", command=self.open_about_dialog)
        if sys.platform == "win32":
            self.settings_menu.add_command(label="Clear pending Jobs", command=self.confirm_clear_queue)
        else:
            self.settings_menu.add_cascade(label="Linux Command", menu=self.linux_menu)
        self.linux_menu.add_radiobutton(
            label="-n",
            variable=self.linux_cmd,
            value="-n",
            command=lambda: config.set_option('linux_command', self.linux_cmd.get())
        )
        self.linux_menu.add_radiobutton(
            label="-o copies",
            variable=self.linux_cmd,
            value="-o",
            command=lambda: config.set_option('linux_command', self.linux_cmd.get())
        )
        self.linux_menu.add_radiobutton(
            label="for loop",
            variable=self.linux_cmd,
            value="for",
            command=lambda: config.set_option('linux_command', self.linux_cmd.get())
        )

    def open_printers_editor(self):
        if self._stopped or self._opening_printers_editor:
            return
        dialog = self._printers_editor
        if dialog is not None and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            dialog.focus_set()
            return

        from pex.ui.printers_editor import PrintersEditor
        self._opening_printers_editor = True
        try:
            self._printers_editor = PrintersEditor(self)
        finally:
            self._opening_printers_editor = False

    def open_api_token_dialog(self):
        if self._stopped or self._opening_api_token_dialog:
            return
        dialog = self._api_token_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            dialog.focus_set()
            return

        from pex.ui.api_token_dialog import ApiTokenDialog
        self._opening_api_token_dialog = True
        try:
            self._api_token_dialog = ApiTokenDialog(self)
        finally:
            self._opening_api_token_dialog = False

    def open_about_dialog(self):
        if self._stopped or self._opening_about_dialog:
            return
        dialog = self._about_dialog
        if dialog is not None and dialog.winfo_exists():
            dialog.deiconify()
            dialog.lift()
            dialog.focus_set()
            return

        from pex.ui.about_dialog import AboutDialog
        self._opening_about_dialog = True
        try:
            self._about_dialog = AboutDialog(self)
        finally:
            self._opening_about_dialog = False

    def _run_spooler_script(self, clear: bool = False):
        if sys.platform != "win32":
            return False, "Spooler maintenance is available on Windows only."
        if not ctypes.windll.shell32.IsUserAnAdmin():
            return False, "Administrator rights are required for spooler maintenance."
        name = "clear_print_queue.bat" if clear else "restart_spooler.bat"
        script = ROOT_PATH / "scripts" / name
        if not script.is_file():
            return False, f"Maintenance script not found: {name}"
        command = ["cmd", "/c", str(script)] + (["--confirm-clear"] if clear else [])
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, errors="replace")
        message = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0, message

    def _cmd_restart_spooler(self):
        return self._run_spooler_script()

    def confirm_clear_queue(self):
        if self._exec_inflight:
            return
        if messagebox.askyesno("Delete all pending print jobs?",
                "This deletes ALL waiting Windows print jobs, including jobs from other applications. Continue?",
                parent=self, default="no"):
            self.exec(lambda: self._run_spooler_script(clear=True))

    def _drain_ui_events(self):
        if self._stopped:
            return
        for _ in range(100):
            try:
                callback = self._ui_events.get_nowait()
            except queue.Empty:
                break
            callback()
        self.after(50, self._drain_ui_events)

    def _cmd_update(self):
        logs: list[str] = []
        success = perform_update(logs.append)
        return success, "\n".join(logs)

    def exec(self, fn: Callable):
        if self._exec_inflight or self._stopped:
            return
        self._exec_inflight = True
        self._disable_buttons()

        def worker():
            try:
                result = fn()
            except Exception as error:
                result = False, str(error)

            def finish():
                self._exec_inflight = False
                self.log(result)
                self.refresh_buttons()
            self._ui_events.put(finish)
        threading.Thread(target=worker, daemon=True).start()

    def log(self, output):
        self.output_text.config(state='normal')
        self.output_text.delete(1.0, tk.END)

        if isinstance(output, tuple):
            status, message = output
            if status:
                self.output_text.insert(tk.END, "[SUCCESS] ", 'success')
            else:
                self.output_text.insert(tk.END, "[ERROR] ", 'error')
            self.output_text.insert(tk.END, message)
        else:
            self.output_text.insert(tk.END, str(output))
        self.output_text.config(state='disabled')

    def _disable_buttons(self):
        self.btn_install.config(state='disabled')
        self.btn_uninstall.config(state='disabled')
        self.btn_spooler.config(state='disabled')
        self.btn_update.config(state='disabled')
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='disabled')
        self.btn_restart.config(state='disabled')
        self.btn_status.config(state='disabled')
        self.btn_exit.config(state='disabled')

    def _refresh_states(self, installed: bool, running: bool):
        if self._stopped:
            return

        self._last_installed = installed
        self._last_running = running

        if not self._poll_inflight and not self._exec_inflight:
            self.btn_install.config(state='normal' if not installed else 'disabled')
            self.btn_uninstall.config(state='normal' if installed and not running else 'disabled')
            self.btn_spooler.config(state='normal' if sys.platform == 'win32' else 'disabled')
            self.btn_update.config(state='normal')
            self.btn_start.config(state='normal' if installed and not running else 'disabled')
            self.btn_stop.config(state='normal' if installed and running else 'disabled')
            self.btn_restart.config(state='normal' if installed and running else 'disabled')
            self.btn_status.config(state='normal' if installed else 'disabled')
            self.btn_exit.config(state='normal')

        if self.loading:
            self.output_text.config(state='normal')
            self.output_text.delete(1.0, tk.END)
            self.output_text.insert(tk.END, "[READY] Application is ready to be used...")
            self.output_text.config(state='disabled')
            self.loading = False

    def refresh_buttons(self):
        if self._poll_inflight:
            return
        self._poll_inflight = True

        def worker():
            try:
                installed = service.is_installed()
                running = service.is_running()
            except Exception as e:
                installed, running = False, False
                msg = f"[ERROR] {e}"
            else:
                msg = None

            def apply():
                self._poll_inflight = False
                self._refresh_states(installed, running)
                if msg:
                    self.output_text.config(state='normal')
                    self.output_text.insert(tk.END, "\n" + msg)
                    self.output_text.config(state='disabled')

            self._ui_events.put(apply)
        threading.Thread(target=worker, daemon=True).start()

    def auto_refresh(self):
        self.refresh_buttons()
        if not self._stopped:
            self.after(3000, self.auto_refresh)


def ensure_admin() -> None:
    if os.name != "nt":
        return

    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass

    params = subprocess.list2cmdline(["-m", "pex", "ui"])
    shell_execute = ctypes.windll.shell32.ShellExecuteW
    shell_execute.restype = ctypes.c_void_p
    result = shell_execute(None, "runas", sys.executable, params, str(ROOT_PATH), 1) or 0
    if result <= 32:
        raise RuntimeError(f"Administrator launch failed or was cancelled (code {result}).")
    raise SystemExit(0)



def run() -> None:
    ensure_admin()

    if sys.platform == "win32":
        tcl_root = Path(sys.base_prefix) / "tcl"
        libraries = (
            ("TCL_LIBRARY", tcl_root / f"tcl{tk.TclVersion}", "init.tcl"),
            ("TK_LIBRARY", tcl_root / f"tk{tk.TkVersion}", "tk.tcl"),
        )
        for variable, directory, entry_file in libraries:
            if (directory / entry_file).is_file():
                os.environ.setdefault(variable, str(directory))

    app = PexApp()
    app.mainloop()


if __name__ == "__main__":
    run()
