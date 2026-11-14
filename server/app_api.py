#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三环只读/计划 API：计划树、当前到期、今日科目分配。"""
import datetime as dt
import json
import math
import re
import uuid

import db

SUBJECT_ORDER = ["math2", "english2", "politics", "cs408"]
DEFAULT_BUDGET = {"math2": 900, "cs408": 1140, "english2": 480, "politics": 480}
NEW_EST = {"math2": 25, "cs408": 25, "english2": 35, "politics": 2}
REVIEW_MIN = 8


def _now_iso():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _today():
    return dt.date.today().isoformat()


def _week_start(day=None):
    d = dt.date.fromisoformat(day) if day else dt.date.today()
    return (d - dt.timedelta(days=d.weekday())).isoformat()


def _conn():
    return db.connect()


def _subject_names(c):
    return {r["id"]: r["name"] for r in c.execute("SELECT id,name FROM subjects").fetchall()}


def _due_rows(c, subject_id=None):
    now = _now_iso()
    sql = (
        "SELECT r.id AS review_id, r.due, r.fsrs_json, p.id AS problem_id, p.no, p.text, "
        "p.paper_id, p.subject_id, x.title AS paper_title, pl.id AS plan_id, pl.name AS plan_name, "
        "t.id AS task_id, t.title AS task_title, g.id AS goal_id, g.title AS goal_title "
        "FROM reviews r JOIN problems p ON p.id=r.problem_id "
        "JOIN papers x ON x.id=p.paper_id "
        "LEFT JOIN plans pl ON pl.id=x.plan_id "
        "LEFT JOIN tasks t ON t.id=pl.task_id "
        "LEFT JOIN goals g ON g.id=t.goal_id "
        "WHERE r.due <= ?"
    )
    args = [now]
    if subject_id:
        sql += " AND p.subject_id=?"
        args.append(subject_id)
    sql += " ORDER BY r.due ASC"
    return c.execute(sql, args).fetchall()


def _counts(c, subject_id):
    now = _now_iso()
    plans = c.execute(
        "SELECT COUNT(*) FROM plans pl JOIN tasks t ON t.id=pl.task_id JOIN goals g ON g.id=t.goal_id WHERE g.subject_id=?",
        (subject_id,),
    ).fetchone()[0]
    papers = c.execute("SELECT COUNT(*) FROM papers WHERE subject_id=?", (subject_id,)).fetchone()[0]
    problems = c.execute("SELECT COUNT(*) FROM problems WHERE subject_id=?", (subject_id,)).fetchone()[0]
    due = c.execute(
        "SELECT COUNT(*) FROM reviews r JOIN problems p ON p.id=r.problem_id WHERE p.subject_id=? AND r.due<=?",
        (subject_id, now),
    ).fetchone()[0]
    finished = c.execute(
        "SELECT COUNT(DISTINCT r.problem_id) FROM reviews r JOIN problems p ON p.id=r.problem_id WHERE p.subject_id=?",
        (subject_id,),
    ).fetchone()[0]
    return {
        "plans": plans,
        "papers": papers,
        "problems": problems,
        "due": due,
        "finished": finished,
        "untouched": max(0, problems - finished),
    }


def overview():
    c = _conn()
    try:
        names = _subject_names(c)
        subjects = []
        for sid in SUBJECT_ORDER:
            if sid not in names:
                continue
            row = {"id": sid, "name": names[sid]}
            row.update(_counts(c, sid))
            subjects.append(row)
        for sid, name in names.items():
            if sid not in SUBJECT_ORDER:
                row = {"id": sid, "name": name}
                row.update(_counts(c, sid))
                subjects.append(row)
        due = _due_rows(c)
        week = _week_start()
        budgets = [
            dict(r) for r in c.execute(
                "SELECT w.subject_id, w.planned_min, w.actual_min, s.name FROM weekly_budgets w "
                "JOIN subjects s ON s.id=w.subject_id WHERE w.week=? ORDER BY w.subject_id",
                (week,),
            ).fetchall()
        ]
        exam = c.execute("SELECT label,exam_date FROM exam_profile WHERE id=1").fetchone()
        daily = c.execute("SELECT * FROM daily_plans WHERE date=?", (_today(),)).fetchone()
        unassigned = c.execute("SELECT COUNT(*) FROM papers WHERE plan_id IS NULL").fetchone()[0]
        return {
            "ok": True,
            "today": _today(),
            "week": week,
            "exam": dict(exam) if exam else {"label": "考研", "exam_date": "2026-12-19"},
            "subjects": subjects,
            "due": [_due_json(r) for r in due],
            "weekly": budgets,
            "daily": dict(daily) if daily else None,
            "unassignedPapers": unassigned,
        }
    finally:
        c.close()


def _due_json(r):
    d = dict(r)
    d.pop("fsrs_json", None)
    return d


def ensure_writing_units(c):
    """把已分配到计划的写作任务同步成计划单元。"""
    for r in c.execute(
        "SELECT id,plan_id,status FROM writing_tasks WHERE plan_id IS NOT NULL"
    ).fetchall():
        uid = "wu_" + r["id"]
        c.execute(
            "INSERT OR IGNORE INTO writing_plan_units(id,plan_id,writing_id,status,created_at) "
            "VALUES(?,?,?,?,?)",
            (uid, r["plan_id"], r["id"], "finished" if r["status"] == "final" else "pending", db.now()),
        )
        c.execute(
            "UPDATE writing_plan_units SET status=? WHERE writing_id=?",
            ("finished" if r["status"] == "final" else "pending", r["id"]),
        )


def _plan_phase(c, plan):
    if (plan["status"] or "") == "archived":
        return "archived"
    total = c.execute(
        "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=?) + "
        "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=?)",
        (plan["id"], plan["id"]),
    ).fetchone()[0]
    done = c.execute(
        "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=? AND status='finished') + "
        "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=? AND status='finished')",
        (plan["id"], plan["id"]),
    ).fetchone()[0]
    touched = c.execute(
        "SELECT COUNT(*) FROM problems x JOIN papers p ON p.id=x.paper_id "
        "WHERE p.plan_id=? AND x.status<>'new'",
        (plan["id"],),
    ).fetchone()[0]
    if total and done >= total:
        return "first_done"
    if done or touched:
        return "in_progress"
    return "not_started"


PHASE_LABELS = {
    "not_started": "未开始",
    "in_progress": "进行中",
    "first_done": "第一遍完成",
    "archived": "已归档",
}


LAST_POSITION_KEY = "last_positions"


def save_last_position(paper_id, index):
    """记住“最近打开的题目”（按计划分开存），给计划页的「下一题」用。"""
    c = _conn()
    try:
        row = c.execute("SELECT plan_id FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not row or not row["plan_id"]:
            return False
        try:
            raw = c.execute("SELECT value FROM settings WHERE key=?", (LAST_POSITION_KEY,)).fetchone()
            data = json.loads(raw["value"]) if raw else {}
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[row["plan_id"]] = {"paper": paper_id, "index": int(index or 0), "at": _now_iso()}
        c.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (LAST_POSITION_KEY, json.dumps(data, ensure_ascii=False)),
        )
        c.commit()
        return True
    finally:
        c.close()


