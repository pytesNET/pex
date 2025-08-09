import sys
from importlib import import_module

_impl_name = "service_windows" if sys.platform == "win32" else "service_linux"
_impl = import_module(_impl_name)


def _missing_tool(msg: str):
    return False, msg


def start(): return _impl.start()


def stop(): return _impl.stop()


def restart(): return _impl.restart()


def status(): return _impl.status()


def is_installed(): return _impl.is_installed()


def is_running(): return _impl.is_running()


def install(): return _impl.install()


def uninstall(): return _impl.uninstall()
