#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tutor 会话存储：SQLite，一道题一个 session，记录全部 turns。"""
import json
import os
import sqlite3
import time
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")
DB = os.path.join(DATA, "tutor.sqlite")


def _conn():
    os.makedirs(DATA, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            paper TEXT NOT NULL,
            problem_index INTEGER NOT NULL,
            mode TEXT NOT NULL DEFAULT 'tutor',
            model TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            ended_at INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            speech TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id, id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_sessions_lookup ON sessions(paper, problem_index, mode, updated_at)")
    c.commit()
    return c


def _session_row(c, sid):
    return c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()


def _turns(c, sid):
    rows = c.execute(
        "SELECT role, content, speech, created_at FROM turns WHERE session_id=? ORDER BY id",
        (sid,),
    ).fetchall()
    return [dict(r) for r in rows]


def _payload(c, row):
    return {
        "id": row["id"],
        "paper": row["paper"],
        "index": row["problem_index"],
        "mode": row["mode"],
        "model": row["model"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "ended_at": row["ended_at"],
        "turns": _turns(c, row["id"]),
    }


def get_or_create(paper, index, mode="tutor", model=""):
    paper = str(paper)
    index = int(index)
    mode = str(mode or "tutor")
    c = _conn()
    try:
        row = c.execute(
            "SELECT * FROM sessions WHERE paper=? AND problem_index=? AND ended_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 1",
            (paper, index),
        ).fetchone()
        if row:
            if row["mode"] != mode:
                c.execute("UPDATE sessions SET mode=?, updated_at=? WHERE id=?",
                          (mode, int(time.time()), row["id"]))
                c.commit()
                row = _session_row(c, row["id"])
            return _payload(c, row)
        sid = uuid.uuid4().hex
        now = int(time.time())
        c.execute(
            "INSERT INTO sessions(id,paper,problem_index,mode,model,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (sid, paper, index, mode, model or "", now, now),
        )
        c.commit()
        return _payload(c, _session_row(c, sid))
    finally:
        c.close()


def history_for_problem(paper, index):
    """按题目返回全部历史，按会话分成复述批次。"""
    paper = str(paper)
    index = int(index)
    c = _conn()
    try:
        sessions = c.execute(
            "SELECT * FROM sessions WHERE paper=? AND problem_index=? ORDER BY created_at, id",
            (paper, index),
        ).fetchall()
        batches = []
        flat = []
        for row in sessions:
            turns = _turns(c, row["id"])
            for t in turns:
                t["session_id"] = row["id"]
                flat.append(t)
            batches.append({
                "id": row["id"],
                "mode": row["mode"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "ended_at": row["ended_at"],
                "turns": turns,
            })
        open_row = c.execute(
            "SELECT * FROM sessions WHERE paper=? AND problem_index=? AND ended_at IS NULL "
            "ORDER BY updated_at DESC LIMIT 1",
            (paper, index),
        ).fetchone()
        return {
            "sessionId": open_row["id"] if open_row else None,
            "batches": batches,
            "turns": flat,
        }
    finally:
        c.close()


def rollback_at(sid, turn_index):
    """回退到某条消息之前；删除该消息及它之后的所有 turns。"""
    c = _conn()
    try:
        row = _session_row(c, sid)
        if not row:
            return None
        turns = c.execute(
            "SELECT id FROM turns WHERE session_id=? ORDER BY id", (sid,)
        ).fetchall()
        idx = int(turn_index)
        if idx < 0 or idx > len(turns):
            raise ValueError("bad turn index")
        if idx < len(turns):
            target = turns[idx]["id"]
            c.execute("DELETE FROM turns WHERE session_id=? AND id>=?", (sid, target))
        c.execute("UPDATE sessions SET updated_at=? WHERE id=?", (int(time.time()), sid))
        c.commit()
        return _payload(c, _session_row(c, sid))
    finally:
        c.close()


def get(sid):
    c = _conn()
    try:
        row = _session_row(c, sid)
        return _payload(c, row) if row else None
    finally:
        c.close()


def append(sid, role, content, speech=""):
    role = str(role)
    if role not in ("user", "assistant", "summary"):
        return
    content = str(content or "")
    if not content.strip():
        return
    c = _conn()
    try:
        now = int(time.time())
        c.execute(
            "INSERT INTO turns(session_id,role,content,speech,created_at) VALUES(?,?,?,?,?)",
            (sid, role, content, str(speech or ""), now),
        )
        c.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
        c.commit()
    finally:
        c.close()


def end(sid):
    c = _conn()
    try:
        c.execute("UPDATE sessions SET ended_at=?, updated_at=? WHERE id=?", (int(time.time()), int(time.time()), sid))
        c.commit()
    finally:
        c.close()


def recent(limit=10):
    c = _conn()
    try:
        rows = c.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (int(limit),)
        ).fetchall()
        return [_payload(c, r) for r in rows]
    finally:
        c.close()
