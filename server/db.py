#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tutor 新应用数据底座：一个 SQLite，三环共用。

表：
  subjects / goals / tasks / plans / papers / problems
  sessions / turns
  reviews
  vocab_items / writing_tasks
  exam_profile / schedule_events
  daily_plans / queue_items

旧 tutor 的 result.json、reviews.json、sessions.sqlite 由 migrate.py 导入。
"""
import json
import os
import sqlite3
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS subjects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  code TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
  id TEXT PRIMARY KEY,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  external_id TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
  id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  external_id TEXT,
  active_plan_id TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plans (
  id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  year INTEGER,
  status TEXT NOT NULL DEFAULT 'active',
  external_id TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS papers (
  id TEXT PRIMARY KEY,
  plan_id TEXT REFERENCES plans(id) ON DELETE SET NULL,
  subject_id TEXT NOT NULL REFERENCES subjects(id),
  title TEXT NOT NULL,
  source_dir TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS problems (
  id TEXT PRIMARY KEY,
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  subject_id TEXT NOT NULL REFERENCES subjects(id),
  type TEXT NOT NULL DEFAULT 'single',
  parent_id TEXT REFERENCES problems(id) ON DELETE CASCADE,
  no TEXT,
  text TEXT,
  latex TEXT,
  image TEXT,
  bbox TEXT,
  options_json TEXT,
  crop TEXT,
  page INTEGER,
  reference_answer TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS plan_units (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
  problem_id TEXT NOT NULL UNIQUE REFERENCES problems(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS writing_plan_units (
  id TEXT PRIMARY KEY,
  plan_id TEXT NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  writing_id TEXT NOT NULL UNIQUE REFERENCES writing_tasks(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS writing_revisions (
  id TEXT PRIMARY KEY,
  writing_id TEXT NOT NULL REFERENCES writing_tasks(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  draft TEXT,
  feedback TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_writing_revisions_task ON writing_revisions(writing_id, created_at);

CREATE TABLE IF NOT EXISTS writing_templates (
  id TEXT PRIMARY KEY,
  part TEXT,
  category TEXT,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  source TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plan_units_plan ON plan_units(plan_id, status);

CREATE TABLE IF NOT EXISTS problem_progress (
  problem_id TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,
  first_finished_at INTEGER,
  last_session_id TEXT,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS lesson_plans (
  problem_id TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,
  plan_json TEXT NOT NULL,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS tutor_states (
  session_id TEXT PRIMARY KEY,
  state_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  problem_id TEXT REFERENCES problems(id) ON DELETE SET NULL,
  paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
  mode TEXT NOT NULL DEFAULT 'tutor',
  model TEXT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER
);

CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  speech TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY,
  problem_id TEXT NOT NULL UNIQUE REFERENCES problems(id) ON DELETE CASCADE,
  fsrs_json TEXT NOT NULL,
  due TEXT,
  state TEXT,
  last_rating TEXT,
  user_summary TEXT,
  suggested TEXT,
  reason TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS vocab_items (
  id TEXT PRIMARY KEY,
  problem_id TEXT REFERENCES problems(id) ON DELETE SET NULL,
  paper_id TEXT REFERENCES papers(id) ON DELETE SET NULL,
  word TEXT NOT NULL,
  sentence TEXT,
  status TEXT NOT NULL DEFAULT 'new',
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS problem_figures (
  problem_id TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,
  image_path TEXT,
  description TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS writing_tasks (
  id TEXT PRIMARY KEY,
  plan_id TEXT REFERENCES plans(id) ON DELETE SET NULL,
  prompt TEXT NOT NULL,
  outline TEXT,
  image TEXT,
  chart_data TEXT,
  first_draft TEXT,
  draft TEXT,
  feedback TEXT,
  rewrite TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  rewrite_due TEXT,
  feedback_at INTEGER,
  rewrite_at INTEGER,
  final_at INTEGER,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS exam_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  label TEXT,
  exam_date TEXT,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS schedule_events (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'other',
  start_at TEXT NOT NULL,
  end_at TEXT,
  source TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS availability_template (
  id TEXT PRIMARY KEY,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 1 AND 7),
  start_min INTEGER NOT NULL,
  end_min INTEGER NOT NULL,
  title TEXT NOT NULL,
  type TEXT NOT NULL DEFAULT 'class'
);

CREATE TABLE IF NOT EXISTS weekly_budgets (
  week TEXT NOT NULL,
  subject_id TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  planned_min INTEGER NOT NULL,
  actual_min INTEGER NOT NULL DEFAULT 0,
  locked INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (week, subject_id)
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_plans (
  id TEXT PRIMARY KEY,
  date TEXT NOT NULL UNIQUE,
  available_min INTEGER,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS queue_items (
  id TEXT PRIMARY KEY,
  daily_plan_id TEXT NOT NULL REFERENCES daily_plans(id) ON DELETE CASCADE,
  subject_id TEXT REFERENCES subjects(id),
  type TEXT NOT NULL,
  ref_id TEXT,
  estimate_min INTEGER,
  sort INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'todo',
  actual_min INTEGER,
  title TEXT,
  meta TEXT,
  created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_goals_subject ON goals(subject_id);
CREATE INDEX IF NOT EXISTS idx_tasks_goal ON tasks(goal_id);
CREATE INDEX IF NOT EXISTS idx_plans_task ON plans(task_id);
CREATE INDEX IF NOT EXISTS idx_papers_plan ON papers(plan_id);
CREATE INDEX IF NOT EXISTS idx_problems_paper ON problems(paper_id);
CREATE INDEX IF NOT EXISTS idx_problems_parent ON problems(parent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_problem ON sessions(problem_id);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id);
CREATE INDEX IF NOT EXISTS idx_reviews_due ON reviews(due);
CREATE INDEX IF NOT EXISTS idx_queue_plan ON queue_items(daily_plan_id, sort);
"""