def _last_position(c, plan_id):
    try:
        row = c.execute("SELECT value FROM settings WHERE key=?", (LAST_POSITION_KEY,)).fetchone()
        data = json.loads(row["value"]) if row else {}
        pos = data.get(plan_id) if isinstance(data, dict) else None
        return pos if isinstance(pos, dict) else None
    except Exception:
        return None


def next_problem(plan_id):
    """当前计划下一题：到期复习优先；否则从最近打开的卷继续；再否则按年份取未完成。"""
    c = _conn()
    try:
        now = _now_iso()
        chosen = None
        # 1) 计划内到期复习题优先
        due = c.execute(
            "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
            "FROM problems x JOIN papers p ON p.id=x.paper_id "
            "JOIN reviews r ON r.problem_id=x.id "
            "WHERE p.plan_id=? AND r.due IS NOT NULL AND r.due<=? "
            "ORDER BY r.due LIMIT 1",
            (plan_id, now),
        ).fetchone()
        if due:
            chosen = {"id": due["id"], "paper_id": due["paper_id"], "no": due["no"],
                      "paper_title": due["paper_title"]}
        # 2) 最近打开的卷：从那个位置往后找第一道未完成
        if not chosen:
            pos = _last_position(c, plan_id)
            if pos and pos.get("paper"):
                prow = c.execute(
                    "SELECT id, title FROM papers WHERE id=? AND plan_id=?",
                    (pos["paper"], plan_id),
                ).fetchone()
                if prow:
                    prs = c.execute(
                        "SELECT x.id, x.no, COALESCE(u.status, 'pending') AS unit_status "
                        "FROM problems x LEFT JOIN plan_units u ON u.problem_id=x.id "
                        "WHERE x.paper_id=? ORDER BY x.rowid",
                        (pos["paper"],),
                    ).fetchall()
                    start = min(max(int(pos.get("index") or 0), 0), max(0, len(prs) - 1))
                    pick = None
                    # 先看当前位置这道题：没做完就是“继续这题”
                    if prs and (prs[start]["unit_status"] or "pending") != "finished":
                        pick = prs[start]
                    if not pick:
                        for r in prs[start + 1:]:
                            if (r["unit_status"] or "pending") != "finished":
                                pick = r
                                break
                    if not pick:
                        for r in prs[:start]:
                            if (r["unit_status"] or "pending") != "finished":
                                pick = r
                                break
                    if pick:
                        chosen = {"id": pick["id"], "paper_id": pos["paper"], "no": pick["no"],
                                  "paper_title": prow["title"]}
        # 3) 兜底：按年份顺序第一道未完成
        if not chosen:
            pending = c.execute(
                "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "LEFT JOIN plan_units u ON u.problem_id=x.id "
                "WHERE p.plan_id=? AND COALESCE(u.status, 'pending')!='finished' "
                "ORDER BY COALESCE(CAST(substr(p.title,1,4) AS INTEGER),9999), p.created_at, x.rowid "
                "LIMIT 1",
                (plan_id,),
            ).fetchone()
            if pending:
                chosen = {"id": pending["id"], "paper_id": pending["paper_id"], "no": pending["no"],
                          "paper_title": pending["paper_title"]}
        if not chosen:
            return None
        paper_rows = c.execute(
            "SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (chosen["paper_id"],)
        ).fetchall()
        index = next((i for i, r in enumerate(paper_rows) if r["id"] == chosen["id"]), 0)
        return {
            "paper": chosen["paper_id"],
            "index": index,
            "problem_id": chosen["id"],
            "no": chosen["no"],
            "paper_title": chosen["paper_title"] or "",
        }
    finally:
        c.close()


def next_in_paper(paper_id, index, skip_finished=True):
    """本卷下一题（顺序，默认跳过已完成）；到卷尾返回 None。"""
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return None
        rows = c.execute(
            "SELECT x.id, x.no, COALESCE(u.status, 'pending') AS unit_status "
            "FROM problems x LEFT JOIN plan_units u ON u.problem_id=x.id "
            "WHERE x.paper_id=? ORDER BY x.rowid",
            (paper_id,),
        ).fetchall()
        if not rows or int(index) < 0 or int(index) >= len(rows):
            return None
        for i in range(int(index) + 1, len(rows)):
            r = rows[i]
            if skip_finished and (r["unit_status"] or "pending") == "finished":
                continue
            return {
                "paper": paper_id,
                "index": i,
                "problem_id": r["id"],
                "no": r["no"],
                "paper_title": paper["title"] or "",
            }
        return None
    finally:
        c.close()


def next_from_problem(paper_id, index):
    """讲题页的下一题：计划内有到期复习题就先去复习；否则只走本卷下一题。"""
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return None
        rows = c.execute(
            "SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (paper_id,)
        ).fetchall()
        if not rows or int(index) < 0 or int(index) >= len(rows):
            return None
        current_id = rows[int(index)]["id"]
        if paper["plan_id"]:
            now = _now_iso()
            due = c.execute(
                "SELECT x.id, x.paper_id, x.no, r.due, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "JOIN reviews r ON r.problem_id=x.id "
                "WHERE p.plan_id=? AND x.id<>? AND r.due IS NOT NULL AND r.due<=? "
                "ORDER BY r.due LIMIT 1",
                (paper["plan_id"], current_id, now),
            ).fetchone()
            if due:
                paper_rows = c.execute(
                    "SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (due["paper_id"],)
                ).fetchall()
                pidx = next((i for i, r in enumerate(paper_rows) if r["id"] == due["id"]), 0)
                return {
                    "paper": due["paper_id"],
                    "index": pidx,
                    "problem_id": due["id"],
                    "no": due["no"],
                    "paper_title": due["paper_title"] or "",
                }
        return next_in_paper(paper_id, index)
    finally:
        c.close()


