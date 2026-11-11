#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色回复规则校验器。"""
import re

MASTERY = ("已掌握", "已经掌握", "能力提升", "你学会了", "完全掌握", "进步很大")
ADVICE = ("你应该", "建议你", "改成", "换成", "记住这个", "背下来")


def questions(text):
    return str(text or "").count("？") + str(text or "").count("?")


def validate(role, text):
    t = str(text or "").strip()
    violations = []
    if not t:
        return ["empty"]
    if role == "gap_check":
        if questions(t):
            violations.append("gap_check_question")
        if any(k in t for k in ADVICE):
            violations.append("gap_check_advice")
    elif role == "gap_fill":
        if questions(t) > 1:
            violations.append("gap_fill_multi_question")
    elif role == "guide":
        if questions(t) > 1:
            violations.append("guide_multi_question")
        if any(k in t for k in ("完整解法", "答案是")):
            violations.append("guide_gives_answer")
    elif role == "summary":
        if questions(t):
            violations.append("summary_question")
        if any(k in t for k in MASTERY):
            violations.append("summary_mastery")
    elif role == "listening":
        if questions(t):
            violations.append("listening_question")
    return violations


def clean(role, text):
    """低风险清理；清理不了就返回空，由调用方兜底。"""
    t = str(text or "").strip()
    if role == "gap_check":
        # 查漏只保留陈述句，去掉问句
        parts = re.split(r"(?<=[。！!])\s*", t)
        t = " ".join(p for p in parts if not (p.endswith("？") or p.endswith("?")))
    if role == "summary":
        for k in MASTERY:
            t = t.replace(k, "")
    return t.strip()
