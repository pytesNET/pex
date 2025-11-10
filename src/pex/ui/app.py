import ctypes
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext, ttk
from typing import Callable
from pex import config
from pex.services import service
from pex.version import __VERSION__


def resource_path(name: str) -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return str(base / name)


class PexApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self._last_installed = False
        self._last_running = False
        self._exec_inflight = False
        self._poll_inflight = False
        self._stopped = False

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

        self.title(f"PEX - Printer Execution Service ({__VERSION__})")
        self._set_icon()
        self.setup_ui()
        self.create_menu()
        self.auto_refresh()

    def destroy(self):
        self._stopped = True
        super().destroy()

    def _set_icon(self):
        if os.name == "nt":
            ico = resource_path("icon.ico")
            if os.path.exists(ico):
                try:
                    self.iconbitmap(ico)
                except tk.TclError:
                    pass
        for fname in ("icon.png", "icon.gif", "icon.xbm"):
            f = resource_path(fname)
            if os.path.exists(f):
                try:
                    self.iconphoto(True, tk.PhotoImage(file=f))
                    break
                except tk.TclError:
                    continue

    def setup_ui(self):
        frame = tk.Frame(self)
        frame.pack(padx=20, pady=10)

        shared = {"width": 14, "state": "disabled"}
        self.btn_install = ttk.Button(frame, text="Install", command=lambda: self.exec(service.install), **shared)
        self.btn_uninstall = ttk.Button(frame, text="Uninstall", command=lambda: self.exec(service.uninstall), **shared)
        self.btn_spooler = ttk.Button(frame, text="Restart Spooler", command=lambda: self.exec(self._cmd_restart_spooler), width=32, state="disabled")
        self.btn_update = ttk.Button(frame, text="Update PEX", command=lambda: self.exec(self._cmd_update), **shared)
        self.btn_start = ttk.Button(frame, text="Start", command=lambda: self.exec(service.start), **shared)
        self.btn_stop = ttk.Button(frame, text="Stop", command=lambda: self.exec(service.stop), **shared)
        self.btn_restart = ttk.Button(frame, text="Restart", command=lambda: self.exec(service.restart), **shared)
        self.btn_status = ttk.Button(frame, text="Status", command=lambda: self.exec(service.status), **shared)
        self.btn_exit = ttk.Button(frame, text="Exit PEX", command=self.quit, **shared)

        self.btn_install.grid(row=0, column=0, padx=5, pady=5)
        self.btn_uninstall.grid(row=0, column=1, padx=5, pady=5)
        self.btn_spooler.grid(row=0, column=2, columnspan=2, padx=5, pady=5)
        self.btn_update.grid(row=0, column=4, padx=5, pady=5)
        self.btn_start.grid(row=1, column=0, padx=5, pady=5)
        self.btn_stop.grid(row=1, column=1, padx=5, pady=5)
        self.btn_restart.grid(row=1, column=2, padx=5, pady=5)
        self.btn_status.grid(row=1, column=3, padx=5, pady=5)
        self.btn_exit.grid(row=1, column=4, padx=5, pady=5)

        self.output_text = scrolledtext.ScrolledText(self, height=10, width=60)
        self.output_text.pack(padx=10, pady=10)
        self.output_text.insert(tk.END, "[LOADING] Loading application, please wait...")
        self.output_text.config(state='disabled')

    def create_menu(self):
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)

        self.settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.linux_menu = tk.Menu(self.settings_menu, tearoff=0)

        self.menubar.add_cascade(label="Printers", command=self.open_printers_editor)
        self.menubar.add_cascade(label="Settings", menu=self.settings_menu)
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
        from pex.ui.printers_editor import PrintersEditor
        PrintersEditor(self)

    def _cmd_restart_spooler(self):
        script_name = "restart_spooler.bat"
        script_path = Path(__file__).resolve().parents[3] / "scripts" / script_name

        if not script_path.exists():
            return False, f"Script not found: {script_path}"

        self._exec_inflight = True
        self.log("Restarting Printer Spooler, please wait...")
        try:
            proc = subprocess.run(
                ["cmd", "/c", str(script_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            out = (proc.stdout or "").strip()
            err = (proc.stderr or "").strip()

            if proc.returncode == 0:
                return True, out or f"{script_name} executed successfully."
            else:
                msg = (out + ("\n" + err if err else "")).strip() or f"{script_name} failed (exit {proc.returncode})"
                return False, msg
        except subprocess.CalledProcessError as e:
            return False, e.output.strip()
        except subprocess.TimeoutExpired:
            return False, f"{script_name} timed out after 15 seconds".strip()
        except Exception as e:
            return False, str(e).strip()
        finally:
            self._exec_inflight = False

    def _cmd_update(self):
        self._exec_inflight = True
        self.log("Updating PEX, please wait...")

        logs = []
        success = True
        try:
            # Check current state
            try:
                installed = service.is_installed()
                running = service.is_running() if installed else False
            except Exception as e:
                installed, running = False, False
                logs.append(f"[ERROR] Could not read service status: {e}")

            # Stop service
            if installed and running:
                logs.append("[INFO] Stopping service...")
                status, msg = service.stop()
                if status:
                    logs.append(f"[SUCCESS] Service successfully stopped")
                else:
                    logs.append(f"[ERROR] {msg}")

            # Update
            logs.append("[INFO] Pulling latest changes from git...")
            try:
                res = subprocess.run(['git', 'pull'], capture_output=True, text=True, timeout=120)
                if res.stdout:
                    logs.append(res.stdout.strip())
                if res.stderr:
                    logs.append(res.stderr.strip())
                if res.returncode != 0:
                    success = False
                    logs.append(f"[ERROR] git pull failed with exit code {res.returncode}")
            except subprocess.TimeoutExpired:
                success = False
                logs.append("[ERROR] git pull timed out")

            # Start service
            if installed and running and success:
                logs.append("[INFO] Starting service...")
                status, msg = service.start()
                if status:
                    logs.append(f"[SUCCESS] Service successfully started")
                else:
                    logs.append(f"[ERROR] {msg}")

            # Return
            message = "\n".join(l for l in logs if l)
            return success, message
        except subprocess.CalledProcessError as e:
            return False, "\n".join(logs + [f"[EXCEPTION] {e.output.strip()}"])
        except Exception as e:
            return False, "\n".join(logs + [f"[EXCEPTION] {e}"])
        finally:
            self._exec_inflight = False

    def exec(self, fn: Callable):
        self._disable_buttons()

        def worker():
            try:
                result = fn()
            except Exception as e:
                result = False, str(e)
            self.after(0, lambda: (self.log(result), self.refresh_buttons()))
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

            self.after(0, apply)
        threading.Thread(target=worker, daemon=True).start()

    def auto_refresh(self):
        self.refresh_buttons()
        if not self._stopped:
            self.after(3000, self.auto_refresh)


def ensure_admin(force_admin: bool):
    if os.name != "nt" or not force_admin:
        return

    try:
        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:
        pass

    argv = [a for a in sys.argv[1:] if a != "--admin"]
    script = Path(sys.argv[0])
    if script.exists():
        params = subprocess.list2cmdline([str(script), *argv])
    else:
        params = subprocess.list2cmdline(["-m", "pex", *argv])

    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
    if ret <= 32:
        raise RuntimeError(f"Elevation failed with code {ret}")
    os.abort()


def run(force_admin: bool | None = None):
    force_admin = ("--admin" in sys.argv) if force_admin is None else force_admin
    ensure_admin(force_admin)
    app = PexApp()
    app.mainloop()


if __name__ == "__main__":
    run()
