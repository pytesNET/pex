"""Fast dialog positioning using Tk geometry only."""
import tkinter as tk


def place_window_near(
    master: tk.Tk | tk.Toplevel,
    win: tk.Toplevel,
    mode: str = "master",
    dx: int = 40,
    dy: int = 40,
    clamp_to_monitor: bool = True,
) -> None:
    """Position dialogs without launching external monitor-discovery processes.

    Use the virtual desktop bounds known to Tk. If those bounds do not include
    the parent's monitor, retain the parent-relative position instead of forcing
    the dialog onto the primary monitor.
    """
    win.update_idletasks()
    width, height = win.winfo_reqwidth(), win.winfo_reqheight()
    if mode == "cursor":
        anchor_x, anchor_y = win.winfo_pointerx(), win.winfo_pointery()
        x, y = anchor_x + dx, anchor_y + dy
    else:
        anchor_x = master.winfo_rootx() + master.winfo_width() // 2
        anchor_y = master.winfo_rooty() + master.winfo_height() // 2
        x, y = anchor_x - width // 2 + dx, anchor_y - height // 2 + dy
    if clamp_to_monitor:
        left, top = win.winfo_vrootx(), win.winfo_vrooty()
        right = left + (win.winfo_vrootwidth() or win.winfo_screenwidth())
        bottom = top + (win.winfo_vrootheight() or win.winfo_screenheight())
        if left <= anchor_x < right and top <= anchor_y < bottom:
            x = max(left, min(x, max(left, right - width)))
            y = max(top, min(y, max(top, bottom - height)))
    win.geometry(f"+{x}+{y}")
