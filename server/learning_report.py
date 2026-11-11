#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日学习报告：聚合事实、生成 Markdown、可选秘书润色、存档。"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
REPORTS = os.path.join(DATA, "reports")
sys.path.insert(0, HERE)
import db  # noqa: E402


def _day_range(date):
    dt = datetime.strptime(date, "%Y-%m-%d")
    start = int(dt.timestamp())
    return start, start + 86400


def _subjects(c, start, end):
    rows = c.execute(
        "SELECT COALESCE(p.subject_id, 'unknown') AS subject, "
        "COUNT(DISTINCT s.id) AS sessions, COUNT(t.id) AS turns "
        "FROM sessions s LEFT JOIN papers p ON p.id=s.paper_id "
        "LEFT JOIN turns t ON t.session_id=s.id "
        "WHERE s.started_at>=? AND s.started_at<? GROUP BY subject ORDER BY sessions DESC",
        (start, end),
    ).fetchall()
    return [dict(r) for r in rows]


def collect(date):
    start, end = _day_range(date)
    c = db.connect()
    try:
        subjects = _subjects(c, start, end)
        sessions = c.execute(
            "SELECT COUNT(*) FROM sessions WHERE started_at>=? AND started_at<?", (start, end)
        ).fetchone()[0]
        turns = c.execute(
            "SELECT COUNT(*) FROM turns t JOIN sessions s ON s.id=t.session_id "
            "WHERE s.started_at>=? AND s.started_at<?", (start, end)
        ).fetchone()[0]
        finished = c.execute(
            "SELECT COUNT(*) FROM problem_progress WHERE first_finished_at>=? AND first_finished_at<?",
            (start, end),
        ).fetchone()[0]
        ratings = c.execute(
            "SELECT COALESCE(last_rating,'-') AS rating, COUNT(*) AS n FROM reviews "
            "WHERE updated_at>=? AND updated_at<? GROUP BY rating", (start, end)
        ).fetchall()
        writing = c.execute(
            "SELECT id,status,final_at FROM writing_tasks "
            "WHERE updated_at>=? OR final_at>=? ORDER BY updated_at", (start, end)
        ).fetchall()
        minutes = c.execute(
            "SELECT COALESCE(SUM(q.actual_min),0) FROM queue_items q "
            "JOIN daily_plans d ON d.id=q.daily_plan_id WHERE d.date=?", (date,)
        ).fetchone()[0]
        return {
            "date": date,
            "sessions": sessions,
            "turns": turns,
            "minutes": int(minutes or 0),
            "finished": finished,
            "subjects": subjects,
            "ratings": [dict(r) for r in ratings],
            "writing": [dict(r) for r in writing],
        }
    finally:
        c.close()


SUBJECT_NAMES = {"math2": "数二", "english2": "英二", "cs408": "408", "unknown": "未分类"}


def build_raw(facts):
    lines = ["# %s 学习记录" % facts["date"], "", "## 概览", ""]
    lines.append("- 讲题会话：%d 个" % facts["sessions"])
    lines.append("- 对话消息：%d 条" % facts["turns"])
    lines.append("- 完成题目：%d 道" % facts["finished"])
    lines.append("- 有效学习时间：%d 分钟" % facts["minutes"])
    lines.append("")
    lines.append("## 分科")
    lines.append("")
    if facts["subjects"]:
        for s in facts["subjects"]:
            name = SUBJECT_NAMES.get(s["subject"], s["subject"])
            lines.append("- %s：%d 个会话，%d 条消息" % (name, s["sessions"], s["turns"]))
    else:
        lines.append("- 当天没有讲题会话。")
    lines.append("")
    lines.append("## 评级记录")
    lines.append("")
    if facts["ratings"]:
        for r in facts["ratings"]:
            lines.append("- %s：%d 次" % (r["rating"], r["n"]))
    else:
        lines.append("- 当天没有评级记录。")
    lines.append("")
    lines.append("## 写作")
    lines.append("")
    if facts["writing"]:
        for w in facts["writing"]:
            lines.append("- `%s`：%s" % (w["id"], w["status"]))
    else:
        lines.append("- 当天没有写作更新。")
    lines.append("")
    return "\n".join(lines)


def polish(raw, facts, model=None):
    """秘书口吻的简报：只使用给定事实，不编造、不判断掌握。"""
    try:
        import speech
        prompt = (
            "你是学习助理，负责把老板当天的学习记录整理成一页简报。\n"
            "只使用给定事实，不要编造，不要判断“掌握/能力提升”，不要打分。\n"
            "不要出现内部 ID、JSON 字段名、null、状态码；用中文描述。\n"
            "输出 Markdown，结构：\n"
            "# 今日学习简报\n"
            "## 今天做了什么\n"
            "## 值得注意\n"
            "## 明天从哪开始\n"
            "语言简洁、像秘书汇报，不奉承。\n\n"
            "【事实】\n" + json.dumps(facts, ensure_ascii=False)[:5000] +
            "\n\n【原始记录】\n" + raw[:5000]
        )
        data, provider, name = speech.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.2, model=model)
        choices = data.get("choices") or []
        text = ((choices[0].get("message") or {}).get("content") or "").strip() if choices else ""
        text = re.sub(r"^```(?:markdown)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
        return text or raw
    except Exception:
        return raw


def save(date, facts, raw, final):
    os.makedirs(REPORTS, exist_ok=True)
    path = os.path.join(REPORTS, date + ".md")
    raw_path = os.path.join(REPORTS, date + ".raw.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(final)
    with open(raw_path, "w", encoding="utf-8") as f:
        f.write(raw)
    return path


def generate(date, model=None, with_polish=True):
    facts = collect(date)
    raw = build_raw(facts)
    final = polish(raw, facts, model=model) if with_polish else raw
    path = save(date, facts, raw, final)
    return {"date": date, "path": path, "facts": facts, "raw": raw, "report": final}


def load(date):
    path = os.path.join(REPORTS, date + ".md")
    raw_path = os.path.join(REPORTS, date + ".raw.md")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        report = f.read()
    raw = ""
    if os.path.isfile(raw_path):
        with open(raw_path, encoding="utf-8") as f:
            raw = f.read()
    return {"date": date, "report": report, "raw": raw}


def list_reports(limit=30):
    if not os.path.isdir(REPORTS):
        return []
    names = [n[:-3] for n in os.listdir(REPORTS) if re.match(r"^\d{4}-\d{2}-\d{2}\.md$", n)]
    return sorted(names, reverse=True)[:limit]


def ensure_yesterday(model=None):
    y = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    if os.path.isfile(os.path.join(REPORTS, y + ".md")):
        return None
    return generate(y, model=model)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?")
    ap.add_argument("--raw", action="store_true")
    args = ap.parse_args()
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    r = generate(date, with_polish=not args.raw)
    print(r["path"])
    print(r["report"][:1200])


if __name__ == "__main__":
    main()
