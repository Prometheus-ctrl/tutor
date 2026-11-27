#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线重放：用真实 tutor 会话检验 loop 控制器（不调 LLM、不花钱、只读数据）。

generate 注入为"返回该轮真实的 assistant 回复"，因此测量的是：
如果当时走 loop 引擎，这些真实回复有多少能一次通过契约校验、
决策状态机会给出什么动作分布、兜底会被触发多少次。
重试次数仅反映"不合格"（重放里模型不会改稿，不合格的轮次必进兜底）。

用法：cd tutor\\server && python tutor_replay.py [--mode tutor]
"""
import argparse
import json
import os
import sqlite3
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402
import tutor_loop  # noqa: E402
import tutor_policy  # noqa: E402


def connect_ro():
    path = os.path.abspath(db.DB).replace("\\", "/")
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def load_sessions(mode):
    c = connect_ro()
    try:
        rows = c.execute(
            "SELECT id FROM sessions WHERE mode=? ORDER BY started_at", (mode,)
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        c.close()


def load_turns(session_id):
    c = connect_ro()
    try:
        rows = c.execute(
            "SELECT role, content FROM turns WHERE session_id=? ORDER BY rowid",
            (session_id,),
        ).fetchall()
        return [{"role": r[0], "content": r[1]} for r in rows]
    finally:
        c.close()


def pair_turns(turns):
    """把 turns 配成 [(user, assistant|None)]；summary 等其他角色跳过。"""
    rounds = []
    pending_user = None
    for t in turns:
        role = t.get("role")
        if role == "user":
            if pending_user is not None:
                rounds.append((pending_user, None))
            pending_user = t.get("content") or ""
        elif role == "assistant":
            if pending_user is not None:
                rounds.append((pending_user, t.get("content") or ""))
                pending_user = None
    if pending_user is not None:
        rounds.append((pending_user, None))
    return rounds


def replay_session(turns, max_retries=2):
    """重放一条会话，返回每轮 trace 列表。"""
    state = tutor_policy.initial_state()
    history = []
    traces = []
    for user_text, real_reply in pair_turns(turns):
        def _gen(text, hist, ctx, extra, meta, _reply=real_reply):
            return {"text": _reply, "speech": _reply}

        loop = tutor_loop.TutorLoop(generate=_gen, max_retries=max_retries)
        out = loop.step(user_text, state=state, history=history)
        state = out["state"]
        traces.append(out["trace"])
        history.append({"role": "user", "content": user_text})
        if real_reply:
            history.append({"role": "assistant", "content": real_reply})
    return traces


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="tutor")
    ap.add_argument("--max-retries", type=int, default=2)
    args = ap.parse_args()

    sessions = load_sessions(args.mode)
    all_traces = []
    per_session = []
    for sid in sessions:
        turns = load_turns(sid)
        if not turns:
            continue
        traces = replay_session(turns, max_retries=args.max_retries)
        if not traces:
            continue
        all_traces.extend(traces)
        per_session.append({
            "session": sid,
            "turns": len(traces),
            "first_try_valid": sum(1 for t in traces if t["valid"] and t["attempts"] == 1),
            "fallback": sum(1 for t in traces if t["fallback"]),
            "actions": dict(Counter(t["action"] for t in traces)),
        })

    total = len(all_traces)
    summary = {
        "mode": args.mode,
        "sessions": len(per_session),
        "turns": total,
        "first_try_valid": sum(1 for t in all_traces if t["valid"] and t["attempts"] == 1),
        "fallback_turns": sum(1 for t in all_traces if t["fallback"]),
        "actions": dict(Counter(t["action"] for t in all_traces)),
        "moves": dict(Counter(t["move"] for t in all_traces)),
        "per_session": per_session,
    }
    if total:
        summary["first_try_valid_rate"] = round(summary["first_try_valid"] / total, 3)
        summary["fallback_rate"] = round(summary["fallback_turns"] / total, 3)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
