from tkinter import scrolledtext
import tkinter as tk
import ctypes
import os
import pexconfig
import printer
import service
import sys


class PexApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.btn_install = None
        self.btn_uninstall = None
        self.btn_start = None
        self.btn_stop = None
        self.btn_restart = None
        self.btn_status = None
        self.output_text = None

        self.menubar = None
        self.settings_menu = None
        self.file_menu = None
        self.label_menu = None
        self.file_var = tk.StringVar(value=pexconfig.get_file_printer())
        self.label_var = tk.StringVar(value=pexconfig.get_label_printer())

        self.title("PEX - Printer Execution eXchange (0.1.0)")
        self.iconbitmap('icon.ico')
        self.setup_ui()
        self.create_menu()
        self.refresh_buttons()
        self.auto_refresh()

    def setup_ui(self):
        frame = tk.Frame(self)
        frame.pack(padx=20, pady=10)

        self.btn_install = tk.Button(frame, text="Install", width=12, command=lambda: self.exec(service.install))
        self.btn_install.grid(row=0, column=0, padx=5, pady=5)

        self.btn_uninstall = tk.Button(frame, text="Uninstall", width=12, command=lambda: self.exec(service.uninstall))
        self.btn_uninstall.grid(row=0, column=1, padx=5, pady=5)

        self.btn_start = tk.Button(frame, text="Start", width=12, command=lambda: self.exec(service.start))
        self.btn_start.grid(row=1, column=0, padx=5, pady=5)

        self.btn_stop = tk.Button(frame, text="Stop", width=12, command=lambda: self.exec(service.stop))
        self.btn_stop.grid(row=1, column=1, padx=5, pady=5)

        self.btn_restart = tk.Button(frame, text="Restart", width=12, command=lambda: self.exec(service.restart))
        self.btn_restart.grid(row=1, column=2, padx=5, pady=5)

        self.btn_status = tk.Button(frame, text="Status", width=12, command=lambda: self.exec(service.status))
        self.btn_status.grid(row=1, column=3, padx=5, pady=5)

        self.output_text = scrolledtext.ScrolledText(self, height=10, width=60, state='disabled')
        self.output_text.pack(padx=10, pady=10)

    def create_menu(self):
        self.menubar = tk.Menu(self)
        self.config(menu=self.menubar)

        self.settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Settings", menu=self.settings_menu)

        self.file_menu = tk.Menu(self.settings_menu, tearoff=0)
        self.label_menu = tk.Menu(self.settings_menu, tearoff=0)
        self.settings_menu.add_cascade(label="File Printer", menu=self.file_menu)
        self.settings_menu.add_cascade(label="Label Printer", menu=self.label_menu)

        self.refresh_printer_menus()

    def refresh_printer_menus(self):
        printers = printer.get_printers()
        self.file_var = tk.StringVar(value=pexconfig.get_file_printer())
        self.label_var = tk.StringVar(value=pexconfig.get_label_printer())

        # File-Printer
        self.file_menu.delete(0, tk.END)
        self.file_menu.add_radiobutton(
            label="None",
            variable=self.file_var,
            value="null",
            command=self.set_file_printer
        )
        for pr in printers:
            self.file_menu.add_radiobutton(
                label=pr,
                variable=self.file_var,
                value=pr,
                command=self.set_file_printer
            )

        # Label-Printer
        self.label_menu.delete(0, tk.END)
        self.label_menu.add_radiobutton(
            label="None",
            variable=self.label_var,
            value="null",
            command=self.set_label_printer
        )
        for pr in printers:
            self.label_menu.add_radiobutton(
                label=pr,
                variable=self.label_var,
                value=pr,
                command=self.set_label_printer
            )

    def set_file_printer(self):
        pexconfig.set_file_printer(self.file_var.get())

    def set_label_printer(self):
        pexconfig.set_label_printer(self.label_var.get())

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

    def exec(self, fn):
        result = fn()
        self.log(result)
        self.refresh_buttons()

    def refresh_buttons(self):
        installed = service.is_installed()
        running = service.is_running()

        self.btn_install.config(state='normal' if not installed else 'disabled')
        self.btn_uninstall.config(state='normal' if installed and not running else 'disabled')
        self.btn_start.config(state='normal' if installed and not running else 'disabled')
        self.btn_stop.config(state='normal' if installed and running else 'disabled')
        self.btn_restart.config(state='normal' if installed and running else 'disabled')
        self.btn_status.config(state='normal')

    def auto_refresh(self):
        self.refresh_buttons()
        self.after(3000, self.auto_refresh)


def ensure_admin():
    if os.name == "nt" and "--admin" in sys.argv and not ctypes.windll.shell32.IsUserAnAdmin():
        new_args = [arg for arg in sys.argv if arg != "--admin"]
        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, " ".join(['"{}"'.format(arg) for arg in new_args]), None, 1
        )
        sys.exit()


if __name__ == '__main__':
    ensure_admin()
    app = PexApp()
    app.mainloop()
