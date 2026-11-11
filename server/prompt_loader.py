#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 base + mode + subject + type 组合 Markdown prompt。"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(os.path.dirname(HERE), "prompts")

SAFE = re.compile(r"^[a-z0-9_]+$")


def _read(rel):
    stem = os.path.basename(rel)
    if stem.endswith(".md"):
        stem = stem[:-3]
    if not SAFE.match(stem):
        return ""
    path = os.path.join(ROOT, rel)
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _pick(kind, name):
    text = _read("%s/%s.md" % (kind, name))
    if text:
        return text
    return _read("%s/generic.md" % kind)


def compose(subject_id="math2", problem_type="single", mode="tutor"):
    """返回 system prompt；不把题目/学生输入拼进来。"""
    parts = [
        _read("base.md"),
        _read("modes/%s.md" % (mode if mode in ("tutor", "review", "exam", "gap_fill", "guide", "summary") else "tutor")),
        _pick("subjects", subject_id),
        _pick("types", problem_type),
    ]
    text = "\n\n".join(x for x in parts if x)
    if "【显示】" not in text or "【朗读】" not in text:
        raise RuntimeError("prompt 缺少【显示】/【朗读】格式段")
    return text


def status():
    out = {}
    for kind in ("subjects", "types", "modes"):
        d = os.path.join(ROOT, kind)
        if os.path.isdir(d):
            out[kind] = sorted(x[:-3] for x in os.listdir(d) if x.endswith(".md"))
    out["base"] = os.path.isfile(os.path.join(ROOT, "base.md"))
    return out


if __name__ == "__main__":
    print(status())
    print(compose())
