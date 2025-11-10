import argparse
from typing import Callable
from .ui import app
from .config import get_option, set_option, delete_option
from .utils import coerce_values, SimpleFormatter
from .services import service
from .version import __VERSION__


def _wrap_noop(fn: Callable) -> int:
    fn()
    return 0


def _wrap_service(fn: Callable[[], tuple[bool, str]]) -> int:
    ok, msg = fn()
    print(msg)
    return 0 if ok else 1


def _cmd_help(_: argparse.Namespace) -> int:
    return _wrap_noop(build_parser().print_help)


def _cmd_install(_: argparse.Namespace) -> int:
    return _wrap_service(service.install)


def _cmd_uninstall(_: argparse.Namespace) -> int:
    return _wrap_service(service.uninstall)


def _cmd_status(_: argparse.Namespace) -> int:
    return _wrap_service(service.status)


def _cmd_start(_: argparse.Namespace) -> int:
    return _wrap_service(service.start)


def _cmd_restart(_: argparse.Namespace) -> int:
    return _wrap_service(service.restart)


def _cmd_stop(_: argparse.Namespace) -> int:
    return _wrap_service(service.stop)


def _cmd_ui(_: argparse.Namespace) -> int:
    return _wrap_noop(app.run)


def _cmd_update(args: argparse.Namespace) -> int:
    return 2


def _cmd_config(args: argparse.Namespace) -> int:
    key = args.option
    values = args.value

    # Delete option
    if args.delete:
        delete_option(key)
        print(f"{key} option has been deleted")
        return 0

    # Read option
    if len(values) == 0:
        print(get_option(key, default=None))
        return 0

    # Write option
    set_option(key, coerce_values(values))
    print(get_option(key, default=None))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pex",
        description="Printer Execution Service",
        epilog=(
            "Examples:\n"
            "  pex install\n"
            "  pex status\n"
            "  pex start\n"
            "  pex config server.port               # get value\n"
            "  pex config server.port 4123          # set value\n"
            "  pex restart\n"
            "  pex update\n"
        ),
        formatter_class=SimpleFormatter,
    )
    p.add_argument("--version", action="version", version=f"PEX - Printer Execution Service v{__VERSION__}")

    sub = p.add_subparsers(dest="cmd", title="Commands", required=True)
    sub.add_parser("help", help="Show this help message").set_defaults(func=_cmd_help)
    sub.add_parser("ui", help="Start the TK desktop UI").set_defaults(func=_cmd_ui)
    sub.add_parser("install", help="Install the printer service").set_defaults(func=_cmd_install)
    sub.add_parser("uninstall", help="Uninstall the printer service").set_defaults(func=_cmd_uninstall)
    sub.add_parser("status", help="Show printer service status").set_defaults(func=_cmd_status)
    sub.add_parser("start", help="Start the printer service").set_defaults(func=_cmd_start)
    sub.add_parser("restart", help="Restart the printer service").set_defaults(func=_cmd_restart)
    sub.add_parser("stop", help="Stop the printer service").set_defaults(func=_cmd_stop)
    sub.add_parser("update", help="Update PEX").set_defaults(func=_cmd_update)
    cmd = sub.add_parser(
        "config",
        help="Get or Set a config value",
        description=(
            "Get or set configuration values using dot-notation.\n\n"
            "Usage:\n"
            "  pex config KEY                       # read\n"
            "  pex config KEY VAL [...]             # write (scalars or list)\n"
            "  pex config --delete KEY              # delete\n"
            "Examples:\n"
            "  pex config server.port 4423\n"
            '  pex config formats.A11 18 26 "Tiny format"\n'
            "  pex config -d formats.A4             # delete\n"
        ),
        formatter_class=SimpleFormatter,
    )
    cmd.add_argument("-d", "--delete", action="store_true", help="Delete this configuration key explicitly")
    cmd.add_argument('option', metavar="KEY", help="Configuration key to read or write")
    cmd.add_argument('value', metavar="VALUE", help="New configuration value to set (omit to read)", nargs="*")
    cmd.set_defaults(func=_cmd_config)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        func = getattr(args, "func")
    except AttributeError:
        parser.print_help()
        return 2
    return int(func(args))
