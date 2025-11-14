import argparse
import json


class SimpleFormatter(argparse.ArgumentDefaultsHelpFormatter, argparse.RawDescriptionHelpFormatter):
    pass


def _coerce_token(s: str):
    try:
        if s.strip().lower() in ("true", "false", "null") or s[:1] in "[{\"" or s[:1].isdigit() or s[:2] in ("-1", "0 "):
            return json.loads(s)
    except Exception:
        pass
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def coerce_values(values):
    if len(values) == 0:
        return None
    if len(values) == 1:
        v = values[0]
        if isinstance(v, str) and v.lower() in ("none", "null"):
            return None
        return _coerce_token(v)
    return [_coerce_token(v) for v in values]


def deep_get(data, path, default=None):
    keys = path.split(".")
    current = data

    for k in keys:
        if isinstance(current, list) and k.isdigit():
            idx = int(k)
            if idx < 0 or idx >= len(current):
                return default
            current = current[idx]
        elif isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


def deep_set(data, path, value):
    keys = path.split(".")
    current = data

    for i, k in enumerate(keys[:-1]):
        if isinstance(current, list) and k.isdigit():
            k = int(k)
            if k >= len(current):
                current.extend([None] * (k - len(current) + 1))
            if current[k] is None:
                current[k] = {}
            current = current[k]
        else:
            if k not in current or not isinstance(current[k], (dict, list)):
                nxt = keys[i + 1]
                current[k] = [] if nxt.isdigit() else {}
            current = current[k]

    last = keys[-1]
    if isinstance(current, list) and last.isdigit():
        idx = int(last)
        if idx >= len(current):
            current.extend([None] * (idx - len(current) + 1))
        current[idx] = value
    else:
        current[last] = value
    return data


def deep_delete(data, path: str) -> bool:
    keys = path.split(".")
    current = data

    for k in keys[:-1]:
        if isinstance(current, list) and k.isdigit():
            idx = int(k)
            if idx < 0 or idx >= len(current):
                return False
            current = current[idx]
        elif isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return False

    last = keys[-1]
    if isinstance(current, list) and last.isdigit():
        idx = int(last)
        if 0 <= idx < len(current):
            del current[idx]
            return True
        return False
    if isinstance(current, dict) and last in current:
        del current[last]
        return True
    return False


def is_int(value):
    try:
        int(value)
        return True
    except (ValueError, TypeError):
        return False
