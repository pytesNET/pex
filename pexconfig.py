import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pexconfig.json")

DEFAULT_CONFIG = {
    "file_printer": "null",
    "label_printer": "null",
    "linux_command": "-n",
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_file_printer():
    return load_config().get("file_printer", "")


def set_file_printer(name):
    config = load_config()
    config["file_printer"] = name
    save_config(config)


def get_label_printer():
    return load_config().get("label_printer", "")


def set_label_printer(name):
    config = load_config()
    config["label_printer"] = name
    save_config(config)


def get_linux_command():
    return load_config().get("linux_command", "-n")


def set_linux_command(name):
    config = load_config()
    config["linux_command"] = name
    save_config(config)
