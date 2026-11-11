#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学伴可调参数；改配置，不改代码。"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(os.path.dirname(HERE), "config", "companion.json")

DEFAULTS = {
    "chat": {"history_window": 8, "temperature": 0.4},
    "preference": {
        "every_turns": 4,
        "max_per_batch": 3,
        "variant_instruction": "这次只回应一句：先确认学生讲到的位置，不要追问，也不要解释。",
    },
}


def _merge(base, value):
    out = dict(base)
    for k, v in (value or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    return _merge(DEFAULTS, data if isinstance(data, dict) else {})
