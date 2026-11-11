#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把每次外部 API 的用量追加到 tutor/data/usage.jsonl，用于估算花费。"""
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
PATH = os.path.join(DATA, "usage.jsonl")


def log(kind, model, provider="", seconds=None, chars=None, usage=None):
    try:
        os.makedirs(DATA, exist_ok=True)
        rec = {
            "ts": int(time.time()),
            "kind": str(kind),
            "model": str(model or ""),
            "provider": str(provider or ""),
        }
        if seconds:
            rec["seconds"] = round(float(seconds), 2)
        if chars:
            rec["chars"] = int(chars)
        if isinstance(usage, dict) and usage:
            keep = {}
            for k in ("prompt_tokens", "completion_tokens", "input_tokens", "output_tokens",
                      "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"):
                if usage.get(k) is not None:
                    keep[k] = usage.get(k)
            if keep:
                rec["usage"] = keep
        with open(PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
