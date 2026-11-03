"""Minimal YAML emitter (stdlib only) for the mihomo client configs.

Strings are always emitted double-quoted using JSON escaping, which YAML
accepts, so no value can be misread as a bool, number or YAML syntax.
"""
from __future__ import annotations

import json
import re

_BARE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _key(k: str) -> str:
    return k if _BARE_KEY.match(k) else json.dumps(k, ensure_ascii=False)


def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    return json.dumps(str(v), ensure_ascii=False)


def _emit(obj, indent: int, out: list[str]) -> None:
    pad = "  " * indent
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)) and v:
                out.append(f"{pad}{_key(k)}:")
                _emit(v, indent + 1, out)
            elif isinstance(v, (dict, list)):
                out.append(f"{pad}{_key(k)}: {'{}' if isinstance(v, dict) else '[]'}")
            else:
                out.append(f"{pad}{_key(k)}: {_scalar(v)}")
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, dict) and item:
                sub: list[str] = []
                _emit(item, indent + 1, sub)
                # First key goes on the "- " line.
                out.append(f"{pad}- {sub[0].lstrip()}")
                out.extend(sub[1:])
            elif isinstance(item, list) and item:
                out.append(f"{pad}-")
                _emit(item, indent + 1, out)
            else:
                out.append(f"{pad}- {_scalar(item)}")
    else:
        out.append(f"{pad}{_scalar(obj)}")


def dump(obj) -> str:
    out: list[str] = []
    _emit(obj, 0, out)
    return "\n".join(out) + "\n"
