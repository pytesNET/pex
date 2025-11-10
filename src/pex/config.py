import json
import os
from pathlib import Path
from .utils import deep_get, deep_set, deep_delete

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_FILE = (ROOT_DIR / "config.json")
DEFAULT_CONFIG_FILE = (ROOT_DIR / "_default_config.json")
LEGACY_CONFIG_FILE = (ROOT_DIR / "pexconfig.json")


def _default_config():
    config = {}
    if os.path.exists(DEFAULT_CONFIG_FILE):
        try:
            with open(DEFAULT_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}
    return config


def _migrate_config() -> bool:
    if not os.path.exists(LEGACY_CONFIG_FILE):
        return False

    try:
        new_config = _default_config()
        with open(LEGACY_CONFIG_FILE, "r", encoding="utf-8") as f:
            content = json.load(f)

        file_printer = content['file_printer'] or None
        file_printer = file_printer if isinstance(file_printer, str) and file_printer != "null" else None
        if file_printer:
            new_config['printers']['file'] = file_printer

        label_printer = content['label_printer'] or None
        label_printer = label_printer if isinstance(label_printer, str) and label_printer != "null" else None
        if label_printer:
            new_config['printers']['label'] = label_printer

        if file_printer or label_printer:
            new_config['printer_default'] = "file" if file_printer else "label"

        save_config(new_config)
        os.unlink(LEGACY_CONFIG_FILE)
        return True
    except Exception as e:
        print(f"Config migration failed: {e}")
        return False


def load_config():
    if os.path.exists(LEGACY_CONFIG_FILE):
        _migrate_config()

    if not os.path.exists(CONFIG_FILE):
        config = _default_config()
        save_config(config)
        return config
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_option(name: str, default=''):
    config = load_config()
    return deep_get(config, name, default)


def set_option(name: str, value):
    config = load_config()
    deep_set(config, name, value)
    save_config(config)


def delete_option(name: str):
    config = load_config()
    deep_delete(config, name)
    save_config(config)
