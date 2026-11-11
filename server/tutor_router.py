#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""学生意图 → 教学角色调度器。"""
import re

ROLES = ("gap_check", "gap_fill", "guide", "summary")
LISTENING = "listening"

SIGNALS = {
    "summary": ("总结", "收尾", "差不多了", "结束本题", "收一下", "概括"),
    "gap_check": ("我讲完了", "讲完了", "检查", "有没有漏", "帮我看", "对一下", "复盘"),
    "guide": ("别直接", "别告诉", "问我", "引导", "下一步怎么想", "提示我"),
    "gap_fill": ("不懂", "不会", "补一下", "补缺", "解释", "为什么", "是什么", "怎么理解", "没学过"),
}


def route(text, history=None):
    t = str(text or "").strip()
    history = history or []
    if not t:
        return {"role": LISTENING, "confidence": 0.0, "reason": "empty"}
    for role in ("summary", "gap_check", "guide", "gap_fill"):
        for k in SIGNALS[role]:
            if k in t:
                return {"role": role, "confidence": 0.95, "reason": "signal:" + k}
    # 上一轮刚问完，学生正在回答 → 先听讲
    if history and (history[-1] or {}).get("role") == "assistant":
        last = str((history[-1] or {}).get("content") or "")
        if "？" in last or "?" in last:
            return {"role": LISTENING, "confidence": 0.7, "reason": "answering_question"}
    if "？" in t or "?" in t:
        return {"role": "gap_fill", "confidence": 0.55, "reason": "student_question"}
    return {"role": LISTENING, "confidence": 0.6, "reason": "explaining"}


def is_role(role):
    return role in ROLES


def is_listening(role):
    return role == LISTENING
