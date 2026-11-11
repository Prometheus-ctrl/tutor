#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对话中的主动反馈：只记录，不自动改学伴。"""
import json
import os
import sqlite3
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "tutor.sqlite")


def _conn():
    os.makedirs(DATA, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS companion_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            paper TEXT,
            problem_index INTEGER,
            session_id TEXT,
            tags TEXT NOT NULL,
            note TEXT
        )
    """)
    c.commit()
    return c


def add(paper, index, session_id, tags, note=""):
    tags = [str(x).strip() for x in (tags or []) if str(x).strip()]
    if not tags:
        raise ValueError("tags required")
    c = _conn()
    try:
        cur = c.execute(
            "INSERT INTO companion_feedback(created_at,paper,problem_index,session_id,tags,note) "
            "VALUES(?,?,?,?,?,?)",
            (int(time.time()), str(paper or ""), int(index or 0), str(session_id or ""),
             json.dumps(tags, ensure_ascii=False), str(note or "")),
        )
        c.commit()
        return cur.lastrowid
    finally:
        c.close()
