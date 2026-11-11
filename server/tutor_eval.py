#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线评估 tutor 会话：真实 vs 策略模拟。

用法：python tutor_eval.py <session_id>
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import db  # noqa: E402
import tutor_policy  # noqa: E402


def load_turns(session_id):
    c = db.connect()
    try:
        rows = c.execute(
            "SELECT role,content FROM turns WHERE session_id=? ORDER BY rowid",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        c.close()


def evaluate(turns):
    state = tutor_policy.initial_state()
    actions = []
    probe_streak = max_probe = 0
    hint_level = 0
    for t in turns:
        if t.get("role") != "user":
            continue
        move = tutor_policy.classify_move(t.get("content"))
        action, state = tutor_policy.next_action(state, move)
        actions.append({"move": move, "action": action})
        probe_streak = probe_streak + 1 if action == "probe" else 0
        max_probe = max(max_probe, probe_streak)
        hint_level = state.get("hint_level", 0)
    assistant = [t for t in turns if t.get("role") == "assistant"]
    qs = [t for t in assistant if "？" in (t.get("content") or "") or "?" in (t.get("content") or "")]
    streak = max_q = 0
    flags = {}
    for t in assistant:
        content = t.get("content") or ""
        streak = streak + 1 if ("？" in content or "?" in content) else 0
        max_q = max(max_q, streak)
        for f in tutor_policy.style_flags(content):
            flags[f] = flags.get(f, 0) + 1
    return {
        "user_turns": sum(1 for t in turns if t.get("role") == "user"),
        "assistant_turns": len(assistant),
        "actual_question_turns": len(qs),
        "actual_max_question_streak": max_q,
        "simulated_actions": actions,
        "simulated_max_probe_streak": max_probe,
        "simulated_final_hint_level": hint_level,
        "style_flags": flags,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: python tutor_eval.py <session_id>")
        return 1
    sid = sys.argv[1]
    turns = load_turns(sid)
    if not turns:
        print(json.dumps({"error": "no turns", "session_id": sid}, ensure_ascii=False))
        return 1
    data = evaluate(turns)
    data["session_id"] = sid
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
