import re
import subprocess
import tkinter as tk


def place_window_near(
    master: tk.Tk | tk.Toplevel,
    win: tk.Toplevel,
    mode: str = "master",
    dx: int = 40,
    dy: int = 40,
    clamp_to_monitor: bool = True
):
    win.update_idletasks()
    width = win.winfo_reqwidth()
    height = win.winfo_reqheight()

    if mode == "cursor":
        x = win.winfo_pointerx() + dx
        y = win.winfo_pointery() + dy
    else:
        mx = master.winfo_rootx()
        my = master.winfo_rooty()
        mw = master.winfo_width() or master.winfo_reqwidth()
        mh = master.winfo_height() or master.winfo_reqheight()
        x = mx + (mw // 2) - (width // 2) + dx
        y = my + (mh // 2) - (height // 2) + dy

    ws = win.tk.call('tk', 'windowingsystem')
    if clamp_to_monitor:
        if ws == 'win32':
            try:
                _clamp_to_current_monitor_windows(win, width, height, x, y)
                return
            except Exception:
                pass
        elif ws == 'x11':
            try:
                _clamp_to_current_monitor_linux(win, width, height, x, y)
                return
            except Exception:
                pass

    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, min(x, sw - width))
    y = max(0, min(y, sh - height))
    win.geometry(f"+{x}+{y}")


def _clamp_to_current_monitor_windows(win: tk.Toplevel, w: int, h: int, x: int, y: int):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    MONITOR_DEFAULTTONEAREST = 2

    class Rect(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG), ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", Rect), ("rcWork", Rect), ("dwFlags", wintypes.DWORD)]

    px, py = win.winfo_pointerx(), win.winfo_pointery()
    monitor = user32.MonitorFromPoint(wintypes.POINT(px, py), MONITOR_DEFAULTTONEAREST)

    mi = MonitorInfo()
    mi.cbSize = ctypes.sizeof(MonitorInfo)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
        raise OSError("GetMonitorInfo failed")

    L = mi.rcWork.left
    T = mi.rcWork.top
    R = mi.rcWork.right
    B = mi.rcWork.bottom

    x = max(L, min(x, R - w))
    y = max(T, min(y, B - h))
    win.geometry(f"+{x}+{y}")


def _get_linux_monitors():
    try:
        res = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=1.5)
        if res.returncode != 0:
            raise RuntimeError(res.stderr or "xrandr failed")
        mons = []
        rx = re.compile(r"\bconnected\b.*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")
        for line in res.stdout.splitlines():
            if " connected" not in line:
                continue
            m = rx.search(line)
            if not m:
                continue
            w = int(m.group(1)); h = int(m.group(2))
            x = int(m.group(3)); y = int(m.group(4))
            mons.append((x, y, w, h))
        if not mons:
            raise RuntimeError("no monitors parsed")
        return mons
    except Exception as e:
        return None


def _clamp_to_current_monitor_linux(win: tk.Toplevel, w: int, h: int, x: int, y: int):
    mons = _get_linux_monitors()
    px, py = win.winfo_pointerx(), win.winfo_pointery()

    if not mons:
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        win.geometry(f"+{x}+{y}")
        return

    def contains(mon):
        mx, my, mw, mh = mon
        return (mx <= px < mx + mw) and (my <= py < my + mh)

    cur = None
    for mon in mons:
        if contains(mon):
            cur = mon
            break
    if cur is None:
        def dist2(mon):
            mx, my, mw, mh = mon
            cx = max(mx, min(px, mx + mw))
            cy = max(my, min(py, my + mh))
            return (cx - px) ** 2 + (cy - py) ** 2
        cur = min(mons, key=dist2)

    mx, my, mw, mh = cur
    x = max(mx, min(x, mx + mw - w))
    y = max(my, min(y, my + mh - h))
    win.geometry(f"+{x}+{y}")
