#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""汇总 A/B 偏好票；只看方向，不自动改参数。"""
import os
import sqlite3
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(os.path.dirname(HERE), "data", "tutor.sqlite")


def main():
    if not os.path.isfile(DB):
        print("还没有 votes 数据库。")
        return
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        rows = c.execute("SELECT * FROM preference_votes ORDER BY id").fetchall()
    except sqlite3.OperationalError:
        print("还没有 preference_votes 表；先跑一次 A/B。")
        return
    finally:
        c.close()
    if not rows:
        print("还没有偏好票。")
        return
    by_axis = defaultdict(list)
    for r in rows:
        by_axis[r["axis"] or "unknown"].append(r)
    for axis, items in sorted(by_axis.items()):
        choices = Counter(r["choice"] for r in items)
        current = variant = 0
        for r in items:
            if r["choice"] == "a":
                source = r["a_source"]
            elif r["choice"] == "b":
                source = r["b_source"]
            else:
                continue
            if source == "current":
                current += 1
            elif source == "less_intervention":
                variant += 1
        decided = current + variant
        rate = (current / decided * 100) if decided else 0
        print("方向：%s" % axis)
        print("  总票数：%d  A:%d  B:%d  都不喜欢:%d  差不多:%d" % (
            len(items), choices.get("a", 0), choices.get("b", 0),
            choices.get("neither", 0), choices.get("similar", 0)))
        print("  当前版胜：%d  实验版胜：%d  当前版胜率：%.1f%%" % (current, variant, rate))
        if len(items) < 10:
            print("  样本不足 10 票，先不改默认。")
        elif choices.get("similar", 0) >= len(items) / 2:
            print("  差不多占多数：暂停这个方向。")
        elif choices.get("neither", 0) >= len(items) / 2:
            print("  都不喜欢占多数：两个候选都淘汰。")
        elif rate >= 60:
            print("  结论：当前版更稳。")
        elif rate <= 40:
            print("  结论：实验版更稳。")
        else:
            print("  结论：方向不明显，继续收集。")
        print()


if __name__ == "__main__":
    main()