def next_after(paper_id, index):
    """按整卷顺序找当前题的下一题；最后一题返回 None。"""
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return None
        if paper["plan_id"]:
            rows = c.execute(
                "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "WHERE p.plan_id=? "
                "ORDER BY COALESCE(CAST(substr(p.title,1,4) AS INTEGER),9999), p.created_at, x.rowid",
                (paper["plan_id"],),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "WHERE x.paper_id=? ORDER BY x.rowid",
                (paper_id,),
            ).fetchall()
        current = None
        for i, r in enumerate(rows):
            if r["paper_id"] == paper_id:
                prs = c.execute("SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (paper_id,)).fetchall()
                pos = next((j for j, p in enumerate(prs) if p["id"] == r["id"]), None)
                if pos == int(index):
                    current = i
                    break
        if current is None or current + 1 >= len(rows):
            return None
        nxt = rows[current + 1]
        prs = c.execute("SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (nxt["paper_id"],)).fetchall()
        nidx = next((j for j, p in enumerate(prs) if p["id"] == nxt["id"]), 0)
        return {"paper": nxt["paper_id"], "index": nidx, "problem_id": nxt["id"],
                "no": nxt["no"], "paper_title": nxt["paper_title"] or ""}
    finally:
        c.close()


def previous_before(paper_id, index):
    """按整卷顺序找当前题的上一题；第一题返回 None。"""
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return None
        if paper["plan_id"]:
            rows = c.execute(
                "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "WHERE p.plan_id=? "
                "ORDER BY COALESCE(CAST(substr(p.title,1,4) AS INTEGER),9999), p.created_at, x.rowid",
                (paper["plan_id"],),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT x.id, x.paper_id, x.no, p.title AS paper_title "
                "FROM problems x JOIN papers p ON p.id=x.paper_id "
                "WHERE x.paper_id=? ORDER BY x.rowid",
                (paper_id,),
            ).fetchall()
        current = None
        for i, r in enumerate(rows):
            if r["paper_id"] == paper_id:
                prs = c.execute("SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (paper_id,)).fetchall()
                pos = next((j for j, p in enumerate(prs) if p["id"] == r["id"]), None)
                if pos == int(index):
                    current = i
                    break
        if current is None or current - 1 < 0:
            return None
        prev = rows[current - 1]
        prs = c.execute("SELECT id FROM problems WHERE paper_id=? ORDER BY rowid", (prev["paper_id"],)).fetchall()
        pidx = next((j for j, p in enumerate(prs) if p["id"] == prev["id"]), 0)
        return {"paper": prev["paper_id"], "index": pidx, "problem_id": prev["id"],
                "no": prev["no"], "paper_title": prev["paper_title"] or ""}
    finally:
        c.close()


def plans_tree():
    c = _conn()
    try:
        ensure_writing_units(c)
        c.commit()
        names = _subject_names(c)
        goals = []
        for g in c.execute("SELECT * FROM goals ORDER BY created_at,id").fetchall():
            tasks = []
            for t in c.execute("SELECT * FROM tasks WHERE goal_id=? ORDER BY created_at,id", (g["id"],)).fetchall():
                plans = []
                for p in c.execute("SELECT * FROM plans WHERE task_id=? ORDER BY year,name", (t["id"],)).fetchall():
                    papers = [_paper_json(c, x) for x in c.execute(
                        "SELECT * FROM papers WHERE plan_id=? "
                        "ORDER BY COALESCE(CAST(substr(title,1,4) AS INTEGER),9999), created_at",
                        (p["id"],)
                    ).fetchall()]
                    plans.append({
                        "id": p["id"], "name": p["name"], "year": p["year"],
                        "subject_id": g["subject_id"],
                        "status": p["status"], "papers": papers,
                        "phase": _plan_phase(c, p),
                        "phase_label": PHASE_LABELS.get(_plan_phase(c, p), ""),
                        "next": next_problem(p["id"]),
                        "due": sum(x["due"] for x in papers),
                        "problems": sum(x["problems"] for x in papers),
                        "finished": sum(x["finished"] for x in papers),
                        "units": c.execute(
                            "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=?) + "
                            "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=?)",
                            (p["id"], p["id"]),
                        ).fetchone()[0],
                        "units_done": c.execute(
                            "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=? AND status='finished') + "
                            "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=? AND status='finished')",
                            (p["id"], p["id"]),
                        ).fetchone()[0],
                        "writing": c.execute("SELECT COUNT(*) FROM writing_tasks WHERE plan_id=?", (p["id"],)).fetchone()[0],
                        "active": t["active_plan_id"] == p["id"],
                    })
                    plans[-1]["units_left"] = max(0, plans[-1]["units"] - plans[-1]["units_done"])
                tasks.append({"id": t["id"], "title": t["title"], "plans": plans,
                              "active_plan_id": t["active_plan_id"],
                              "due": sum(x["due"] for x in plans)})
            goals.append({"id": g["id"], "title": g["title"], "subject_id": g["subject_id"],
                          "subject": names.get(g["subject_id"], ""),
                          "tasks": tasks, "due": sum(x["due"] for x in tasks)})
        unassigned = []
        for x in c.execute("SELECT * FROM papers WHERE plan_id IS NULL ORDER BY created_at").fetchall():
            unassigned.append(_paper_json(c, x))
        return {"ok": True, "goals": goals, "unassigned": unassigned}
    finally:
        c.close()


def _paper_json(c, p):
    now = _now_iso()
    problems = c.execute("SELECT COUNT(*) FROM problems WHERE paper_id=?", (p["id"],)).fetchone()[0]
    due = c.execute(
        "SELECT COUNT(*) FROM reviews r JOIN problems x ON x.id=r.problem_id "
        "WHERE x.paper_id=? AND r.due<=?", (p["id"], now),
    ).fetchone()[0]
    finished = c.execute(
        "SELECT COUNT(DISTINCT r.problem_id) FROM reviews r JOIN problems x ON x.id=r.problem_id WHERE x.paper_id=?",
        (p["id"],),
    ).fetchone()[0]
    return {
        "id": p["id"], "title": p["title"], "subject_id": p["subject_id"],
        "plan_id": p["plan_id"], "problems": problems, "due": due,
        "finished": finished, "untouched": max(0, problems - finished),
    }


def _problem_json(row, index=None):
    try:
        options = json.loads(row["options_json"] or "[]")
    except (TypeError, ValueError):
        options = []
    return {
        "id": row["id"],
        "no": row["no"],
        "type": row["type"] or "single",
        "parent_id": row["parent_id"],
        "text": row["text"] or "",
        "latex": row["latex"] or "",
        "options": options if isinstance(options, list) else [],
        "crop": row["crop"],
        "page": row["page"] or 1,
        "index": index,
        "text_trusted": True,
    }


def paper_detail(paper_id):
    """题目环的唯一数据源：直接读 app.db，不再依赖 result.json。"""
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return None
        rows = c.execute(
            "SELECT * FROM problems WHERE paper_id=? ORDER BY rowid", (paper_id,)
        ).fetchall()
        problems = [_problem_json(row, i) for i, row in enumerate(rows)]
        for p in problems:
            last = c.execute(
                "SELECT s.id, s.started_at, s.ended_at, "
                "(SELECT COUNT(*) FROM turns t WHERE t.session_id=s.id) AS n "
                "FROM sessions s WHERE s.problem_id=? "
                "AND EXISTS(SELECT 1 FROM turns t WHERE t.session_id=s.id) "
                "ORDER BY s.started_at DESC LIMIT 1",
                (p["id"],),
            ).fetchone()
            if last:
                p["last_session_at"] = last["ended_at"] or last["started_at"]
                p["last_session_turns"] = last["n"]
                p["last_session_open"] = last["ended_at"] is None
            rv = c.execute(
                "SELECT due, state, last_rating FROM reviews WHERE problem_id=?",
                (p["id"],),
            ).fetchone()
            if rv:
                p["review_due"] = rv["due"]
                p["review_state"] = rv["state"]
                p["review_last_rating"] = rv["last_rating"]
        pages = max([p.get("page") or 1 for p in problems] or [1])
        return {
            "id": paper["id"],
            "title": paper["title"],
            "subject_id": paper["subject_id"],
            "plan_id": paper["plan_id"],
            "pages": pages,
            "problems": problems,
        }
    finally:
        c.close()


def problem_at(paper_id, index):
    data = paper_detail(paper_id)
    if not data:
        return None
    try:
        return data["problems"][int(index)]
    except (IndexError, TypeError, ValueError):
        return None


def set_active_plan(plan_id):
    c = _conn()
    try:
        row = c.execute(
            "SELECT p.*, t.id AS task_id, t.active_plan_id FROM plans p "
            "JOIN tasks t ON t.id=p.task_id WHERE p.id=?", (plan_id,)
        ).fetchone()
        if not row:
            return {"ok": False, "error": "plan not found", "status": 404}
        if (row["status"] or "") == "archived":
            return {"ok": False, "error": "已归档计划不能设为当前", "status": 400}
        c.execute("UPDATE tasks SET active_plan_id=? WHERE id=?", (plan_id, row["task_id"]))
        c.commit()
        return {"ok": True, "planId": plan_id, "taskId": row["task_id"]}
    finally:
        c.close()


def set_plan_status(plan_id, status):
    status = str(status or "")
    if status not in ("active", "archived"):
        return {"ok": False, "error": "bad status", "status": 400}
    c = _conn()
    try:
        row = c.execute(
            "SELECT p.*, t.id AS task_id FROM plans p JOIN tasks t ON t.id=p.task_id WHERE p.id=?",
            (plan_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "error": "plan not found", "status": 404}
        if status == "archived" and _plan_phase(c, row) != "first_done":
            return {"ok": False, "error": "第一遍未完成，不能归档", "status": 400}
        c.execute("UPDATE plans SET status=? WHERE id=?", (status, plan_id))
        if status == "archived":
            c.execute("UPDATE tasks SET active_plan_id=NULL WHERE id=? AND active_plan_id=?",
                      (row["task_id"], plan_id))
        c.commit()
        return {"ok": True, "planId": plan_id, "status": status}
    finally:
        c.close()


def set_unit_status(unit_id, status):
    status = str(status or "")
    if status not in ("pending", "finished"):
        return {"ok": False, "error": "bad status", "status": 400}
    c = _conn()
    try:
        for table in ("plan_units", "writing_plan_units"):
            row = c.execute("SELECT id FROM %s WHERE id=?" % table, (unit_id,)).fetchone()
            if row:
                c.execute("UPDATE %s SET status=? WHERE id=?" % table, (status, unit_id))
                c.commit()
                return {"ok": True, "unitId": unit_id, "unitStatus": status}
        return {"ok": False, "error": "unit not found", "status": 404}
    finally:
        c.close()


def get_problem_figure(problem_id):
    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM problem_figures WHERE problem_id=?", (problem_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        c.close()


def update_problem_figure(problem_id, description):
    c = _conn()
    try:
        row = c.execute("SELECT problem_id FROM problem_figures WHERE problem_id=?", (problem_id,)).fetchone()
        if not row:
            return False
        c.execute("UPDATE problem_figures SET description=?, updated_at=? WHERE problem_id=?",
                  (description or "", db.now(), problem_id))
        c.commit()
        return True
    finally:
        c.close()


def delete_problem_figure(problem_id):
    c = _conn()
    try:
        row = c.execute("SELECT image_path FROM problem_figures WHERE problem_id=?", (problem_id,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM problem_figures WHERE problem_id=?", (problem_id,))
        c.commit()
        return row["image_path"] or ""
    finally:
        c.close()


def save_problem_figure(problem_id, image_path, description):
    now = db.now()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO problem_figures(problem_id,image_path,description,created_at,updated_at) "
            "VALUES(?,?,?,?,?) ON CONFLICT(problem_id) DO UPDATE SET "
            "image_path=excluded.image_path,description=excluded.description,updated_at=excluded.updated_at",
            (problem_id, image_path or "", description or "", now, now),
        )
        c.commit()
        return True
    finally:
        c.close()


def vocab_list():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT v.*, p.title AS paper_title FROM vocab_items v "
            "LEFT JOIN papers p ON p.id=v.paper_id "
            "ORDER BY CASE v.status WHEN 'new' THEN 0 ELSE 1 END, v.created_at DESC"
        ).fetchall()
        return {"ok": True, "items": [dict(r) for r in rows]}
    finally:
        c.close()


def vocab_add(word, sentence, paper_id):
    word = str(word or "").strip()
    if not word:
        return {"ok": False, "error": "word required", "status": 400}
    c = _conn()
    try:
        if paper_id:
            row = c.execute("SELECT id FROM papers WHERE id=?", (paper_id,)).fetchone()
            if not row:
                return {"ok": False, "error": "paper not found", "status": 404}
        else:
            paper_id = None
        rid = "v_" + uuid.uuid4().hex[:12]
        c.execute(
            "INSERT INTO vocab_items(id,problem_id,paper_id,word,sentence,status,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (rid, None, paper_id, word, str(sentence or "").strip(), "new", db.now()),
        )
        c.commit()
        return {"ok": True, "id": rid}
    finally:
        c.close()


def vocab_set_status(rid, status):
    if status not in ("new", "known"):
        return {"ok": False, "error": "bad status", "status": 400}
    c = _conn()
    try:
        row = c.execute("SELECT id FROM vocab_items WHERE id=?", (rid,)).fetchone()
        if not row:
            return {"ok": False, "error": "vocab not found", "status": 404}
        c.execute("UPDATE vocab_items SET status=? WHERE id=?", (status, rid))
        c.commit()
        return {"ok": True, "id": rid, "vocabStatus": status}
    finally:
        c.close()


def vocab_delete(rid):
    c = _conn()
    try:
        c.execute("DELETE FROM vocab_items WHERE id=?", (rid,))
        c.commit()
        return {"ok": True}
    finally:
        c.close()


def assign_paper(paper_id, plan_id):
    c = _conn()
    try:
        paper = c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone()
        if not paper:
            return {"ok": False, "error": "paper not found", "status": 404}
        plan = c.execute(
            "SELECT p.*, g.subject_id FROM plans p JOIN tasks t ON t.id=p.task_id "
            "JOIN goals g ON g.id=t.goal_id WHERE p.id=?", (plan_id,)
        ).fetchone()
        if not plan:
            return {"ok": False, "error": "plan not found", "status": 404}
        if plan["subject_id"] != paper["subject_id"]:
            return {"ok": False, "error": "科目不一致：paper=%s plan=%s" % (paper["subject_id"], plan["subject_id"]), "status": 400}
        if paper["plan_id"] == plan_id:
            return {"ok": True, "paper": _paper_json(c, paper)}
        history = c.execute("SELECT COUNT(*) FROM sessions WHERE paper_id=?", (paper_id,)).fetchone()[0]
        history += c.execute(
            "SELECT COUNT(*) FROM reviews r JOIN problems x ON x.id=r.problem_id WHERE x.paper_id=?",
            (paper_id,),
        ).fetchone()[0]
        if history:
            return {"ok": False, "error": "这份卷已有讲题/复习记录，不能换计划；请新建归档版本", "status": 409}
        c.execute("UPDATE papers SET plan_id=? WHERE id=?", (plan_id, paper_id))
        c.commit()
        return {"ok": True, "paper": _paper_json(c, c.execute("SELECT * FROM papers WHERE id=?", (paper_id,)).fetchone())}
    finally:
        c.close()


def plan_detail(plan_id):
    c = _conn()
    try:
        ensure_writing_units(c)
        c.commit()
        p = c.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
        if not p:
            return None
        papers = [_paper_json(c, x) for x in c.execute(
            "SELECT * FROM papers WHERE plan_id=? "
            "ORDER BY COALESCE(CAST(substr(title,1,4) AS INTEGER),9999), created_at",
            (plan_id,),
        ).fetchall()]
        now = _now_iso()
        problems = [
            dict(r) for r in c.execute(
                "SELECT x.id, x.no, x.text, x.type, x.paper_id, x.status, r.due, r.id AS review_id, "
                "u.id AS unit_id, u.status AS unit_status "
                "FROM problems x LEFT JOIN reviews r ON r.problem_id=x.id "
                "LEFT JOIN plan_units u ON u.problem_id=x.id "
                "WHERE x.paper_id IN (SELECT id FROM papers WHERE plan_id=?) "
                "ORDER BY x.paper_id, x.rowid",
                (plan_id,),
            ).fetchall()
        ]
        for x in problems:
            if x.get("due") and x["due"] <= now:
                x["state"] = "due"
            elif x.get("review_id"):
                x["state"] = "scheduled"
            else:
                x["state"] = "new"
        units = c.execute(
            "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=?) + "
            "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=?)",
            (plan_id, plan_id),
        ).fetchone()[0]
        done = c.execute(
            "SELECT (SELECT COUNT(*) FROM plan_units WHERE plan_id=? AND status='finished') + "
            "(SELECT COUNT(*) FROM writing_plan_units WHERE plan_id=? AND status='finished')",
            (plan_id, plan_id),
        ).fetchone()[0]
        active = c.execute(
            "SELECT t.active_plan_id FROM plans p JOIN tasks t ON t.id=p.task_id WHERE p.id=?",
            (plan_id,),
        ).fetchone()
        data = dict(p)
        data.update({
            "units": units, "units_done": done, "units_left": max(0, units - done),
            "writing": c.execute("SELECT COUNT(*) FROM writing_tasks WHERE plan_id=?", (plan_id,)).fetchone()[0],
            "phase": _plan_phase(c, p),
            "phase_label": PHASE_LABELS.get(_plan_phase(c, p), ""),
            "next": next_problem(plan_id),
            "active": bool(active and active["active_plan_id"] == plan_id),
        })
        return {"ok": True, "plan": data, "papers": papers, "problems": problems}
    finally:
        c.close()


def get_lesson_plan(problem_id):
    c = _conn()
    try:
        row = c.execute("SELECT plan_json FROM lesson_plans WHERE problem_id=?", (problem_id,)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["plan_json"])
        except ValueError:
            return None
    finally:
        c.close()


def save_lesson_plan(problem_id, plan):
    now = db.now()
    c = _conn()
    try:
        c.execute(
            "INSERT INTO lesson_plans(problem_id,plan_json,created_at,updated_at) VALUES(?,?,?,?) "
            "ON CONFLICT(problem_id) DO UPDATE SET plan_json=excluded.plan_json,updated_at=excluded.updated_at",
            (problem_id, json.dumps(plan, ensure_ascii=False), now, now),
        )
        c.commit()
        return True
    finally:
        c.close()


def get_tutor_state(session_id):
    c = _conn()
    try:
        row = c.execute("SELECT state_json FROM tutor_states WHERE session_id=?", (session_id,)).fetchone()
        if not row:
            return {}
        try:
            return json.loads(row["state_json"])
        except ValueError:
            return {}
    finally:
        c.close()


def save_tutor_state(session_id, state):
    c = _conn()
    try:
        c.execute(
            "INSERT INTO tutor_states(session_id,state_json,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET state_json=excluded.state_json,updated_at=excluded.updated_at",
            (session_id, json.dumps(state, ensure_ascii=False), db.now()),
        )
        c.commit()
        return True
    finally:
        c.close()


def set_problem_status(problem_id, status):
    c = _conn()
    try:
        c.execute("UPDATE problems SET status=? WHERE id=?", (status, problem_id))
        c.commit()
        return True
    finally:
        c.close()


def mark_problem_in_session(paper_id, index):
    problem = problem_at(paper_id, index)
    if not problem:
        return False
    return set_problem_status(problem["id"], "in_session")


def save_session(data):
    """把旧 session_store 的会话镜像进 app.db，保持同一 session id。"""
    if not data or not data.get("id"):
        return False
    sid = str(data["id"])
    paper_id = str(data.get("paper") or "")
    problem = problem_at(paper_id, data.get("index")) if paper_id else None
    problem_id = problem.get("id") if problem else None
    started = int(data.get("created_at") or db.now())
    ended = data.get("ended_at")
    c = _conn()
    try:
        if paper_id and not c.execute("SELECT 1 FROM papers WHERE id=?", (paper_id,)).fetchone():
            paper_id = ""
            problem_id = None
        c.execute(
            "INSERT INTO sessions(id,problem_id,paper_id,mode,model,started_at,ended_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "problem_id=excluded.problem_id,paper_id=excluded.paper_id,mode=excluded.mode,"
            "model=excluded.model,ended_at=excluded.ended_at",
            (sid, problem_id, paper_id or None, data.get("mode") or "tutor",
             data.get("model") or "", started, int(ended) if ended else None),
        )
        c.commit()
        return True
    finally:
        c.close()


def sync_session_history(data):
    """一次性把旧库会话的 turns 补进 app.db（仅当 app.db 还没有该会话的 turns）。"""
    if not save_session(data):
        return False
    sid = str(data["id"])
    turns = data.get("turns") or []
    c = _conn()
    try:
        if c.execute("SELECT 1 FROM turns WHERE session_id=? LIMIT 1", (sid,)).fetchone():
            return True
        for t in turns:
            c.execute(
                "INSERT INTO turns(session_id,role,content,speech,created_at) VALUES(?,?,?,?,?)",
                (sid, t.get("role") or "user", t.get("content") or "",
                 t.get("speech") or "", int(t.get("created_at") or db.now())),
            )
        c.commit()
        return True
    finally:
        c.close()


def replace_session_turns(session_id, turns):
    """回退后同步 app.db 的 turns 镜像。"""
    c = _conn()
    try:
        if not c.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
            return False
        c.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
        for t in turns or []:
            c.execute(
                "INSERT INTO turns(session_id,role,content,speech,created_at) VALUES(?,?,?,?,?)",
                (session_id, t.get("role") or "user", t.get("content") or "",
                 t.get("speech") or "", int(t.get("created_at") or db.now())),
            )
        c.commit()
        return True
    finally:
        c.close()


def append_turn(session_id, role, content, speech=""):
    c = _conn()
    try:
        if not c.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
            return False
        c.execute(
            "INSERT INTO turns(session_id,role,content,speech,created_at) VALUES(?,?,?,?,?)",
            (session_id, role, str(content or ""), str(speech or ""), db.now()),
        )
        c.commit()
        return True
    finally:
        c.close()


def end_session(session_id):
    c = _conn()
    try:
        c.execute("UPDATE sessions SET ended_at=? WHERE id=?", (db.now(), session_id))
        c.commit()
    finally:
        c.close()


def sync_review(problem_id, fsrs, summary=None, last_rating=None):
    """把旧 review_store 的 FSRS 结果同步到 app.db，供计划/时间环读。"""
    if not problem_id or not isinstance(fsrs, dict):
        return False
    c = _conn()
    try:
        exists = c.execute("SELECT 1 FROM problems WHERE id=?", (problem_id,)).fetchone()
        if not exists:
            return False
        summary = summary or {}
        now = db.now()
        c.execute(
            "INSERT INTO reviews(id,problem_id,fsrs_json,due,state,last_rating,user_summary,suggested,reason,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(problem_id) DO UPDATE SET fsrs_json=excluded.fsrs_json, due=excluded.due, "
            "state=excluded.state, last_rating=excluded.last_rating, "
            "user_summary=COALESCE(excluded.user_summary,reviews.user_summary), "
            "suggested=COALESCE(excluded.suggested,reviews.suggested), "
            "reason=COALESCE(excluded.reason,reviews.reason), updated_at=excluded.updated_at",
            (problem_id, problem_id, json.dumps(fsrs, ensure_ascii=False), fsrs.get("due"),
             fsrs.get("state_name"), last_rating, summary.get("user"), summary.get("suggested"),
             summary.get("reason"), now, now),
        )
        c.execute(
            "INSERT INTO problem_progress(problem_id,first_finished_at,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(problem_id) DO UPDATE SET first_finished_at=COALESCE(problem_progress.first_finished_at,excluded.first_finished_at), "
            "updated_at=excluded.updated_at",
            (problem_id, now, now),
        )
        c.execute("UPDATE plan_units SET status='finished' WHERE problem_id=?", (problem_id,))
        c.execute("UPDATE problems SET status='scheduled' WHERE id=?", (problem_id,))
        task = c.execute(
            "SELECT p.task_id FROM plan_units u JOIN plans p ON p.id=u.plan_id WHERE u.problem_id=?",
            (problem_id,),
        ).fetchone()
        if task:
            plans = c.execute(
                "SELECT id FROM plans WHERE task_id=? ORDER BY COALESCE(year,9999),created_at",
                (task["task_id"],),
            ).fetchall()
            chosen = None
            for plan in plans:
                left = c.execute(
                    "SELECT COUNT(*) FROM plan_units WHERE plan_id=? AND status='pending'",
                    (plan["id"],),
                ).fetchone()[0]
                if left:
                    chosen = plan["id"]
                    break
            if chosen:
                c.execute("UPDATE tasks SET active_plan_id=? WHERE id=?", (chosen, task["task_id"]))
        c.commit()
        return True
    finally:
        c.close()

    c = _conn()
    try:
        return {"ok": True, "due": [_due_json(r) for r in _due_rows(c)]}
    finally:
        c.close()


def writing_list():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT w.*, p.name AS plan_name, p.year AS plan_year "
            "FROM writing_tasks w LEFT JOIN plans p ON p.id=w.plan_id "
            "ORDER BY COALESCE(p.year,9999), w.id"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            m = re.search(r":(\d{4}):([AB])$", d["id"])
            d["year"] = int(m.group(1)) if m else d.get("plan_year")
            d["part"] = m.group(2) if m else ""
            d["draft_len"] = len(d.get("draft") or "")
            out.append(d)
        return {"ok": True, "tasks": out}
    finally:
        c.close()


def writing_templates():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT id,part,category,title,body,source,created_at FROM writing_templates "
            "ORDER BY CASE WHEN part IS NULL OR part='' THEN 1 ELSE 0 END, part,category,title"
        ).fetchall()
        return {"ok": True, "templates": [dict(r) for r in rows]}
    finally:
        c.close()


def writing_get(task_id):
    c = _conn()
    try:
        r = c.execute("SELECT * FROM writing_tasks WHERE id=?", (task_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["feedback_data"] = json.loads(d.get("feedback") or "{}")
        except (TypeError, ValueError):
            d["feedback_data"] = {}
        m = re.search(r":(\d{4}):([AB])$", d.get("id") or "")
        d["year"] = int(m.group(1)) if m else None
        d["part"] = m.group(2) if m else ""
        if d.get("image") and d.get("year"):
            d["image_url"] = "/media/ingest-english2-%s/%s" % (d["year"], d["image"])
        else:
            d["image_url"] = ""
        return d
    finally:
        c.close()


def writing_report(task_id):
    import writing_report as wr
    task = writing_get(task_id)
    if not task:
        return None
    return {"ok": True, "report": wr.build_report(task)}


def writing_feedback(task_id, draft=None):
    import speech

    task = writing_get(task_id)
    if not task:
        return None
    text = str(draft if draft is not None else (task.get("draft") or ""))
    if not text.strip():
        raise ValueError("先写草稿，再批改")
    part = "A" if (task.get("id") or "").endswith(":A") else "B"
    chart_data = None
    if task.get("chart_data"):
        try:
            chart_data = json.loads(task["chart_data"])
        except (TypeError, ValueError):
            chart_data = None
    result = speech.review_writing(task.get("prompt") or "", text, part, chart_data=chart_data)
    c = _conn()
    try:
        now = db.now()
        due = (dt.datetime.now() + dt.timedelta(days=2)).date().isoformat()
        if result.get("rewrite_required"):
            c.execute(
                "UPDATE writing_tasks SET draft=?, first_draft=COALESCE(first_draft,?), feedback=?, status='feedback', feedback_at=?, "
                "rewrite_due=?, updated_at=? WHERE id=?",
                (text, text, json.dumps(result, ensure_ascii=False), now, due, now, task_id),
            )
        else:
            c.execute(
                "UPDATE writing_tasks SET draft=?, first_draft=COALESCE(first_draft,?), feedback=?, status='ready', feedback_at=?, "
                "rewrite_due=NULL, updated_at=? WHERE id=?",
                (text, text, json.dumps(result, ensure_ascii=False), now, now, task_id),
            )
        _snapshot_writing(c, task_id, "feedback", text, json.dumps(result, ensure_ascii=False))
        c.commit()
    finally:
        c.close()
    return writing_get(task_id)


def writing_final(task_id, draft=None):
    task = writing_get(task_id)
    if not task:
        return None
    text = str(draft if draft is not None else (task.get("draft") or "")).strip()
    if not text:
        raise ValueError("重写内容为空")
    c = _conn()
    try:
        now = db.now()
        original = task.get("first_draft") or task.get("draft") or text
        pending = c.execute(
            "SELECT COALESCE(SUM(estimate_min),0) FROM queue_items "
            "WHERE type='writing' AND ref_id=? AND status IN ('todo','opened')",
            (task_id,),
        ).fetchone()[0]
        c.execute(
            "UPDATE writing_tasks SET draft=?, first_draft=COALESCE(first_draft,?), rewrite=?, status='final', rewrite_at=?, final_at=?, "
            "rewrite_due=NULL, updated_at=? WHERE id=?",
            (text, original, text, now, now, now, task_id),
        )
        _snapshot_writing(c, task_id, "final", text, task.get("feedback"))
        c.execute(
            "UPDATE queue_items SET status='done', "
            "actual_min=CASE WHEN actual_min IS NULL OR actual_min=0 THEN estimate_min ELSE actual_min END "
            "WHERE type='writing' AND ref_id=? AND status IN ('todo','opened')",
            (task_id,),
        )
        ensure_writing_units(c)
        if pending:
            week = _week_start()
            planned = DEFAULT_BUDGET.get("english2", 480)
            c.execute(
                "INSERT INTO weekly_budgets(week,subject_id,planned_min,actual_min,locked) VALUES(?,?,?,?,1) "
                "ON CONFLICT(week,subject_id) DO UPDATE SET actual_min=weekly_budgets.actual_min+excluded.actual_min",
                (week, "english2", planned, pending),
            )
        c.commit()
    finally:
        c.close()
    return writing_get(task_id)


def _snapshot_writing(c, task_id, kind, draft, feedback=None):
    c.execute(
        "INSERT INTO writing_revisions(id,writing_id,kind,draft,feedback,created_at) VALUES(?,?,?,?,?,?)",
        (db.uid("wrev"), task_id, kind, draft or "", feedback, db.now()),
    )


def writing_save(task_id, draft):
    c = _conn()
    try:
        r = c.execute("SELECT 1 FROM writing_tasks WHERE id=?", (task_id,)).fetchone()
        if not r:
            return None
        now = db.now()
        c.execute(
            "UPDATE writing_tasks SET draft=?, first_draft=COALESCE(first_draft,?), "
            "status=CASE WHEN ?='' THEN 'draft' ELSE 'revised' END, updated_at=? WHERE id=?",
            (draft, draft, draft, now, task_id),
        )
        _snapshot_writing(c, task_id, "save", draft)
        c.commit()
        return writing_get(task_id)
    finally:
        c.close()


def queue_open(queue_id):
    c = _conn()
    try:
        row = c.execute("SELECT * FROM queue_items WHERE id=?", (queue_id,)).fetchone()
        if not row:
            return None
        c.execute("UPDATE queue_items SET status='opened' WHERE id=?", (queue_id,))
        c.commit()
        return dict(row)
    finally:
        c.close()


def queue_done(queue_id):
    c = _conn()
    try:
        row = c.execute("SELECT * FROM queue_items WHERE id=?", (queue_id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        if item.get("status") == "done":
            return item
        minutes = int(item.get("estimate_min") or 0)
        c.execute(
            "UPDATE queue_items SET status='done', "
            "actual_min=CASE WHEN actual_min IS NULL OR actual_min=0 THEN estimate_min ELSE actual_min END "
            "WHERE id=?",
            (queue_id,),
        )
        if minutes:
            week = _week_start()
            sid = item.get("subject_id") or "math2"
            planned = DEFAULT_BUDGET.get(sid, 0)
            c.execute(
                "INSERT INTO weekly_budgets(week,subject_id,planned_min,actual_min,locked) VALUES(?,?,?,?,1) "
                "ON CONFLICT(week,subject_id) DO UPDATE SET actual_min=weekly_budgets.actual_min+excluded.actual_min",
                (week, sid, planned, minutes),
            )
        c.commit()
        item["status"] = "done"
        item["actual_min"] = minutes
        return item
    finally:
        c.close()


def _budgets(c):
    week = _week_start()
    rows = c.execute(
        "SELECT w.subject_id, w.planned_min, w.actual_min, s.name FROM weekly_budgets w "
        "JOIN subjects s ON s.id=w.subject_id WHERE w.week=?", (week,)
    ).fetchall()
    out = {}
    for r in rows:
        out[r["subject_id"]] = {"planned": r["planned_min"], "actual": r["actual_min"], "name": r["name"]}
    for sid, planned in DEFAULT_BUDGET.items():
        out.setdefault(sid, {"planned": planned, "actual": 0, "name": sid})
    return out


def writing_due_rows(c):
    today = _today()
    rows = c.execute(
        "SELECT w.*, p.name AS plan_name, p.year AS plan_year "
        "FROM writing_tasks w LEFT JOIN plans p ON p.id=w.plan_id "
        "WHERE w.rewrite_due IS NOT NULL AND w.rewrite_due <= ? "
        "AND w.status IN ('feedback','rewrite') "
        "ORDER BY w.rewrite_due, w.id",
        (today,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        m = re.search(r":(\d{4}):([AB])$", d["id"])
        year = m.group(1) if m else (d.get("plan_year") or "")
        part = m.group(2) if m else ""
        out.append({
            "type": "writing",
            "id": d["id"],
            "subject_id": "english2",
            "title": "%s 英二 Part %s" % (year, part),
            "due": d.get("rewrite_due"),
            "estimate_min": 25,
            "status": d.get("status"),
            "plan_id": d.get("plan_id"),
        })
    return out


def due_list():
    c = _conn()
    try:
        due = [_due_json(r) for r in _due_rows(c)] + writing_due_rows(c)
        due.sort(key=lambda x: str(x.get("due") or ""))
        return {"ok": True, "due": due}
    finally:
        c.close()


def get_time(day=None):
    day = day or _today()
    c = _conn()
    try:
        carried = c.execute(
            "SELECT COUNT(*) FROM queue_items q JOIN writing_tasks w ON w.id=q.ref_id "
            "WHERE q.type='writing' AND q.status='carried'"
        ).fetchone()[0]
        plan = c.execute("SELECT * FROM daily_plans WHERE date=?", (day,)).fetchone()
        if not plan:
            return {"ok": True, "date": day, "plan": None, "blocks": [], "carried_writing": carried}
        items = c.execute(
            "SELECT q.*, s.name AS subject_name FROM queue_items q "
            "LEFT JOIN subjects s ON s.id=q.subject_id WHERE q.daily_plan_id=? ORDER BY q.sort, q.id",
            (plan["id"],),
        ).fetchall()
        blocks = {}
        for q in items:
            sid = q["subject_id"] or "other"
            b = blocks.setdefault(sid, {
                "subject_id": sid, "subject": q["subject_name"] or "其他",
                "minutes": 0, "items": [],
            })
            b["minutes"] += q["estimate_min"] or 0
            b["items"].append(dict(q))
        return {"ok": True, "date": day, "plan": dict(plan), "blocks": list(blocks.values()), "carried_writing": carried}
    finally:
        c.close()


def _choose_subjects(c, due_by_subject, budgets, max_n=3):
    chosen = []
    for sid, n in sorted(due_by_subject.items(), key=lambda kv: -kv[1]):
        if n > 0 and sid not in chosen:
            chosen.append(sid)
    if "math2" not in chosen:
        chosen.insert(0, "math2")
    rest = [
        (sid, max(0, b["planned"] - b["actual"]))
        for sid, b in budgets.items() if sid not in chosen
    ]
    rest.sort(key=lambda kv: -kv[1])
    for sid, _ in rest:
        if len(chosen) >= max_n:
            break
        chosen.append(sid)
    return chosen[:max_n]


def _carry_previous(c, day):
    c.execute(
        "UPDATE queue_items SET status='carried' "
        "WHERE status IN ('todo','opened') AND daily_plan_id IN "
        "(SELECT id FROM daily_plans WHERE date < ?)",
        (day,),
    )


def generate_time(day=None, available_min=180):
    day = day or _today()
    available_min = max(30, min(720, int(available_min)))
    c = _conn()
    try:
        _carry_previous(c, day)
        due_rows = _due_rows(c)
        due_by_subject = {}
        due_map = {}
        for r in due_rows:
            sid = r["subject_id"]
            due_by_subject[sid] = due_by_subject.get(sid, 0) + 1
            due_map.setdefault(sid, []).append(dict(r))
        for r in writing_due_rows(c):
            sid = "english2"
            due_by_subject[sid] = due_by_subject.get(sid, 0) + 1
            due_map.setdefault(sid, []).append(r)
        budgets = _budgets(c)
        subjects = _choose_subjects(c, due_by_subject, budgets, 3)
        usable = int(available_min * 0.8)
        due_minutes = sum(
            sum(int(x.get("estimate_min") or REVIEW_MIN) for x in items)
            for items in due_map.values()
        )
        due_only = due_minutes > available_min * 0.6
        weights = {}
        for sid in subjects:
            b = budgets.get(sid) or {"planned": 0, "actual": 0}
            weights[sid] = max(30, b["planned"] - b["actual"])
        total_weight = sum(weights.values()) or 1
        alloc = {}
        remain = usable
        for sid in subjects:
            alloc[sid] = max(15, int(usable * weights[sid] / total_weight))
        # 修正总和
        diff = usable - sum(alloc.values())
        if diff:
            sid = subjects[0]
            alloc[sid] = max(15, alloc[sid] + diff)
        # 优先保证到期题
        for sid in subjects:
            alloc[sid] = max(0, alloc[sid])
        # 有写作/到期项时，保证该科目至少装得下最早的一个到期项
        for sid, items in due_map.items():
            if sid not in alloc:
                continue
            need = min(usable, sum(int(x.get("estimate_min") or REVIEW_MIN) for x in items))
            if alloc[sid] >= need:
                continue
            add = need - alloc[sid]
            for other in sorted(subjects, key=lambda x: alloc.get(x, 0), reverse=True):
                if other == sid or add <= 0:
                    continue
                take = min(add, max(0, alloc.get(other, 0) - 15))
                alloc[other] -= take
                alloc[sid] += take
                add -= take

        # 政治在平台外复习，但保留一个 30 分钟自主块
        if "politics" not in subjects and available_min >= 120 and budgets.get("politics"):
            subjects.append("politics")
            alloc["politics"] = 30
            for other in sorted([x for x in subjects if x != "politics"], key=lambda x: alloc.get(x, 0), reverse=True):
                take = min(30, max(0, alloc.get(other, 0) - 15))
                alloc[other] -= take
                if take:
                    break

        plan = c.execute("SELECT * FROM daily_plans WHERE date=?", (day,)).fetchone()
        if plan:
            if plan["status"] == "confirmed":
                return {"ok": False, "error": "今天已确认，先不要重排"}
            pid = plan["id"]
            c.execute("UPDATE daily_plans SET available_min=?,status='draft',updated_at=? WHERE id=?",
                      (available_min, db.now(), pid))
            c.execute("DELETE FROM queue_items WHERE daily_plan_id=?", (pid,))
        else:
            pid = db.uid("day")
            c.execute(
                "INSERT INTO daily_plans(id,date,available_min,status,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (pid, day, available_min, "draft", db.now(), db.now()),
            )
        order = 0
        for sid in subjects:
            minutes = alloc.get(sid, 0)
            if minutes <= 0:
                continue
            due_items = due_map.get(sid, [])
            due_take = 0
            due_est = 0
            if not (due_only and sid not in due_by_subject):
                for item in due_items:
                    est = int(item.get("estimate_min") or REVIEW_MIN)
                    if due_est + est > minutes:
                        break
                    due_est += est
                    due_take += 1
            used = 0
            for r in due_items[:due_take]:
                order += 1
                if r.get("type") == "writing":
                    est = int(r.get("estimate_min") or 25)
                    c.execute(
                        "INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                        "VALUES(?,?,?,?,?,?,?,?,0,?,?)",
                        (db.uid("q"), pid, sid, "writing", r["id"], est, order, "todo",
                         r["title"], db.now()),
                    )
                    used += est
                    continue
                c.execute(
                    "INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,0,?,?)",
                    (db.uid("q"), pid, sid, "review", r["problem_id"], REVIEW_MIN, order, "todo",
                     "%s 第%s题" % (r["paper_title"], r["no"]), db.now()),
                )
                used += REVIEW_MIN
            if not due_only:
                left = max(0, minutes - used)
                if sid == "politics":
                    if left >= 30:
                        order += 1
                        c.execute(
                            "INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                            "VALUES(?,?,?,?,NULL,?,?,?,0,?,?)",
                            (db.uid("q"), pid, sid, "offline", 30, order, "todo",
                             "政治自主复习", db.now()),
                        )
                        used += 30
                else:
                    est = NEW_EST.get(sid, 25)
                    n = left // est
                    for _ in range(n):
                        order += 1
                        c.execute(
                            "INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                            "VALUES(?,?,?,?,NULL,?,?,?,0,?,?)",
                            (db.uid("q"), pid, sid, "new", est, order, "todo",
                             "下一道新题", db.now()),
                        )
                        used += est
            if alloc.get(sid, 0) - used >= 10:
                order += 1
                c.execute(
                    "INSERT INTO queue_items(id,daily_plan_id,subject_id,type,ref_id,estimate_min,sort,status,actual_min,title,created_at) "
                    "VALUES(?,?,?,?,NULL,?,?,?,0,?,?)",
                    (db.uid("q"), pid, sid, "buffer", alloc[sid] - used, order, "todo", "缓冲/回看", db.now()),
                )
        c.commit()
        return get_time(day)
    finally:
        c.close()


def confirm_time(day=None):
    day = day or _today()
    c = _conn()
    try:
        plan = c.execute("SELECT * FROM daily_plans WHERE date=?", (day,)).fetchone()
        if not plan:
            return {"ok": False, "error": "今天还没有排"}
        c.execute("UPDATE daily_plans SET status='confirmed',updated_at=? WHERE id=?", (db.now(), plan["id"]))
        c.commit()
        return get_time(day)
    finally:
        c.close()