def connect(path=None):
    p = path or DB
    os.makedirs(os.path.dirname(p), exist_ok=True)
    c = sqlite3.connect(p)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init(path=None):
    c = connect(path)
    try:
        c.executescript(SCHEMA)
        cols = [r[1] for r in c.execute("PRAGMA table_info(queue_items)").fetchall()]
        if "title" not in cols:
            c.execute("ALTER TABLE queue_items ADD COLUMN title TEXT")
        if "meta" not in cols:
            c.execute("ALTER TABLE queue_items ADD COLUMN meta TEXT")
        tcols = [r[1] for r in c.execute("PRAGMA table_info(tasks)").fetchall()]
        if "active_plan_id" not in tcols:
            c.execute("ALTER TABLE tasks ADD COLUMN active_plan_id TEXT")
        wcols = [r[1] for r in c.execute("PRAGMA table_info(writing_tasks)").fetchall()]
        for name in ("feedback_at", "rewrite_at", "final_at"):
            if name not in wcols:
                c.execute("ALTER TABLE writing_tasks ADD COLUMN %s INTEGER" % name)
        if "first_draft" not in wcols:
            c.execute("ALTER TABLE writing_tasks ADD COLUMN first_draft TEXT")
        if "image" not in wcols:
            c.execute("ALTER TABLE writing_tasks ADD COLUMN image TEXT")
        if "chart_data" not in wcols:
            c.execute("ALTER TABLE writing_tasks ADD COLUMN chart_data TEXT")
        pcols = [r[1] for r in c.execute("PRAGMA table_info(problems)").fetchall()]
        for name, typ in (
            ("options_json", "TEXT"),
            ("crop", "TEXT"),
            ("page", "INTEGER"),
            ("reference_answer", "TEXT"),
        ):
            if name not in pcols:
                c.execute("ALTER TABLE problems ADD COLUMN %s %s" % (name, typ))
        c.commit()
    finally:
        c.close()


def now():
    return int(time.time())


def uid(prefix="x"):
    return prefix + "_" + uuid.uuid4().hex[:12]


def summary(path=None):
    c = connect(path)
    try:
        tables = ["subjects", "goals", "tasks", "plans", "papers", "problems",
                  "sessions", "turns", "reviews", "vocab_items", "writing_tasks",
                  "schedule_events", "availability_template", "weekly_budgets",
                  "daily_plans", "queue_items"]
        out = {}
        for t in tables:
            try:
                out[t] = c.execute("SELECT COUNT(*) FROM " + t).fetchone()[0]
            except sqlite3.Error:
                out[t] = None
        return out
    finally:
        c.close()


if __name__ == "__main__":
    init()
    print(json.dumps(summary(), ensure_ascii=False, indent=2))
