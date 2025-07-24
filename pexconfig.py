import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "pexconfig.json")

DEFAULT_CONFIG = {
    "label_printer": "null",
    "tag_printer": "null",
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


def get_label_printer():
    return load_config().get("label_printer", "")


def set_label_printer(name):
    config = load_config()
    config["label_printer"] = name
    save_config(config)


def get_price_printer():
    return load_config().get("tag_printer", "")


def set_price_printer(name):
    config = load_config()
    config["tag_printer"] = name
    save_config(config)
