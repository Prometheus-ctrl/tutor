#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：旧 tutor 数据 + 旧学习工作台结构 → app.db。

用法：
  python migrate.py --tutor
  python migrate.py --old-store path/to/store.json
  python migrate.py --schedule path/to/schedule.json
  python migrate.py --all --old-store ... --schedule ...
"""
import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys

import db

HERE = os.path.dirname(os.path.abspath(__file__))
TUTOR = os.path.dirname(HERE)
SAMPLES = os.path.join(TUTOR, "samples")

SUBJECT_DEFS = [
    ("math2", "数学二", "math2"),
    ("english2", "英语二", "english2"),
    ("politics", "政治", "politics"),
    ("cs408", "408", "cs408"),
]
SUBJECT_ALIASES = {
    "数二": "math2", "数学二": "math2", "数学": "math2",
    "英二": "english2", "英语二": "english2", "英语": "english2",
    "政治": "politics",
    "408": "cs408", "计算机": "cs408", "专业课": "cs408",
}


def ensure_subjects(c):
    now = db.now()
    for sid, name, code in SUBJECT_DEFS:
        c.execute(
            "INSERT INTO subjects(id,name,code,created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, code=excluded.code",
            (sid, name, code, now),
        )


def subject_for(title):
    t = str(title or "")
    for k, v in SUBJECT_ALIASES.items():
        if k in t:
            return v
    return "math2"


def upsert_paper(c, pid, plan_id, subject_id, title, source_dir):
    c.execute(
        "INSERT INTO papers(id,plan_id,subject_id,title,source_dir,created_at) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET plan_id=excluded.plan_id, subject_id=excluded.subject_id, "
        "title=excluded.title, source_dir=excluded.source_dir",
        (pid, plan_id, subject_id, title, source_dir, db.now()),
    )


def upsert_problem(c, p):
    c.execute(
        "INSERT INTO problems(id,paper_id,subject_id,type,parent_id,no,text,latex,image,bbox,options_json,crop,page,reference_answer,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET no=excluded.no, type=excluded.type, parent_id=excluded.parent_id, "
        "text=excluded.text, latex=excluded.latex, "
        "image=excluded.image, bbox=excluded.bbox, options_json=excluded.options_json, "
        "crop=excluded.crop, page=excluded.page, reference_answer=excluded.reference_answer",
        (
            p["id"], p["paper_id"], p["subject_id"], p.get("type", "single"),
            p.get("parent_id"), p.get("no"), p.get("text"), p.get("latex"),
            p.get("image"), p.get("bbox"), p.get("options_json"), p.get("crop"),
            p.get("page"), p.get("reference_answer"), p.get("status", "new"), db.now(),
        ),
    )


def import_samples(c, plan_id=None, subject_id="math2", only=None):
    if not os.path.isdir(SAMPLES):
        print("没有 samples 目录")
        return 0
    count = 0
    for name in sorted(os.listdir(SAMPLES)):
        d = os.path.join(SAMPLES, name)
        if not name.startswith("ingest-") or not os.path.isdir(d):
            continue
        if only and name not in only:
            continue
        result_path = os.path.join(d, "result.json")
        if not os.path.isfile(result_path):
            continue
        try:
            with open(result_path, encoding="utf-8") as f:
                result = json.load(f)
        except (OSError, ValueError):
            continue
        upsert_paper(c, name, plan_id, subject_id, name, os.path.relpath(d, TUTOR))
        for i, p in enumerate(result.get("problems") or []):
            rel = p.get("retake") or p.get("crop") or ("crops/p%02d.jpg" % (i + 1))
            upsert_problem(c, {
                "id": "%s:%d" % (name, i),
                "paper_id": name,
                "subject_id": subject_id,
                "type": p.get("type") or "single",
                "parent_id": p.get("parent_id"),
                "no": str(p.get("no") or (i + 1)),
                "text": p.get("text") or "",
                "latex": p.get("latex") or "",
                "image": os.path.join("samples", name, rel),
                "bbox": json.dumps(p.get("bbox"), ensure_ascii=False) if p.get("bbox") else None,
                "options_json": json.dumps(p.get("options") or [], ensure_ascii=False),
                "crop": p.get("crop"),
                "page": p.get("page"),
                "reference_answer": p.get("reference_answer"),
            })
            count += 1
            if plan_id:
                c.execute(
                    "INSERT OR IGNORE INTO plan_units(id,plan_id,paper_id,problem_id,status,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    ("u:%s:%d" % (name, i), plan_id, name, "%s:%d" % (name, i), "pending", db.now()),
                )
    return count


def import_reviews(c):
    path = os.path.join(TUTOR, "data", "reviews.json")
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return 0
    count = 0
    for item in data.get("reviews") or []:
        problem_id = item.get("id")
        fsrs = item.get("fsrs")
        if not problem_id or not isinstance(fsrs, dict):
            continue
        exists = c.execute("SELECT 1 FROM problems WHERE id=?", (problem_id,)).fetchone()
        if not exists:
            continue
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        c.execute(
            "INSERT INTO reviews(id,problem_id,fsrs_json,due,state,last_rating,user_summary,suggested,reason,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(problem_id) DO UPDATE SET fsrs_json=excluded.fsrs_json, due=excluded.due, "
            "state=excluded.state, last_rating=excluded.last_rating, user_summary=excluded.user_summary, "
            "suggested=excluded.suggested, reason=excluded.reason, updated_at=excluded.updated_at",
            (
                problem_id, problem_id, json.dumps(fsrs, ensure_ascii=False),
                fsrs.get("due"), fsrs.get("state_name"), item.get("last_rating"),
                summary.get("user"), summary.get("suggested"), summary.get("reason"),
                item.get("created") or db.now(), db.now(),
            ),
        )
        count += 1
    return count


def import_sessions(c):
    path = os.path.join(TUTOR, "data", "tutor.sqlite")
    if not os.path.isfile(path):
        return 0
    old = sqlite3.connect(path)
    old.row_factory = sqlite3.Row
    count = 0
    try:
        for s in old.execute("SELECT * FROM sessions").fetchall():
            problem_id = "%s:%d" % (s["paper"], s["problem_index"])
            exists = c.execute("SELECT 1 FROM problems WHERE id=?", (problem_id,)).fetchone()
            if not exists:
                continue
            c.execute(
                "INSERT INTO sessions(id,problem_id,paper_id,mode,model,started_at,ended_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING",
                (s["id"], problem_id, s["paper"], s["mode"], s["model"], s["created_at"], s["ended_at"]),
            )
            turns = old.execute("SELECT * FROM turns WHERE session_id=? ORDER BY id", (s["id"],)).fetchall()
            for t in turns:
                c.execute(
                    "INSERT INTO turns(session_id,role,content,speech,created_at) VALUES(?,?,?,?,?)",
                    (s["id"], t["role"], t["content"], t["speech"] or "", t["created_at"]),
                )
            count += 1
    finally:
        old.close()
    return count


def import_old_store(c, path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    store = raw.get("data") if isinstance(raw.get("data"), dict) else raw
    now = db.now()
    goals = tasks = plans = 0
    for old_task in store.get("tasks") or []:
        sid = subject_for(old_task.get("title"))
        gid = "g_" + str(old_task.get("id") or db.uid("g"))
        c.execute(
            "INSERT INTO goals(id,subject_id,title,external_id,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET subject_id=excluded.subject_id, title=excluded.title",
            (gid, sid, old_task.get("title") or "未命名目标", str(old_task.get("id") or ""), now),
        )
        goals += 1
        for old_problem in old_task.get("problems") or []:
            tid = "t_" + str(old_problem.get("id") or db.uid("t"))
            c.execute(
                "INSERT INTO tasks(id,goal_id,title,external_id,created_at) VALUES(?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET goal_id=excluded.goal_id, title=excluded.title",
                (tid, gid, old_problem.get("desc") or "未命名任务", str(old_problem.get("id") or ""), now),
            )
            tasks += 1
            for old_plan in old_problem.get("plans") or []:
                pid = "p_" + str(old_plan.get("id") or db.uid("p"))
                raw_name = old_plan.get("name") or old_plan.get("content") or "未命名计划"
                name = str(raw_name).splitlines()[0].strip()[:80] or "未命名计划"
                m = re.search(r"(19|20)\d{2}", name)
                c.execute(
                    "INSERT INTO plans(id,task_id,name,year,status,external_id,created_at) VALUES(?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET task_id=excluded.task_id, name=excluded.name, year=excluded.year",
                    (pid, tid, name, int(m.group(0)) if m else None, "active", str(old_plan.get("id") or ""), now),
                )
                plans += 1
    exam = store.get("exam") if isinstance(store.get("exam"), dict) else {}
    if exam.get("exam_date") or exam.get("date") or exam.get("label"):
        c.execute(
            "INSERT INTO exam_profile(id,label,exam_date,updated_at) VALUES(1,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET label=excluded.label, exam_date=excluded.exam_date, updated_at=excluded.updated_at",
            (exam.get("label") or "考研", exam.get("date") or exam.get("exam_date"), now),
        )
    return {"goals": goals, "tasks": tasks, "plans": plans}


def import_schedule(c, path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("events") if isinstance(data, dict) else data
    count = 0
    for e in events or []:
        eid = str(e.get("id") or db.uid("ev"))
        start = e.get("start_at") or e.get("start")
        if not start:
            continue
        c.execute(
            "INSERT INTO schedule_events(id,title,type,start_at,end_at,source,created_at) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, type=excluded.type, "
            "start_at=excluded.start_at, end_at=excluded.end_at",
            (eid, e.get("title") or "未命名", e.get("type") or "other", str(start),
             str(e.get("end_at") or e.get("end") or ""), path, db.now()),
        )
        count += 1
    return count


def seed_time_defaults(c):
    """固定课表 + 50h 周目标 + 80% 上限。"""
    now = db.now()
    classes = [
        ("class-mon-1", 1, 9 * 60 + 55, 11 * 60 + 20, "移动物联网 @松江 SB403"),
        ("class-mon-2", 1, 14 * 60 + 40, 16 * 60 + 5, "自然语言处理 @松江 信息楼332"),
        ("class-thu-1", 4, 9 * 60 + 55, 11 * 60 + 20, "商务智能综合实训 @松江 SD104"),
        ("class-thu-2", 4, 13 * 60, 14 * 60 + 25, "商务智能综合实训 @松江 SB506"),
        ("class-thu-3", 4, 14 * 60 + 40, 16 * 60 + 5, "人工智能伦理规范讲座 @松江 SB103"),
    ]
    for cid, wd, start, end, title in classes:
        c.execute(
            "INSERT INTO availability_template(id,weekday,start_min,end_min,title,type) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET weekday=excluded.weekday,start_min=excluded.start_min,"
            "end_min=excluded.end_min,title=excluded.title,type=excluded.type",
            (cid, wd, start, end, title, "class"),
        )
    settings = {
        "weekly_target_min": "3000",
        "buffer_pct": "20",
        "max_daily_pct": "80",
        "subjects_per_day": "3",
        "schedule_week": "fixed",
    }
    for k, v in settings.items():
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
    monday = dt.date.today() - dt.timedelta(days=dt.date.today().weekday())
    week = monday.isoformat()
    budgets = [("math2", 900), ("cs408", 1140), ("english2", 480), ("politics", 480)]
    for sid, minutes in budgets:
        c.execute(
            "INSERT INTO weekly_budgets(week,subject_id,planned_min,actual_min,locked) VALUES(?,?,?,0,1) "
            "ON CONFLICT(week,subject_id) DO UPDATE SET planned_min=excluded.planned_min",
            (week, sid, minutes),
        )
    return {"classes": len(classes), "week": week}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tutor", action="store_true", help="导入 samples/reviews/sessions")
    ap.add_argument("--old-store", help="旧工作台导出的 store.json")
    ap.add_argument("--schedule", help="时间表 JSON")
    ap.add_argument("--time", action="store_true", help="写入课表周模板和 50h 周预算")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    db.init()
    c = db.connect()
    try:
        ensure_subjects(c)
        if args.tutor or args.all:
            print("整卷/题目:", import_samples(c))
            print("复习卡:", import_reviews(c))
            print("旧会话:", import_sessions(c))
        if args.old_store:
            print("旧工作台:", import_old_store(c, args.old_store))
        if args.schedule:
            print("时间表:", import_schedule(c, args.schedule))
        if args.time or args.all:
            print("时间模板:", seed_time_defaults(c))
        c.commit()
        print(json.dumps(db.summary(), ensure_ascii=False, indent=2))
    finally:
        c.close()


if __name__ == "__main__":
    main()
