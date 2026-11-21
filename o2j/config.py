from __future__ import annotations

import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _expand(v):
    if isinstance(v, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: os.environ.get(m.group(1), ""), v) or None
    if isinstance(v, dict):
        return {k: _expand(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_expand(x) for x in v]
    return v


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out.get(k) or {}, v) if isinstance(v, dict) and isinstance(out.get(k), dict | None) else v
    return out


def apply_profile(s: dict, name: str | None) -> dict:
    name = name or s.get("profile")
    prof = (s.get("profiles") or {}).get(name)
    if not prof:
        return s
    out = _merge(s, prof)
    out["active_profile"] = name
    return out


def load_settings(path: Path | None = None, profile: str | None = None) -> dict:
    load_dotenv(ROOT / ".env")
    path = path or ROOT / "config" / "settings.yaml"
    s = _expand(yaml.safe_load(path.read_text(encoding="utf-8")))
    for k, v in s.get("paths", {}).items():
        s["paths"][k] = (ROOT / v) if v and not Path(v).is_absolute() else Path(v)
    return apply_profile(s, profile or os.environ.get("O2J_PROFILE"))
