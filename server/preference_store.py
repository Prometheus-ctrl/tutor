#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B 偏好投票存储。"""
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
        CREATE TABLE IF NOT EXISTS preference_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at INTEGER NOT NULL,
            paper TEXT,
            problem_index INTEGER,
            session_id TEXT,
            axis TEXT,
            option_a TEXT,
            option_b TEXT,
            a_source TEXT,
            b_source TEXT,
            choice TEXT NOT NULL
        )
    """)
    c.commit()
    return c


def vote(paper, index, session_id, axis, option_a, option_b, a_source, b_source, choice):
    if choice not in ("a", "b", "neither", "similar"):
        raise ValueError("bad choice")
    c = _conn()
    try:
        c.execute(
            "INSERT INTO preference_votes(created_at,paper,problem_index,session_id,axis,"
            "option_a,option_b,a_source,b_source,choice) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (int(time.time()), str(paper or ""), int(index or 0), str(session_id or ""),
             str(axis or ""), str(option_a or ""), str(option_b or ""),
             str(a_source or ""), str(b_source or ""), choice),
        )
        c.commit()
        return c.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
    finally:
        c.close()


def summary():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT axis, choice, COUNT(*) AS n FROM preference_votes GROUP BY axis, choice"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()
