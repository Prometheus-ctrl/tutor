#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从一篇写作的初稿/当前稿/批改生成学习报告（原型）。

只报事实、证据和一个下一步；不打分、不判断掌握、不替用户写。
"""
import argparse
import difflib
import json
import re
import sqlite3
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "app.db")


def words(text):
    return len(re.findall(r"[A-Za-z]+(?:['-][A-Za-z]+)?", str(text or "")))


def sentences(text):
    parts = re.split(r"(?<=[.!?])(?:\s+|(?=[A-Z]))|\n+", str(text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def quote_present(quote, text):
    q = re.sub(r"\s+", " ", str(quote or "")).strip().lower()
    t = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    return bool(q) and q in t


def load_task(task_id, db=DB):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        row = c.execute("SELECT * FROM writing_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def load_revisions(task_id, db=DB):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    try:
        rows = c.execute(
            "SELECT rowid AS seq,kind,draft,feedback,created_at FROM writing_revisions "
            "WHERE writing_id=? ORDER BY created_at,rowid",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def build_report(task, revisions=None):
    if revisions is None:
        revisions = load_revisions(task.get("id"))
    first = (task.get("first_draft") or "").strip()
    current = (task.get("rewrite") or task.get("draft") or "").strip()
    part = "A" if str(task.get("id") or "").endswith(":A") else "B"
    target = 100 if part == "A" else 150
    threshold = 70 if part == "A" else 105
    fb = {}
    try:
        fb = json.loads(task.get("feedback") or "{}")
    except ValueError:
        fb = {}
    must = fb.get("must_fix") or fb.get("issues") or []
    optional = fb.get("optional") or []

    w1, w2 = words(first), words(current)
    s1, s2 = sentences(first), sentences(current)
    sm = difflib.SequenceMatcher(None, s1, s2)
    added = []
    changed = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            added.extend(s2[j1:j2])
        elif tag == "replace":
            changed.extend(s2[j1:j2])
        elif tag == "delete":
            changed.extend(s2[j1:j2])
    added = [x for x in added if x][:2]
    changed = [x for x in changed if x][:2]

    lines = []
    lines.append("# 写作修改报告")
    lines.append("")
    lines.append("## 事实")
    lines.append("")
    lines.append("- 初稿：约 %d 词，%d 句" % (w1, len(s1)))
    lines.append("- 当前稿：约 %d 词，%d 句" % (w2, len(s2)))
    lines.append("- 目标：约 %d 词（%s）" % (target, "Part A" if part == "A" else "Part B"))
    if w2 < threshold:
        lines.append("- 当前仍低于目标 70%%（%d 词）" % threshold)
    lines.append("")

    if revisions:
        grouped = []
        for r in revisions:
            if r.get("kind") == "feedback":
                try:
                    f = json.loads(r.get("feedback") or "{}")
                    probs = tuple(str(x.get("problem") or "") for x in (f.get("must_fix") or f.get("issues") or []))
                except ValueError:
                    probs = ()
                key = ("feedback", r.get("draft"), probs)
            else:
                key = (r.get("kind"), r.get("draft"), r.get("feedback"))
            if grouped and grouped[-1]["_key"] == key:
                grouped[-1]["_count"] += 1
            else:
                item = dict(r)
                item["_key"] = key
                item["_count"] = 1
                grouped.append(item)
        lines.append("## 修改时间线")
        lines.append("")
        prev_words = None
        for r in grouped[:8]:
            draft = str(r.get("draft") or "")
            n = words(draft)
            kind = {"save": "保存", "feedback": "批改", "final": "定稿"}.get(r.get("kind"), r.get("kind") or "事件")
            try:
                ts = datetime.fromtimestamp(int(r.get("created_at"))).strftime("%m-%d %H:%M")
            except (TypeError, ValueError, OSError):
                ts = "时间未知"
            delta = "" if prev_words is None else "，%+d 词" % (n - prev_words)
            repeat = "，重复 %d 次" % r["_count"] if r["_count"] > 1 else ""
            lines.append("- %s %s：%d 词%s%s" % (ts, kind, n, delta, repeat))
            if kind == "批改":
                try:
                    f = json.loads(r.get("feedback") or "{}")
                    problems = f.get("must_fix") or f.get("issues") or []
                    if problems:
                        lines.append("  - 硬伤：%s" % (problems[0].get("problem") or "")[:120])
                except ValueError:
                    pass
            prev_words = n
        lines.append("")

    lines.append("## 这次改了什么")
    lines.append("")
    if added:
        lines.append("新增/展开：")
        for x in added:
            lines.append("- “%s”" % x[:160])
    if changed:
        lines.append("替换/重写：")
        for x in changed:
            lines.append("- “%s”" % x[:160])
    if not added and not changed:
        lines.append("- 未检测到句子级新增或替换。")
    lines.append("")

    lines.append("## 为什么改（对应批改）")
    lines.append("")
    if must:
        for m in must:
            lines.append("- %s" % (m.get("problem") or "未命名硬伤"))
    else:
        lines.append("- 批改里没有 must_fix；这次变化可能是自主扩写或润色。")
    lines.append("")

    lines.append("## 改后是否解决")
    lines.append("")
    if not must:
        lines.append("- 没有待验证的硬伤。")
    else:
        for m in must:
            problem = str(m.get("problem") or "")
            quote = str(m.get("quote") or "")
            if "字数" in problem:
                ok = w2 >= threshold
                lines.append("- 字数：%s（当前 %d 词，门槛 %d 词）" % ("已达标" if ok else "仍未达标", w2, threshold))
            elif quote and quote_present(quote, current):
                if any(k in problem for k in ("没覆盖", "缺少", "遗漏", "未提到", "未给出")):
                    lines.append("- 缺失类问题：当前稿比初稿新增 %d 词；请对照题目确认是否补上（不自动判掌握）。" % (w2 - w1))
                else:
                    lines.append("- 仍能在当前稿找到原问题句：%s" % problem[:120])
            elif quote:
                lines.append("- 原问题句已不在当前稿：%s" % problem[:120])
            else:
                lines.append("- 无法自动核对：%s" % problem[:120])
    lines.append("")

    lines.append("## 重复模式")
    lines.append("")
    if revisions:
        lines.append("- 已有 %d 个版本快照，可以追踪本次修改；跨篇同类问题仍需累计。" % len(revisions))
    else:
        lines.append("- 当前只有初稿/当前稿，没有中间版本，不能判断这是第几次同类问题。")
    if "字数" in " ".join(str(m.get("problem") or "") for m in must):
        lines.append("- 这次的主要限制是篇幅，不是句子表达；先补内容，不要先背高级词。")
    lines.append("")

    lines.append("## 下一次只练什么")
    lines.append("")
    if must:
        m = must[0]
        action = str(m.get("action") or "").strip()
        lines.append("- %s" % (action or "只改这一处：%s" % (m.get("problem") or "")))
    elif optional:
        lines.append("- 没有必须改；可选润色不影响定稿。下一次换一道同类型题，检查同类问题是否复现。")
    else:
        lines.append("- 没有硬伤；下一次换题，保持同样的段落功能。")
    lines.append("")
    lines.append("> 报告只列事实和证据，不判断“已掌握/能力提升”；是否进步由你自己对照下一次写作判断。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("task_id")
    args = ap.parse_args()
    task = load_task(args.task_id)
    if not task:
        print("task not found", file=sys.stderr)
        return 1
    print(build_report(task))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
